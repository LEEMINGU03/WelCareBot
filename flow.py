import json
import re
from typing import Any, List
from pydantic import BaseModel
from crewai.flow.flow import Flow, listen, start, router

from crewai_tools import ScrapeWebsiteTool
from crews.intake_crew import IntakeCrew
from crews.policy_crew import PolicySearchCrew
from crews.eligibility_crew import EligibilityCrew
from utils import parse_json as _parse_json


class WelCareState(BaseModel):
    message: str = ""
    history: List[str] = []
    phase: str = "intake"          # intake | search | selection | eligibility | done
    conditions: dict[str, Any] = {}
    policies: List[dict] = []
    selected_policy: dict = {}
    result: str = ""
    lang: str = "ko"               # 응답 언어 코드 (ko, en, ja, zh, ...)



def _find_policy(message: str, policies: list[dict]) -> dict | None:
    """번호(숫자/한국어) 또는 이름 텍스트로 정책 매칭."""
    msg = message.strip()

    # 숫자 직접 입력: "1", "2", ...
    if msg.isdigit():
        idx = int(msg) - 1
        if 0 <= idx < len(policies):
            return policies[idx]

    # 한국어 수 표현
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

    # 정책명 포함 검색
    msg_lower = msg.lower()
    for policy in policies:
        name = policy.get("name", "").lower()
        if name and (name in msg_lower or msg_lower in name):
            return policy

    # 단어 단위 부분 매칭
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


