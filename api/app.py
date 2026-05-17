"""Set up logging before importing anything else"""

import sentry_sdk

from api.constants import DEPLOYMENT_MODE, ENABLE_TELEMETRY, SENTRY_DSN
from api.logging_config import ENVIRONMENT, setup_logging

# Set up logging and get the listener for cleanup
setup_logging()


if SENTRY_DSN and (
    DEPLOYMENT_MODE != "oss" or (DEPLOYMENT_MODE == "oss" and ENABLE_TELEMETRY)
):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        environment=ENVIRONMENT,
    )
    print(f"Sentry initialized in environment: {ENVIRONMENT}")


from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from api.constants import REDIS_URL
from api.mcp_server import mcp
from api.routes.main import router as main_router
from api.services.pipecat.tracing_config import (
    handle_langfuse_sync,
    load_all_org_langfuse_credentials,
)
from api.services.worker_sync.manager import (
    WorkerSyncManager,
    set_worker_sync_manager,
)
from api.services.worker_sync.protocol import WorkerSyncEventType
from api.tasks.arq import get_arq_redis

API_PREFIX = "/api/v1"

mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_app.lifespan(app):
        # warmup arq pool
        await get_arq_redis()

        # Pre-register all org-specific Langfuse exporters so they're ready
        # before any pipeline runs, without per-call DB lookups.
        await load_all_org_langfuse_credentials()

        # Start cross-worker sync manager so config changes propagate to all workers
        sync_manager = WorkerSyncManager(REDIS_URL)
        sync_manager.register(
            WorkerSyncEventType.LANGFUSE_CREDENTIALS, handle_langfuse_sync
        )
        await sync_manager.start()
        set_worker_sync_manager(sync_manager)

        yield  # Run app

        # Shutdown sequence - this runs when FastAPI is shutting down
        logger.info("Starting graceful shutdown...")
        await sync_manager.stop()


