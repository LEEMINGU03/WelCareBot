import json
import re
from typing import Any


def _parse_json(raw: str) -> dict[str, Any]:
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


def _find_policy(message: str, policies: list[dict]) -> dict | None:
    """번호(숫자/한국어) 또는 이름 텍스트로 정책 매칭."""
    msg = message.strip()

    if msg.isdigit():
        idx = int(msg) - 1
        if 0 <= idx < len(policies):
            return policies[idx]

    kr_nums = {
        "첫 번째": 0, "하나": 0, "1번": 0,
        "두 번째": 1, "둘": 1, "2번": 1,
        "세 번째": 2, "셋": 2, "3번": 2,
        "네 번째": 3, "넷": 3, "4번": 3,
        "다섯 번째": 4, "다섯": 4, "5번": 4,
    }
    for word, idx in kr_nums.items():
        if word in msg and idx < len(policies):
            return policies[idx]

    msg_lower = msg.lower()
    for policy in policies:
        name = policy.get("name", "").lower()
        if name and (name in msg_lower or msg_lower in name):
            return policy

    for policy in policies:
        words = [w for w in policy.get("name", "").split() if len(w) > 1]
        if any(w in msg for w in words):
            return policy

    return None


def _format_policy_list(policies: list[dict], city: str = "") -> str:
    lines = [
        "아래 복지 정책을 찾았어요!",
        "**번호** 또는 **이름**으로 더 알고 싶은 항목을 선택해주세요.\n",
    ]

    has_scope = any("scope" in p for p in policies)

    if has_scope:
        scope_order: list[str] = []
        scope_groups: dict[str, list] = {}
        for p in policies:
            s = p.get("scope", "기타")
            if s not in scope_groups:
                scope_order.append(s)
                scope_groups[s] = []
            scope_groups[s].append(p)

        icon_map: dict[str, str] = {"전국": "🇰🇷"}
        non_national = [s for s in scope_order if s != "전국"]
        for i, s in enumerate(non_national):
            icon_map[s] = ("📍" if i == 0 else "🏙️")

        counter = 1
        for scope in scope_order:
            lines.append(f"\n{icon_map.get(scope, '📌')} **{scope} 정책**\n")
            for p in scope_groups[scope]:
                benefit = p.get("benefit", "")
                preview = benefit[:60] + ("..." if len(benefit) > 60 else "")
                lines.append(f"**{counter}. {p.get('name', '')}**")
                lines.append(f"   {preview}")
                lines.append("")
                counter += 1
    else:
        for i, p in enumerate(policies, 1):
            benefit = p.get("benefit", "")
            preview = benefit[:60] + ("..." if len(benefit) > 60 else "")
            lines.append(f"**{i}. {p.get('name', '')}**")
            lines.append(f"   {preview}")
            lines.append("")

    lines.append('예) `2` 또는 `청년 월세 지원`')

    existing_scopes = {p.get("scope", "") for p in policies}
    show_city = bool(city and city not in existing_scopes)
    show_national = "전국" not in existing_scopes

    if show_city or show_national:
        lines.append("\n──────────────────────")
        lines.append("다른 범위에서도 찾아드릴까요?")
        if show_city:
            lines.append(f"A. {city} 전체 정책 찾기")
        if show_national:
            lines.append("B. 전국 정책 찾기")

    return "\n".join(lines)
