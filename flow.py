import json
import re
from typing import Any, List
from pydantic import BaseModel
from crewai.flow.flow import Flow, listen, start, router, or_

from crews.intake_crew import IntakeCrew
from crews.policy_crew import PolicySearchCrew
from crews.translator_crew import TranslatorCrew


class WelCareState(BaseModel):
    message: str = ""
    history: List[str] = []
    conditions: dict[str, Any] = {}
    follow_up: str = ""
    status: str = "INCOMPLETE"
    result: str = ""


def _parse_json(raw: str) -> dict[str, Any]:
    """코드 펜스·thinking 텍스트·이중 중괄호를 모두 처리해 JSON만 추출해 파싱."""
    # 1) 코드 펜스 제거
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    # 2) 앞뒤 thinking 텍스트 무시 — 첫 { 부터 마지막 } 까지만 추출
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    text = match.group() if match else cleaned
    # 3) 정상 파싱 먼저 시도
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 4) LLM이 Jinja2 이스케이프({{ }})를 그대로 출력한 경우 변환 후 재시도
    text = text.replace("{{", "{").replace("}}", "}")
    return json.loads(text)


class WelCareFlow(Flow[WelCareState]):

    @start()
    def run_intake(self):
        intake_result = IntakeCrew().crew().kickoff(inputs={
            "message": self.state.message,
            "history": "\n".join(self.state.history) if self.state.history else "없음",
        })

        data: dict[str, Any]
        try:
            data = _parse_json(intake_result.raw)
        except (json.JSONDecodeError, AttributeError, ValueError):
            data = {"status": "INCOMPLETE", "follow_up_question": str(intake_result.raw)}

        self.state.status = data.get("status", "INCOMPLETE")

        if self.state.status == "INCOMPLETE":
            self.state.follow_up = data.get("follow_up_question", "추가 정보가 필요합니다.")
        else:
            self.state.conditions = data.get("conditions", {})

    @router(run_intake)
    def check_status(self):
        if self.state.status == "COMPLETE":
            return "search_via_intake"
        return "ask_followup"

    @listen("ask_followup")
    def ask_user(self):
        self.state.result = self.state.follow_up

    # or_ : "search_via_intake" (일반 경로) 또는
    #        "direct_search"     (나중에 조건을 직접 주입하는 경로 확장용)
    @listen(or_("search_via_intake", "direct_search"))
    def search_policies(self):
        policy_result = PolicySearchCrew().crew().kickoff(inputs={
            "conditions": json.dumps(self.state.conditions, ensure_ascii=False),
        })
        # 코드 펜스 제거 후 저장 (translator가 받는 원문 정리)
        cleaned = re.sub(r"```(?:json)?\s*", "", policy_result.raw).replace("```", "").strip()
        self.state.result = cleaned

    @listen(search_policies)
    def translate_result(self):
        translated = TranslatorCrew().crew().kickoff(inputs={
            "policy_result": self.state.result,
        })
        self.state.result = translated.raw