app = FastAPI(
    title="Dograh API",
    description="API for the Dograh app",
    version="1.0.0",
    openapi_url=f"{API_PREFIX}/openapi.json",
    lifespan=lifespan,
    servers=[
        {"url": "https://app.dograh.com", "description": "Production"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

api_router = APIRouter()

# include subrouters here
api_router.include_router(main_router)

# main router with api prefix
app.include_router(api_router, prefix=API_PREFIX)

# Mount the MCP server — agents reach it at /api/v1/mcp over Streamable HTTP,
# authenticating with the same X-API-Key header used by the REST API.
# Mounted under /api/v1 so existing reverse-proxy rules (nginx etc.) route it
# without any extra configuration.
app.mount(f"{API_PREFIX}/mcp", mcp_app)


# ----------------------------------------------------
# Transparent Asterisk ARI Reverse-Proxy Middleware
# ----------------------------------------------------
import asyncio
import httpx
import aiohttp
from fastapi import Request, Response, WebSocket, WebSocketDisconnect

ASTERISK_ARI_URL = "http://asterisk:8088/ari"
ASTERISK_ARI_WS = "ws://asterisk:8088/ari"

@app.post("/ari/channels")
async def proxy_ari_channels(request: Request):
    logger.info("[ARI REST Proxy] Received originate call request")
    query_params = dict(request.query_params)
    logger.info(f"[ARI REST Proxy] Query params: {query_params}")
    
    if "endpoint" in query_params:
        endpoint = query_params["endpoint"]
        old_endpoint = endpoint
        
        # Smart formatting logic
        if endpoint.startswith("PJSIP/vobiz-out/sip:") or endpoint.startswith("SIP/vobiz-out/sip:"):
            pass
        elif endpoint.startswith("vobiz-out/sip:"):
            query_params["endpoint"] = f"PJSIP/{endpoint}"
        elif endpoint.startswith("PJSIP/"):
            bare_target = endpoint.replace("PJSIP/", "", 1)
            clean_number = "".join(c for c in bare_target if c.isdigit())
            if len(clean_number) >= 10:
                query_params["endpoint"] = f"PJSIP/vobiz-out/sip:{clean_number}@31868684.sip.vobiz.ai"
        else:
            clean_number = "".join(c for c in endpoint if c.isdigit())
            if len(clean_number) >= 10:
                query_params["endpoint"] = f"PJSIP/vobiz-out/sip:{clean_number}@31868684.sip.vobiz.ai"
                
        if old_endpoint != query_params["endpoint"]:
            logger.info(f"[ARI Interceptor] Rewrote cloud dial string: {old_endpoint} -> {query_params['endpoint']}")
            
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    
    url = f"{ASTERISK_ARI_URL}/channels"
    logger.info(f"[ARI REST Proxy] Forwarding to Asterisk: POST {url}")
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            url,
            params=query_params,
            headers=headers,
            content=body,
            timeout=30.0
        )
        
    logger.info(f"[ARI REST Proxy] Asterisk responded with status: {response.status_code}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )

@app.delete("/ari/channels/{channel_id}")
async def proxy_ari_hangup(request: Request, channel_id: str):
    logger.info(f"[ARI REST Proxy] Received hangup request for channel: {channel_id}")
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    
    url = f"{ASTERISK_ARI_URL}/channels/{channel_id}"
    logger.info(f"[ARI REST Proxy] Forwarding to Asterisk: DELETE {url}")
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            timeout=30.0
        )
        
    logger.info(f"[ARI REST Proxy] Asterisk responded with status: {response.status_code}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )

@app.post("/ari/channels/externalMedia")
async def proxy_ari_external_media(request: Request):
    logger.info("[ARI REST Proxy] Intercepted externalMedia request")
    query_params = dict(request.query_params)
    logger.info(f"[ARI REST Proxy] Original query params: {query_params}")
    
    # Transparently rewrite external_host to 'dograh' (local WebSocket client mapping)
    if "external_host" in query_params:
        old_host = query_params["external_host"]
        query_params["external_host"] = "dograh"
        logger.info(f"[ARI Interceptor] Rewrote external_host: {old_host} -> {query_params['external_host']}")
        
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    
    url = f"{ASTERISK_ARI_URL}/channels/externalMedia"
    logger.info(f"[ARI REST Proxy] Forwarding to Asterisk: POST {url}")
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            url,
            params=query_params,
            headers=headers,
            content=body,
            timeout=30.0
        )
        
    logger.info(f"[ARI REST Proxy] Asterisk responded with status: {response.status_code}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )

@app.api_route("/ari/{path:path}", methods=["GET", "POST", "DELETE", "PUT"])
async def proxy_ari_rest(request: Request, path: str):
    logger.info(f"[ARI REST Proxy] Catch-all received request: {request.method} /ari/{path}")
    query_params = dict(request.query_params)
    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    
    url = f"{ASTERISK_ARI_URL}/{path}"
    logger.info(f"[ARI REST Proxy] Forwarding catch-all to Asterisk: {method} {url}")
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method,
            url,
            params=query_params,
            headers=headers,
            content=body,
            timeout=30.0
        )
        
    logger.info(f"[ARI REST Proxy] Asterisk catch-all responded with status: {response.status_code}")
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )

@app.websocket("/ari/events")
async def proxy_ari_websocket(websocket: WebSocket):
    logger.info("[ARI WebSocket Proxy] Incoming WebSocket handshake request")
    await websocket.accept()
    query_params = dict(websocket.query_params)
    logger.info(f"[ARI WebSocket Proxy] Accepted. Query params: {query_params}")
    query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
    asterisk_ws_url = f"{ASTERISK_ARI_WS}/events?{query_string}"
    
    logger.info(f"[ARI WebSocket Proxy] Proxying cloud WebSocket connection to Asterisk: {asterisk_ws_url}")
    
    session = aiohttp.ClientSession()
    try:
        async with session.ws_connect(asterisk_ws_url) as asterisk_ws:
            async def client_to_asterisk():
                try:
                    while True:
                        data = await websocket.receive()
                        if "text" in data:
                            await asterisk_ws.send_str(data["text"])
                        elif "bytes" in data:
                            await asterisk_ws.send_bytes(data["bytes"])
                except WebSocketDisconnect:
                    logger.info("[ARI WebSocket Proxy] Cloud client disconnected")
                except Exception as e:
                    logger.warning(f"[ARI WebSocket Proxy] Client read error: {e}")

            async def asterisk_to_client():
                try:
                    async for msg in asterisk_ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(msg.data)
                except Exception as e:
                    logger.warning(f"[ARI WebSocket Proxy] Asterisk read error: {e}")

            await asyncio.gather(
                client_to_asterisk(),
                asterisk_to_client()
            )
    except Exception as e:
        logger.error(f"[ARI WebSocket Proxy] Connection failed: {e}")
    finally:
        await session.close()
