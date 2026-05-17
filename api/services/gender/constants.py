"""
Hyperparameters and configuration for gender prediction service.
"""

# Confidence threshold for using local model predictions
CONFIDENCE_THRESHOLD = 0.85

# Redis cache configuration
REDIS_CACHE_TTL = 86400 * 30  # 30 days in seconds
REDIS_KEY_PREFIX = "genderservice:"
