from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATOR_NEUTRAL_LIBRARIES = (
    ROOT / "HMBImageAssetLibrary.py",
    ROOT / "HMBVideoPickerLibrary.py",
    ROOT / "HMBPromptLibrary.py",
    ROOT / "HMBAgentLibrary.py",
)

# The four source/contract libraries must remain usable by any compatible
# generator. Provider/model vocabulary belongs only in its generator module.
FORBIDDEN_GENERATOR_SPECIFIC_TOKENS = (
    "seedance",
    "시댄스",
    "doubao",
    "dreamina",
    "byteplus",
    "volcengine",
    "volcano engine",
)


def test_four_libraries_are_generator_neutral() -> None:
    for path in GENERATOR_NEUTRAL_LIBRARIES:
        text = path.read_text(encoding="utf-8").casefold()
        found = [
            token
            for token in FORBIDDEN_GENERATOR_SPECIFIC_TOKENS
            if token.casefold() in text
        ]
        assert not found, f"{path.name} contains generator-specific terms: {found}"


if __name__ == "__main__":
    test_four_libraries_are_generator_neutral()
    print("HMB four-library generator-neutrality regression: PASS")