class WelCareFlow(Flow[WelCareState]):

    @start()
    def dispatch(self):
        pass

    @router(dispatch)
    def route_phase(self):
        return self.state.phase

    # ── Phase 1: Intake (3가지 기본 정보 수집) ──────────────────
    @listen("intake")
    def run_intake(self):
        intake_result = IntakeCrew().crew().kickoff(inputs={
            "message": self.state.message,
            "history": "\n".join(self.state.history) if self.state.history else "없음",
            "lang": self.state.lang,
        })
        try:
            data = _parse_json(intake_result.raw)
        except Exception:
            data = {"status": "INCOMPLETE", "follow_up_question": str(intake_result.raw)}

        if data.get("status", "").upper() == "COMPLETE":
            raw = data.get("conditions")
            self.state.conditions = raw if isinstance(raw, dict) else {}
            self.state.phase = "search"
        else:
            self.state.result = data.get("follow_up_question", "조금 더 알려주실 수 있을까요?")

    @router(run_intake)
    def after_intake(self):
        return "do_search" if self.state.phase == "search" else "end_turn"

    # ── Phase 2: 검색 → 3~5개 목록 제시 ─────────────────────────
    @listen("do_search")
    def search_and_present(self):
        region = self.state.conditions.get("region", "")
        parts = region.strip().split()
        district = parts[-1] if len(parts) >= 2 else region
        city = parts[0] if len(parts) >= 2 else ""
        scope_desc = f"{district} 단위 기초자치단체 정책만" if city else f"{region} 단위 정책만"

        policy_result = PolicySearchCrew().crew().kickoff(inputs={
            "conditions": json.dumps(self.state.conditions, ensure_ascii=False),
            "search_region": region,
            "scope": scope_desc,
            "lang": self.state.lang,
        })
        try:
            cleaned = re.sub(r"```(?:json)?\s*", "", policy_result.raw).replace("```", "").strip()
            data = _parse_json(cleaned)
            policies = data.get("policies", [])[:3]
            for p in policies:
                p["scope"] = district
            self.state.policies = policies
        except Exception:
            self.state.policies = []

        if not self.state.policies:
            self.state.result = "죄송해요, 조건에 맞는 정책을 찾지 못했어요. 다시 말씀해주세요."
            self.state.phase = "intake"
            return

        self.state.result = _format_policy_list(self.state.policies, city)
        self.state.phase = "selection"

    # ── Phase 3: 선택 (번호 또는 텍스트) ──────────────────────────
    @listen("selection")
    def handle_selection(self):
        msg = self.state.message.strip()
        region = self.state.conditions.get("region", "")
        parts = region.strip().split()
        city = parts[0] if len(parts) >= 2 else ""
        existing_scopes = {p.get("scope", "") for p in self.state.policies}

        # A: 시/도 전체 정책 요청
        is_city_req = (
            city and city not in existing_scopes and
            (msg.upper() in ("A", "A.") or city in msg or "시 전체" in msg)
        )
        # B: 전국 정책 요청
        is_national_req = (
            "전국" not in existing_scopes and
            (msg.upper() in ("B", "B.") or msg == "전국")
        )

        if is_city_req:
            result = PolicySearchCrew().crew().kickoff(inputs={
                "conditions": json.dumps(self.state.conditions, ensure_ascii=False),
                "search_region": city,
                "scope": f"{city} 광역시/도 단위 정책만",
                "lang": self.state.lang,
            })
            try:
                data = _parse_json(result.raw)
                new_policies = data.get("policies", [])[:3]
                for p in new_policies:
                    p["scope"] = city
                self.state.policies.extend(new_policies)
            except Exception:
                pass
            self.state.result = _format_policy_list(self.state.policies, city)
            return

        if is_national_req:
            result = PolicySearchCrew().crew().kickoff(inputs={
                "conditions": json.dumps(self.state.conditions, ensure_ascii=False),
                "search_region": "전국",
                "scope": "전국 중앙정부 정책만",
                "lang": self.state.lang,
            })
            try:
                data = _parse_json(result.raw)
                new_policies = data.get("policies", [])[:3]
                for p in new_policies:
                    p["scope"] = "전국"
                self.state.policies.extend(new_policies)
            except Exception:
                pass
            self.state.result = _format_policy_list(self.state.policies, city)
            return

        policy = _find_policy(msg, self.state.policies)

        if policy is None:
            self.state.result = (
                "어떤 정책을 원하시는지 잘 모르겠어요. "
                "번호나 이름으로 다시 선택해주세요.\n\n"
                + _format_policy_list(self.state.policies, city)
            )
            return  # phase stays "selection"

        self.state.selected_policy = policy
        self.state.phase = "eligibility"

        # 선택된 정책 URL만 크롤링해서 상세 정보 보강
        url = policy.get("url", "")
        if url:
            try:
                detail = ScrapeWebsiteTool()._run(website_url=url)
                policy = {**policy, "detail": str(detail)[:3000]}
                self.state.selected_policy = policy
            except Exception:
                pass

        # 선택 확인 + 첫 번째 자격 질문을 같은 turn에 제공
        elig_result = EligibilityCrew().crew().kickoff(inputs={
            "policy_json": json.dumps(policy, ensure_ascii=False),
            "history": "없음",
            "message": "시작해주세요",
            "lang": self.state.lang,
        })
        try:
            data = _parse_json(elig_result.raw)
            first_question = data.get("message", "자격 조건을 확인해볼게요!")
        except Exception:
            first_question = str(elig_result.raw)

        self.state.result = (
            f"**{policy.get('name', '')}**를 선택하셨군요! "
            f"자격 조건을 함께 확인해볼게요.\n\n"
            f"{first_question}"
        )

    # ── Phase 4: 자격 확인 대화 ───────────────────────────────────
    @listen("eligibility")
    def check_eligibility(self):
        elig_result = EligibilityCrew().crew().kickoff(inputs={
            "policy_json": json.dumps(self.state.selected_policy, ensure_ascii=False),
            "history": "\n".join(self.state.history) if self.state.history else "없음",
            "message": self.state.message,
            "lang": self.state.lang,
        })
        try:
            data = _parse_json(elig_result.raw)
        except Exception:
            data = {"status": "INCOMPLETE", "message": str(elig_result.raw)}

        status = data.get("status", "INCOMPLETE").upper()

        if status == "ELIGIBLE":
            p = self.state.selected_policy
            self.state.result = (
                f"✅ **신청 가능합니다!**\n\n"
                f"**{p.get('name', '')}**\n\n"
                f"**신청 방법:** {p.get('how_to_apply', '')}\n\n"
                f"**마감일:** {p.get('deadline', '상시 접수')}\n\n"
                f"[더 알아보기 →]({p.get('url', '')})"
            )
            self.state.phase = "done"

        elif status == "NOT_ELIGIBLE" or status == "NOT ELIGIBLE":
            reason = data.get("reason", "")
            region = self.state.conditions.get("region", "")
            city = (region.strip().split() + [""])[0] if len(region.strip().split()) >= 2 else ""
            self.state.result = (
                f"😔 **아쉽게도 해당 정책은 신청이 어렵습니다.**\n\n"
                f"{reason}\n\n---\n\n"
                f"다른 정책을 확인해볼까요?\n\n"
                + _format_policy_list(self.state.policies, city)
            )
            self.state.phase = "selection"

        else:
            self.state.result = data.get("message", "")
