"""
TTS (Text-to-Speech) pricing models for different providers.

Prices are per character for TTS services.
"""

from decimal import Decimal
from typing import Dict

from api.services.configuration.registry import ServiceProviders

from .models import CharacterPricingModel

# TTS pricing registry
TTS_PRICING: Dict[str, Dict[str, CharacterPricingModel]] = {
    ServiceProviders.OPENAI: {
        "gpt-4o-mini-tts": CharacterPricingModel(Decimal("0.6") / 1_00_00_000),
        "default": CharacterPricingModel(Decimal("0.6") / 1_00_00_000),
    },
    ServiceProviders.DEEPGRAM: {
        "aura-2": CharacterPricingModel(Decimal("0.030") / 1_000),
        "aura-1": CharacterPricingModel(Decimal("0.015") / 1_000),
        "default": CharacterPricingModel(Decimal("0.030") / 1_000),
    },
    ServiceProviders.ELEVENLABS: {
        # 6400 usd per 250*1e6 characters
        "default": CharacterPricingModel(Decimal("0.0256") / 1_000)
    },
    "default": {"default": CharacterPricingModel(Decimal("0.030") / 1_000)},
}
