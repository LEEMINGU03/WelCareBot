import json
import re
from typing import Any


def parse_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    candidates: list[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(cleaned[start : i + 1])
                start = -1

    for candidate in reversed(candidates):
        for text in (candidate, candidate.replace("{{", "{").replace("}}", "}")):
            try:
                result = json.loads(text)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

    raise json.JSONDecodeError("No valid JSON dict found", cleaned, 0)
