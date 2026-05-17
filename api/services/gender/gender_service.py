"""
Gender prediction service with local model and GenderAPI fallback.
Internal service for use within Dograh platform.
"""

import json
import os
import time
from pathlib import Path
from typing import Literal, Optional

import httpx
import redis.asyncio as aioredis
from loguru import logger
from pydantic import BaseModel, Field

from api.constants import REDIS_URL
from api.services.gender.constants import (
    CONFIDENCE_THRESHOLD,
    REDIS_CACHE_TTL,
    REDIS_KEY_PREFIX,
)


class GenderPrediction(BaseModel):
    """Gender prediction result."""

    gender: Literal["male", "female", "unknown"] = Field(
        ..., description="Predicted gender"
    )
    confidence: float = Field(..., ge=0, le=1, description="Confidence score (0-1)")
    source: Literal["model", "genderapi"] = Field(
        ..., description="Source of prediction"
    )


class GenderService:
    """
    Internal service for predicting gender from names.
    Uses local SSA-based model with GenderAPI fallback.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        gender_api_key: Optional[str] = None,
        gender_api_url: str = "https://gender-api.com/v2/gender",
    ):
        """
        Initialize the gender service.

        Args:
            model_path: Path to the model file (default: ./model.txt)
            confidence_threshold: Minimum confidence to use local model
            gender_api_key: API key for GenderAPI (falls back to env var)
            gender_api_url: GenderAPI endpoint URL
        """
        self.confidence_threshold = confidence_threshold
        self.gender_api_key = gender_api_key or os.getenv("GENDERAPI_API_KEY")
        self.gender_api_url = gender_api_url

        # Load model
        if model_path is None:
            model_path = Path(__file__).parent / "model.txt"
        else:
            model_path = Path(model_path)

        self.model = self._load_model(model_path)
        self._http_client = None
        self._redis_client: Optional[aioredis.Redis] = None

    def _load_model(self, model_path: Path) -> dict:
        """Load the compressed gender prediction model."""
        if not model_path.exists():
            logger.warning(f"Warning: Model file not found at {model_path}")
            return {"metadata": {}, "names": {}}

        try:
            with open(model_path, "r", encoding="utf-8") as f:
                model = json.load(f)

            # Validate model structure
            if "names" not in model or "metadata" not in model:
                raise ValueError("Invalid model format")

            logger.debug(
                f"Loaded gender prediction model with {model['metadata'].get('total_names', 0):,} names"
            )

            return model

        except Exception as e:
            logger.error(f"Error loading gender prediction model: {e}")
            return {"metadata": {}, "names": {}}

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for API calls."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=5),
            )
        return self._http_client

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis_client is None:
            self._redis_client = await aioredis.from_url(
                REDIS_URL, decode_responses=True
            )
        return self._redis_client

    async def predict(
        self, first_name: str, last_name: Optional[str] = None
    ) -> GenderPrediction:
        """
        Predict gender for a given name.

        Args:
            first_name: First name to predict gender for
            last_name: Last name (optional, not used in v1.0)

        Returns:
            GenderPrediction with gender, confidence, and source
        """
        if not first_name:
            return GenderPrediction(gender="unknown", confidence=0.0, source="model")

        # Normalize name for lookup
        normalized_name = first_name.lower().strip()

        # Step 1: Check local model
        if normalized_name in self.model["names"]:
            male_count, female_count, confidence = self.model["names"][normalized_name]

            # Use local model if confidence meets threshold
            if confidence >= self.confidence_threshold:
                gender = "male" if male_count > female_count else "female"
                logger.debug(
                    f"GenderService: Local Prediction {first_name} - {gender} with confidence: {confidence}"
                )
                return GenderPrediction(
                    gender=gender, confidence=confidence, source="model"
                )
            else:
                logger.debug(
                    f"GenderService: Low Confidence Local Prediction {first_name} - with confidence: {confidence}"
                )

        # Step 2: Check Redis cache for previous API responses
        try:
            redis_client = await self._get_redis()
            cache_key = f"{REDIS_KEY_PREFIX}{normalized_name}"
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                cached_result = json.loads(cached_data)
                logger.debug(
                    f"GenderService: Redis Cache Hit {first_name} - {cached_result['gender']} with confidence: {cached_result['confidence']}"
                )
                return GenderPrediction(**cached_result, source="genderapi")
        except Exception as e:
            logger.warning(f"Redis cache check failed: {e}")

        # Step 3: Fallback to GenderAPI
        if self.gender_api_key:
            try:
                result = await self._call_gender_api(first_name)

                # Cache the result in Redis
                try:
                    redis_client = await self._get_redis()
                    cache_key = f"{REDIS_KEY_PREFIX}{normalized_name}"
                    cache_data = json.dumps(
                        {"gender": result.gender, "confidence": result.confidence}
                    )
                    await redis_client.setex(cache_key, REDIS_CACHE_TTL, cache_data)
                except Exception as e:
                    logger.warning(f"Failed to cache result in Redis: {e}")

                # No need for additional debug log here as _call_gender_api logs with timing
                return result
            except Exception as e:
                # Error already logged in _call_gender_api with timing
                pass

        # Step 4: Return best guess from model or unknown
        if normalized_name in self.model["names"]:
            male_count, female_count, confidence = self.model["names"][normalized_name]
            gender = "male" if male_count > female_count else "female"
            return GenderPrediction(
                gender=gender, confidence=confidence, source="model"
            )

        # Final fallback: unknown
        return GenderPrediction(gender="unknown", confidence=0.0, source="model")

    async def _call_gender_api(self, first_name: str) -> GenderPrediction:
        """
        Call GenderAPI for gender prediction.

        Args:
            first_name: First name to predict

        Returns:
            GenderPrediction from API response
        """
        headers = {
            "Authorization": f"Bearer {self.gender_api_key}",
            "Content-Type": "application/json",
        }

        payload = {"first_name": first_name}

        try:
            # Track API call timing
            start_time = time.perf_counter()

            response = await self.http_client.post(
                self.gender_api_url, headers=headers, json=payload
            )
            response.raise_for_status()

            # Calculate elapsed time
            elapsed_time = (
                time.perf_counter() - start_time
            ) * 1000  # Convert to milliseconds

            data = response.json()

            # Map GenderAPI response format
            gender = data.get("gender", "unknown").lower()
            if gender not in ["male", "female"]:
                gender = "unknown"

            # GenderAPI returns accuracy as probability
            confidence = data.get("probability", 0)

            # Log the API call with timing
            logger.info(
                f"GenderAPI call for '{first_name}': {gender} with confidence {confidence:.2f} "
                f"(took {elapsed_time:.2f}ms)"
            )

            return GenderPrediction(
                gender=gender, confidence=confidence, source="genderapi"
            )

        except httpx.HTTPStatusError as e:
            # Log error with timing if we got a response
            elapsed_time = (
                (time.perf_counter() - start_time) * 1000
                if "start_time" in locals()
                else 0
            )
            logger.error(
                f"GenderAPI HTTP error for '{first_name}': {e.response.status_code} "
                f"(took {elapsed_time:.2f}ms)"
            )

            if e.response.status_code == 401:
                raise ValueError("Invalid GenderAPI key")
            elif e.response.status_code == 429:
                raise ValueError("GenderAPI rate limit exceeded")
            else:
                raise ValueError(f"GenderAPI HTTP error: {e.response.status_code}")

        except httpx.TimeoutException as e:
            elapsed_time = (
                (time.perf_counter() - start_time) * 1000
                if "start_time" in locals()
                else 0
            )
            logger.error(
                f"GenderAPI timeout for '{first_name}' after {elapsed_time:.2f}ms"
            )
            raise ValueError(f"GenderAPI request timed out")

        except Exception as e:
            elapsed_time = (
                (time.perf_counter() - start_time) * 1000
                if "start_time" in locals()
                else 0
            )
            logger.error(
                f"GenderAPI unexpected error for '{first_name}': {str(e)} "
                f"(took {elapsed_time:.2f}ms)"
            )
            raise

    async def get_salutation(
        self,
        first_name: str,
        last_name: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
    ) -> str:
        """
        Get appropriate salutation based on gender prediction.

        Args:
            first_name: First name to predict gender for
            last_name: Last name (optional, not used in v1.0)
            confidence_threshold: Optional override for confidence threshold

        Returns:
            "Mr." for male, "Ms." for female, "Dear" for unknown/low confidence
        """
        if not first_name:
            return "Dear"

        # Get gender prediction
        prediction = await self.predict(first_name, last_name)

        # Return salutation based on gender and confidence
        if prediction.gender == "unknown":
            return "Dear"
        elif prediction.gender == "male":
            return "Mr."
        else:  # female
            return "Ms."

    async def batch_predict(self, names: list[str]) -> list[GenderPrediction]:
        """
        Predict gender for multiple names.

        Args:
            names: List of first names

        Returns:
            List of GenderPrediction results
        """
        results = []
        for name in names:
            result = await self.predict(name)
            results.append(result)
        return results

    async def close(self):
        """Close HTTP and Redis clients and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._redis_client:
            await self._redis_client.close()
            self._redis_client = None

    async def get_stats(self) -> dict:
        """Get statistics about the service and model."""
        metadata = self.model.get("metadata", {})

        # Get Redis cache stats
        cache_stats = {}
        try:
            redis_client = await self._get_redis()
            # Count keys matching our prefix pattern
            keys = await redis_client.keys(f"{REDIS_KEY_PREFIX}*")
            cache_stats = {
                "cached_names": len(keys),
                "cache_type": "redis",
                "ttl_seconds": REDIS_CACHE_TTL,
            }
        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {e}")
            cache_stats = {"cached_names": 0, "cache_type": "redis", "error": str(e)}

        return {
            "model": {
                "version": self.model.get("version", "unknown"),
                "total_names": metadata.get("total_names", 0),
                "high_confidence_names": metadata.get("high_confidence_names", 0),
                "confidence_threshold": self.confidence_threshold,
                "build_date": metadata.get("build_date", "unknown"),
            },
            "cache": cache_stats,
            "api": {"enabled": bool(self.gender_api_key), "url": self.gender_api_url},
        }

    async def clear_cache(self):
        """Clear the Redis cache for gender predictions."""
        try:
            redis_client = await self._get_redis()
            keys = await redis_client.keys(f"{REDIS_KEY_PREFIX}*")
            if keys:
                await redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} entries from Redis cache")
            else:
                logger.debug("No cache entries to clear")
        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
