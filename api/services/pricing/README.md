# Pricing Module

This module contains pricing models and registries for different AI services used in workflow cost calculations.

## Structure

```
pricing/
├── __init__.py           # Main module exports
├── models.py            # Base pricing model classes
├── llm.py              # LLM pricing configurations
├── tts.py              # TTS pricing configurations  
├── stt.py              # STT pricing configurations
├── registry.py         # Combined pricing registry
└── README.md           # This file
```

## Pricing Models

### TokenPricingModel
Used for LLM services that charge based on tokens:
- `prompt_token_price`: Cost per prompt token
- `completion_token_price`: Cost per completion token
- `cache_read_discount`: Discount for cache read tokens (default 50%)
- `cache_creation_multiplier`: Premium for cache creation tokens (default 25%)

### CharacterPricingModel
Used for TTS services that charge based on character count:
- `character_price`: Cost per character

### TimePricingModel
Used for STT services that charge based on time:
- `second_price`: Cost per second

## Adding New Pricing

### Adding a New LLM Model
Edit `llm.py` and add the model to the appropriate provider:

```python
ServiceProviders.OPENAI: {
    "new-model": TokenPricingModel(
        prompt_token_price=Decimal("2.00") / 1000000,
        completion_token_price=Decimal("8.00") / 1000000,
    ),
    # ... existing models
}
```

### Adding a New Provider
1. Add pricing configurations to the appropriate service file (llm.py, tts.py, stt.py)
2. The registry will automatically include them

### Adding a New Service Type
1. Create a new pricing file (e.g., `image.py`)
2. Define the pricing models
3. Import and add to `registry.py`

## Usage

The pricing registry is automatically imported and used by the cost calculator:

```python
from api.services.pricing import PRICING_REGISTRY
from api.services.workflow.cost_calculator import cost_calculator

# The cost calculator uses the pricing registry automatically
result = cost_calculator.calculate_total_cost(usage_info)
```

## Maintenance

- Update pricing when providers change their rates
- All prices should use `Decimal` for precision
- Include comments with current pricing from provider documentation
- Test changes with existing test suite 