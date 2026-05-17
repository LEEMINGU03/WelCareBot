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
from flow_helpers import (
    parse_region as _parse_region,
    find_policy as _find_policy,
    format_policy_list as _format_policy_list,
)


class WelCareState(BaseModel):
    message: str = ""
    history: List[str] = []
    phase: str = "intake"          # intake | search | selection | eligibility | done
    conditions: dict[str, Any] = {}
    policies: List[dict] = []
    selected_policy: dict = {}
    result: str = ""
    lang: str = "ko"               # 응답 언어 코드 (ko, en, ja, zh, ...)


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
        city, district = _parse_region(region)
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

    def _expand_policy_search(
        self,
        search_region: str,
        scope_desc: str,
        scope_label: str,
        city: str,
    ) -> None:
        """추가 범위 검색 → 결과를 state.policies에 누적하고 응답 포맷팅."""
        result = PolicySearchCrew().crew().kickoff(inputs={
            "conditions": json.dumps(self.state.conditions, ensure_ascii=False),
            "search_region": search_region,
            "scope": scope_desc,
            "lang": self.state.lang,
        })
        try:
            data = _parse_json(result.raw)
            new_policies = data.get("policies", [])[:3]
            for p in new_policies:
                p["scope"] = scope_label
            self.state.policies.extend(new_policies)
        except Exception:
            pass
        self.state.result = _format_policy_list(self.state.policies, city)

    # ── Phase 3: 선택 (번호 또는 텍스트) ──────────────────────────
    @listen("selection")
    def handle_selection(self):
        msg = self.state.message.strip()
        region = self.state.conditions.get("region", "")
        city, _ = _parse_region(region)
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
            self._expand_policy_search(
                search_region=city,
                scope_desc=f"{city} 광역시/도 단위 정책만",
                scope_label=city,
                city=city,
            )
            return

        if is_national_req:
            self._expand_policy_search(
                search_region="전국",
                scope_desc="전국 중앙정부 정책만",
                scope_label="전국",
                city=city,
            )
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
            city, _ = _parse_region(region)
            self.state.result = (
                f"😔 **아쉽게도 해당 정책은 신청이 어렵습니다.**\n\n"
                f"{reason}\n\n---\n\n"
                f"다른 정책을 확인해볼까요?\n\n"
                + _format_policy_list(self.state.policies, city)
            )
            self.state.phase = "selection"

        else:
            self.state.result = data.get("message", "")
