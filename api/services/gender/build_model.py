"""
Build gender prediction model from SSA baby names data.
Generates a compressed JSON model file.
"""

import json
from collections import defaultdict
from datetime import datetime
from math import log10
from pathlib import Path

from api.services.gender.constants import CONFIDENCE_THRESHOLD


def calculate_confidence(male_count: int, female_count: int) -> float:
    """Calculate confidence score for gender prediction."""
    total = male_count + female_count

    # Minimum sample size requirement
    if total < 100:
        return 0.0

    # Calculate gender ratio
    ratio = max(male_count, female_count) / total

    # Apply logarithmic scaling for sample size
    # Max confidence at 100,000 occurrences
    sample_weight = min(1.0, log10(total) / 5)

    # Final confidence
    return round(ratio * sample_weight, 4)


def build_model():
    """Build gender prediction model from SSA data."""
    # Initialize counters
    name_stats = defaultdict(lambda: {"M": 0, "F": 0})

    # Get the path to names directory
    names_dir = Path(__file__).parent / "names"

    if not names_dir.exists():
        raise FileNotFoundError(f"Names directory not found: {names_dir}")

    file_count = 0
    # Process all year files
    for year_file in sorted(names_dir.glob("yob*.txt")):
        file_count += 1
        with open(year_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split(",")
                if len(parts) != 3:
                    continue

                name, gender, count = parts
                name = name.lower()
                count = int(count)

                # Simple aggregation - no year weighting
                name_stats[name][gender] += count

    print(f"Processed {file_count} year files")

    # Build compressed model format
    names_data = {}
    high_confidence_count = 0

    for name, stats in name_stats.items():
        male_count = stats["M"]
        female_count = stats["F"]

        if male_count == 0 and female_count == 0:
            continue

        # Calculate confidence
        confidence = calculate_confidence(male_count, female_count)

        # Store as compact array: [male_count, female_count, confidence]
        names_data[name] = [male_count, female_count, confidence]

        if confidence >= CONFIDENCE_THRESHOLD:
            high_confidence_count += 1

    # Create final model structure with metadata
    model = {
        "version": "1.0",
        "metadata": {
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "total_names": len(names_data),
            "high_confidence_names": high_confidence_count,
            "build_date": datetime.now().isoformat(),
            "source_files": file_count,
        },
        "names": names_data,
    }

    return model


def save_model(model, output_path="model.txt"):
    """Save model to compressed JSON file."""
    output_file = Path(__file__).parent / output_path

    # Write compressed JSON (no indentation for smaller size)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(model, f, separators=(",", ":"))

    # Calculate file size
    file_size_mb = output_file.stat().st_size / (1024 * 1024)

    print(f"\nModel saved to: {output_file}")
    print(f"File size: {file_size_mb:.2f} MB")
    print(f"\nModel statistics:")
    print(f"  Total names: {model['metadata']['total_names']:,}")
    print(
        f"  High confidence names (≥{CONFIDENCE_THRESHOLD}): {model['metadata']['high_confidence_names']:,}"
    )
    print(
        f"  Confidence percentage: {model['metadata']['high_confidence_names'] / model['metadata']['total_names'] * 100:.1f}%"
    )


def test_model(model):
    """Test model with sample names."""
    print("\nSample predictions:")
    test_names = [
        "john",
        "mary",
        "alex",
        "taylor",
        "michael",
        "sarah",
        "jordan",
        "casey",
    ]

    for name in test_names:
        if name in model["names"]:
            male_count, female_count, confidence = model["names"][name]
            gender = "male" if male_count > female_count else "female"
            print(
                f"  {name.capitalize():10} -> {gender:6} (confidence: {confidence:.3f}, M:{male_count:,} F:{female_count:,})"
            )
        else:
            print(f"  {name.capitalize():10} -> not found in dataset")


if __name__ == "__main__":
    print("Building gender prediction model from SSA data...")
    print("=" * 50)

    try:
        model = build_model()
        save_model(model)
        test_model(model)
        print("\n✓ Model build complete!")

    except Exception as e:
        print(f"\n✗ Error building model: {e}")
        raise
