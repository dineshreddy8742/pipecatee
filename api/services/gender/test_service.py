"""
Test script for the gender prediction service.
"""

import asyncio

from api.services.gender.gender_service import GenderService


async def test_local_model():
    """Test predictions using local model only."""
    print("\n" + "=" * 60)
    print("Testing Local Model Predictions")
    print("=" * 60)

    # Initialize service without API key (local model only)
    service = GenderService()

    # Test high-confidence names
    high_confidence_names = [
        "John",
        "Mary",
        "Michael",
        "Sarah",
        "Robert",
        "Lisa",
        "William",
        "Jennifer",
        "David",
        "Patricia",
    ]

    print("\nHigh-confidence predictions (should use local model):")
    print("-" * 50)
    for name in high_confidence_names:
        result = await service.predict(name)
        print(
            f"  {name:12} -> {result.gender:6} (conf: {result.confidence:.3f}, source: {result.source})"
        )

    # Test ambiguous names
    ambiguous_names = [
        "Taylor",
        "Jordan",
        "Casey",
        "Alex",
        "Morgan",
        "Blake",
        "Avery",
        "Riley",
        "Quinn",
        "Sage",
    ]

    print("\nAmbiguous names (lower confidence):")
    print("-" * 50)
    for name in ambiguous_names:
        result = await service.predict(name)
        status = "✓" if result.source == "model" and result.confidence >= 0.85 else "○"
        print(
            f"  {status} {name:12} -> {result.gender:6} (conf: {result.confidence:.3f}, source: {result.source})"
        )

    # Test unknown names
    unknown_names = ["Xyzabc", "Qwerty", "Abcdef"]

    print("\nUnknown names (not in dataset):")
    print("-" * 50)
    for name in unknown_names:
        result = await service.predict(name)
        print(
            f"  {name:12} -> {result.gender:7} (conf: {result.confidence:.3f}, source: {result.source})"
        )

    # Get service statistics
    stats = await service.get_stats()
    print("\nService Statistics:")
    print("-" * 50)
    print(f"  Model version: {stats['model']['version']}")
    print(f"  Total names: {stats['model']['total_names']:,}")
    print(f"  High confidence: {stats['model']['high_confidence_names']:,}")
    print(f"  Threshold: {stats['model']['confidence_threshold']}")
    print(f"  Cache type: {stats['cache'].get('cache_type', 'unknown')}")
    print(f"  Cached names: {stats['cache'].get('cached_names', 0)}")
    print(f"  API enabled: {stats['api']['enabled']}")

    await service.close()


async def test_with_api():
    """Test with GenderAPI integration (requires API key)."""
    print("\n" + "=" * 60)
    print("Testing with GenderAPI Integration")
    print("=" * 60)

    # Check if API key is available
    import os

    api_key = os.getenv("GENDER_API_KEY")

    if not api_key:
        print("\n⚠️  No GENDER_API_KEY found in environment")
        print("   Skipping API integration tests")
        print("   To test API fallback, set: export GENDER_API_KEY=your_key")
        return

    service = GenderService(gender_api_key=api_key)

    # Test names that might need API fallback
    test_names = [
        "Priya",  # Indian name, might not be in SSA data
        "Hiroshi",  # Japanese name
        "Giovanni",  # Italian name
        "Olga",  # Russian name
        "Chen",  # Chinese name
    ]

    print("\nInternational names (may use API fallback):")
    print("-" * 50)
    for name in test_names:
        result = await service.predict(name)
        print(
            f"  {name:12} -> {result.gender:6} (conf: {result.confidence:.3f}, source: {result.source})"
        )

    # Test batch prediction
    print("\nBatch prediction test:")
    print("-" * 50)
    batch_names = ["Alice", "Bob", "Charlie", "Diana", "Eve"]
    results = await service.batch_predict(batch_names)
    for name, result in zip(batch_names, results):
        print(f"  {name:12} -> {result.gender:6} (conf: {result.confidence:.3f})")

    await service.close()


async def test_salutation():
    """Test salutation generation."""
    print("\n" + "=" * 60)
    print("Testing Salutation Generation")
    print("=" * 60)

    service = GenderService()

    # Test high-confidence names
    test_cases = [
        ("John", "Mr."),
        ("Mary", "Ms."),
        ("Michael", "Mr."),
        ("Sarah", "Ms."),
        ("Robert", "Mr."),
        ("Jennifer", "Ms."),
    ]

    print("\nHigh-confidence salutations:")
    print("-" * 50)
    for name, expected in test_cases:
        salutation = await service.get_salutation(name)
        status = "✓" if salutation == expected else "✗"
        print(f"  {status} {name:12} -> {salutation:4} (expected: {expected})")

    # Test ambiguous/unknown names
    ambiguous_cases = [
        "Xyzabc",  # Unknown name
        "Qwerty",  # Unknown name
        "",  # Empty string
        "   ",  # Whitespace
        "123",  # Numbers
    ]

    print("\nUnknown/ambiguous names (should return 'Dear'):")
    print("-" * 50)
    for name in ambiguous_cases:
        salutation = await service.get_salutation(name)
        display_name = f"'{name}'" if name else "(empty)"
        status = "✓" if salutation == "Dear" else "✗"
        print(f"  {status} {display_name:12} -> {salutation}")

    # Test with custom confidence threshold
    print("\nCustom confidence threshold test:")
    print("-" * 50)
    # Taylor has confidence ~0.744, should be "Dear" with high threshold
    salutation_default = await service.get_salutation("Taylor")
    salutation_high = await service.get_salutation("Taylor", confidence_threshold=0.9)
    print(f"  Taylor (default threshold): {salutation_default}")
    print(f"  Taylor (0.9 threshold): {salutation_high}")

    await service.close()


async def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n" + "=" * 60)
    print("Testing Edge Cases")
    print("=" * 60)

    service = GenderService()

    # Test empty/invalid inputs
    edge_cases = [
        "",  # Empty string
        "   ",  # Whitespace
        "123",  # Numbers
        "John-Paul",  # Hyphenated
        "Mary Ann",  # Space in name
        "O'Brien",  # Apostrophe
        "José",  # Accented
    ]

    print("\nEdge case inputs:")
    print("-" * 50)
    for name in edge_cases:
        result = await service.predict(name)
        display_name = f"'{name}'" if name else "(empty)"
        print(
            f"  {display_name:12} -> {result.gender:7} (conf: {result.confidence:.3f})"
        )

    # Test case insensitivity
    print("\nCase insensitivity test:")
    print("-" * 50)
    case_variants = ["john", "JOHN", "John", "JoHn"]
    for name in case_variants:
        result = await service.predict(name)
        print(f"  {name:12} -> {result.gender:6} (conf: {result.confidence:.3f})")

    await service.close()


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Gender Prediction Service Test Suite")
    print("=" * 60)

    # Run tests
    await test_local_model()
    await test_salutation()
    await test_edge_cases()
    await test_with_api()

    print("\n" + "=" * 60)
    print("✓ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
