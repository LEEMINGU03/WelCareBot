"""
FastAPI 서버 - WelCare 챗봇 HTTP API

실행 방법:
    .venv/Scripts/uvicorn.exe api:app --reload

테스트 방법 (브라우저):
    http://localhost:8000/docs  ← 자동 생성된 API 문서 (Swagger UI)
"""

import env  # noqa: F401  — .env 파일 로드
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import Any

from main import run_agent, _fresh_state, _sync_state


# ── 앱 생성 ──────────────────────────────────────────────────────────────────
app = FastAPI(title="WelCare 복지 챗봇 API", version="1.0.0")

# 웹 프론트엔드(다른 포트)에서 호출 가능하도록 CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 요청/응답 스키마 ──────────────────────────────────────────────────────────

class ChatState(BaseModel):
    """클라이언트가 저장했다가 다음 요청에 다시 보내주는 대화 상태"""
    phase: str = "intake" ## 어느 대화 단계인지
    policies: list[dict] = [] ## 검색 결과로 나온 복지 정책 목록
    selected_policy: dict[str, Any] = {} ## 사용자가 목록에서 선택한 정책(1개)
    conditions: dict[str, Any] = {}  ## 사용자 개인 정보
    lang: str = "ko"  ## 응답 언어 코드 (ko, en, ja, zh ...)


class ChatRequest(BaseModel):
    """POST /chat 요청 바디"""
    message: str                        # 사용자가 입력한 메시지
    history: list[str] = []             # 지금까지의 대화 기록
    state: ChatState = ChatState()      # 현재 대화 상태

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message는 빈 문자열일 수 없습니다")
        return v.strip()


class ChatResponse(BaseModel):
    """POST /chat 응답 바디"""
    reply: str                          # 봇의 응답 텍스트
    history: list[str]                  # 업데이트된 대화 기록
    state: ChatState                    # 업데이트된 대화 상태


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """서버가 살아있는지 확인용 (헬스 체크)"""
    return {"status": "ok", "service": "WelCare 챗봇"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    챗봇과 대화하는 핵심 엔드포인트.

    - 클라이언트는 매 요청마다 history와 state를 함께 보내야 해요.
    - 서버는 봇 응답 + 새로운 history + 새로운 state를 돌려줍니다.
    """
    # 1. 요청에서 꺼낸 상태를 dict로 변환
    state_data = req.state.model_dump()
    history = list(req.history)

    # 2. 사용자 메시지를 history에 추가
    history.append(f"사용자: {req.message}")

    # 3. main.py의 run_agent를 그대로 호출
    try:
        flow = run_agent(req.message, history, state_data)
    except Exception as e:
        err = str(e).lower()
        # AI API 과부하 / 일시 불가 / 속도 제한 → 503
        if any(keyword in err for keyword in ("503", "overloaded", "unavailable", "rate limit", "429", "timeout")):
            raise HTTPException(status_code=503, detail="AI 서비스가 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요.")
        # 그 외 서버 내부 오류 → 500
        raise HTTPException(status_code=500, detail=f"챗봇 실행 중 오류가 발생했습니다: {str(e)}")

    # 4. 봇 응답을 history에 추가
    reply = flow.state.result
    history.append(f"봇: {reply}")

    # 5. state 동기화 (phase, policies 등 업데이트)
    _sync_state(state_data, flow)

    # 대화가 완전히 끝나면 state를 초기화
    if state_data["phase"] == "done":
        state_data = _fresh_state()
        history = []

    return ChatResponse(
        reply=reply,
        history=history,
        state=ChatState(**state_data),
    )
