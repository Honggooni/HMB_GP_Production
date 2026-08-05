from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import HMBPromptLibrary as prompt
import HMBVideoPickerLibrary as picker

SEED = 20260728
PICKER_CASES = 20_000
PROMPT_CASES = 10_000


def _random_value(rng: random.Random, depth: int = 0) -> Any:
    scalars: tuple[Any, ...] = (
        None,
        True,
        False,
        0,
        1,
        -1,
        3.14,
        float("nan"),
        "",
        "x",
        "999999999",
        "not-a-number",
        "{}",
        "[]",
        "한글",
        "@video2",
    )
    branch = rng.randrange(8 if depth < 2 else 5)
    if branch < 5:
        return rng.choice(scalars)
    if branch == 5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(0, 6))]
    if branch == 6:
        keys = (
            "x",
            "video_slot",
            "markers",
            "hidden_paths",
            "matched_images",
            "color",
            "value",
            "right_section_heights",
        )
        return {
            rng.choice(keys): _random_value(rng, depth + 1)
            for _ in range(rng.randrange(0, 5))
        }
    return [_random_value(rng, depth + 1), _random_value(rng, depth + 1)]


def _exercise(
    rng: random.Random,
    count: int,
    normalize: Callable[[Dict[str, Any]], Dict[str, Any]],
    keys: Iterable[str],
) -> None:
    key_list = list(dict.fromkeys(keys))
    for case_number in range(1, count + 1):
        raw: Dict[str, Any] = {}
        for _ in range(rng.randrange(0, min(20, len(key_list)) + 1)):
            raw[rng.choice(key_list)] = _random_value(rng)
        normalized = normalize(raw)
        normalized_again = normalize(normalized)
        assert normalized == normalized_again, (
            f"Normalization is not idempotent at case {case_number}: "
            f"{raw!r}"
        )


def main() -> None:
    rng = random.Random(SEED)
    picker_keys = [
        *picker._default_widget_state().keys(),
        "pending_action",
        "pending_action_id",
        "viewport_panel_height",
        "right_section_heights",
        "ui_layout_version",
        "videos",
        "markers",
        "slot_assignments",
        "slot_visibility",
    ]
    prompt_keys = [
        *prompt._default_widget_state().keys(),
        "images",
        "videos",
        "text",
        "ui",
        "picker",
        "status",
    ]
    _exercise(rng, PICKER_CASES, picker._parse_state, picker_keys)
    _exercise(
        rng,
        PROMPT_CASES,
        lambda value: prompt._normalize_state(prompt._parse_state(value)),
        prompt_keys,
    )
    print(
        "HMB malformed-state normalization and idempotency property regression: "
        f"PASS ({PICKER_CASES} Picker + {PROMPT_CASES} Prompt cases; seed {SEED})"
    )


if __name__ == "__main__":
    main()
