# WelCare — 복지 정책 매칭 챗봇

CrewAI Flow 기반의 4-Phase 복지 정책 안내 시스템입니다.
사용자와 대화로 조건을 수집하고, 실시간 웹 검색으로 정책 목록을 제시한 뒤, 선택한 정책의 자격 조건을 단계별로 확인합니다.

---

## 아키텍처

```
사용자 입력
    │
    ▼
┌────────────────────────────────────────────────┐
│  WelCareFlow  (flow.py)                        │
│                                                │
│  @start   dispatch()                           │
│      │                                         │
│  @router  route_phase()   ← phase 값으로 분기  │
│      │                                         │
│  "intake"      run_intake()      ← IntakeCrew  │
│      │                                         │
│  @router  after_intake()                       │
│      │               │                         │
│  end_turn      "do_search"                     │
│  (역질문 반환)       │                         │
│            search_and_present() ← PolicySearchCrew │
│                      │                         │
│               "selection"                      │
│            handle_selection()                  │
│            (번호/이름으로 정책 선택)            │
│                      │                         │
│               "eligibility"                    │
│            check_eligibility() ← EligibilityCrew  │
│            (자격 조건 1개씩 확인)               │
│                      │                         │
│                   "done"                       │
│            신청 방법 + URL 안내                 │
└────────────────────────────────────────────────┘
```

---

## 상태 (WelCareState)

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | str | 사용자 최근 메시지 |
| `history` | List[str] | 대화 이력 |
| `phase` | str | 현재 단계 (`intake` \| `search` \| `selection` \| `eligibility` \| `done`) |
| `conditions` | dict | 수집된 복지 검색 조건 |
| `policies` | List[dict] | 검색된 정책 목록 |
| `selected_policy` | dict | 사용자가 선택한 정책 |
| `result` | str | 사용자에게 반환할 응답 텍스트 |
| `lang` | str | 응답 언어 코드 (기본값: `"ko"`) |

---

## 에이전트

### 1. `intake_agent` — 복지 정보 수집 전문가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/intake_crew.py` |
| **역할** | 대분류→소분류→지역→나이 순으로 4단계 수집 |
| **도구** | 없음 (대화 전용) |
| **LLM** | `gemini/gemini-2.5-flash` |

**수집 단계**
1. **대분류** — 주거 / 취업·일자리 / 의료·건강 / 교육 / 생계·소득 / 육아·가족 / 노인 / 장애인 / 청년
2. **소분류** — 대분류에 해당하는 세부 항목 (자유 텍스트 입력도 허용)
3. **지역 & 나이** — 한 번에 수집

**출력 형식 (JSON)**
```json
{
  "status": "INCOMPLETE | COMPLETE",
  "follow_up_question": "다음 질문 (INCOMPLETE일 때만)",
  "conditions": {
    "welfare_type_major": "대분류",
    "welfare_type_minor": "소분류",
    "region": "거주 지역",
    "age": "나이"
  }
}
```

---

### 2. `eligibility_agent` — 복지 자격 확인 전문가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/eligibility_crew.py` |
| **역할** | 선택된 정책의 자격 조건을 1개씩 대화로 확인 |
| **도구** | 없음 (대화 전용) |
| **LLM** | `gemini/gemini-2.5-flash` |

**출력 형식 (JSON)**
```json
{
  "status": "ELIGIBLE(신청가능) | NOT_ELIGIBLE(신청 불가) | INCOMPLETE(심사 중)",
  "message": "다음 질문 또는 확인 메시지",
  "reason": "판단 이유 (ELIGIBLE/NOT_ELIGIBLE일 때)"
}
```

---

### 3. `policy_researcher_agent` — 복지 정책 검색 전문가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/policy_crew.py` |
| **역할** | 수집된 조건으로 실시간 웹 검색 후 맞춤 정책 최대 3개 제공 |
| **도구** | `SerperDevTool` (웹 검색) |
| **LLM** | `gemini/gemini-2.5-flash` |

검색 범위는 **구/군(기초자치단체) → 시/도 → 전국** 순으로 확장 가능하며, 사용자가 목록에서 A/B 버튼으로 범위를 넓힐 수 있습니다.
선택된 정책의 URL은 `flow.py`에서 `ScrapeWebsiteTool`로 직접 크롤링하여 상세 정보를 보강합니다.

**출력 형식 (JSON)**
```json
{
  "status": "SUCCESS",
  "policies": [
    {
      "name": "정책명",
      "benefit": "혜택 내용",
      "eligibility": "수혜 자격",
      "how_to_apply": "신청 방법",
      "deadline": "마감일",
      "url": "URL (없으면 빈 문자열)"
    }
  ]
}
```

---

### 4. `translator_agent` — 쉬운 말 번역가 *(현재 미사용)*

행정 용어를 쉬운 우리말로 순화하는 에이전트입니다. `config/agents.yaml`과 `crews/translator_crew.py`에 정의되어 있으나 현재 Flow에서는 사용되지 않습니다.

---

## Flow 실행 흐름

```
flow.kickoff(inputs)
    │
    ├─ @start      dispatch()            # 진입점 (아무 동작 없음)
    │
    ├─ @router     route_phase()         # state.phase 값으로 분기
    │
    ├─ "intake"    run_intake()          # IntakeCrew 실행
    │                  │
    │              after_intake()        # @router: "do_search" or "end_turn"
    │                  │
    ├─ "do_search" search_and_present()  # PolicySearchCrew → 정책 목록 제시
    │                  │                # state.phase = "selection"
    │
    ├─ "selection" handle_selection()   # 번호/이름으로 정책 선택
    │                  │                # A → 시/도 확장 검색
    │                  │                # B → 전국 확장 검색
    │                  │                # 선택 → URL 크롤링 + EligibilityCrew 첫 질문
    │                  │                # state.phase = "eligibility"
    │
    └─ "eligibility" check_eligibility() # EligibilityCrew 실행
                       │
              ELIGIBLE → 신청 안내 + state.phase = "done"
              NOT_ELIGIBLE → 다른 정책 목록으로 복귀 (state.phase = "selection")
              INCOMPLETE → 다음 자격 질문 반환
```

---

## 프로젝트 구조

```
WelCare/
├── crews/
│   ├── __init__.py
│   ├── intake_crew.py        # IntakeCrew       (intake_agent)
│   ├── eligibility_crew.py   # EligibilityCrew  (eligibility_agent)
│   ├── policy_crew.py        # PolicySearchCrew (policy_researcher_agent)
│   └── translator_crew.py    # TranslatorCrew   (미사용)
├── config/
│   ├── agents.yaml           # agent role / goal / backstory
│   └── tasks.yaml            # task description / expected_output
├── flow.py                   # WelCareFlow (Flow 오케스트레이션)
├── main.py                   # 진입점 + 터미널 대화 루프
├── utils.py                  # parse_json 유틸리티
├── env.py                    # 환경변수 로딩
└── .env                      # API 키 (git 제외)
```

---

## 환경 변수 (.env)

```
GEMINI_API_KEY=...
SERPER_API_KEY=...
```

---

## 실행

```bash
python main.py
# 또는 초기 메시지를 인자로 전달
python main.py 청년 주거 지원이 필요해요
```
