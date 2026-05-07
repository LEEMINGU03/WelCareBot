# WelCare — 복지 정책 매칭 챗봇

CrewAI Flow 기반의 3-Agent 복지 정책 안내 시스템입니다.
사용자와 대화로 조건을 수집하고, 실시간 웹 검색으로 정책을 찾은 뒤, 행정 용어를 쉬운 말로 풀어서 전달합니다.

---

## 아키텍처

```
사용자 입력
    │
    ▼
┌──────────────────────────────────────────┐
│  WelCareFlow  (flow.py)                  │
│                                          │
│  @start   run_intake()                   │  ← IntakeCrew
│      │                                   │
│  @router  check_status()                 │  ← INCOMPLETE / COMPLETE 분기
│      │                  │                │
│  ask_user()        search_policies()     │  ← PolicySearchCrew
│  (역질문 반환)           │               │
│                   translate_result()     │  ← TranslatorCrew
│                   (쉬운 말로 최종 출력)  │
└──────────────────────────────────────────┘
```

---

## 에이전트

### 1. `intake_agent` — 복지 정보 수집 전문가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/intake_crew.py` |
| **역할** | 사용자와 대화하며 복지 매칭에 필요한 정보 수집 |
| **도구** | 없음 (대화 전용) |
| **동작** | 나이·가구수·월소득·장애 여부·거주 지역 등 누락 정보가 있으면 역질문(Slot Filling) 생성. 모든 조건이 갖춰지면 `status: COMPLETE` 반환 |

**출력 형식 (JSON)**
```json
{
  "status": "INCOMPLETE | COMPLETE",
  "follow_up_question": "추가 질문 (INCOMPLETE 시)",
  "conditions": {
    "age": "나이",
    "household_size": "가구수",
    "monthly_income": "월소득",
    "disability": "장애 여부",
    "region": "거주 지역"
  }
}
```

---

### 2. `policy_researcher_agent` — 복지 정책 검색 전문가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/policy_crew.py` |
| **역할** | 수집된 조건으로 실시간 웹 검색 후 맞춤 정책 제공 |
| **도구** | `SerperDevTool` (웹 검색), `ScrapeWebsiteTool` (크롤링) |
| **동작** | 복지로·고용노동부·지자체 사이트 검색 → 조건 부합 정책 최대 5개 선별 |

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
      "url": "링크"
    }
  ]
}
```

---

### 3. `translator_agent` — 쉬운 말 번역가

| 항목 | 내용 |
|------|------|
| **위치** | `crews/translator_crew.py` |
| **역할** | 정책 검색 결과의 행정 용어를 초등학생 수준의 쉬운 우리말로 순화 |
| **도구** | 없음 (텍스트 변환 전용) |
| **동작** | `policy_researcher_agent` 출력을 받아 용어만 바꿈. 정책명·금액·자격 조건 등 원래 내용은 절대 변경하지 않음 |

**용어 순화 예시**

| 행정 용어 | 쉬운 말 |
|-----------|---------|
| 소득인정액 | 가정의 실제 수입으로 인정되는 금액 |
| 부양의무자 | 부모님이나 자녀 |
| 차상위계층 | 기초생활수급자 바로 위 소득 계층 |
| 수급자 | 나라에서 돈을 받는 사람 |

**출력 형식 (사용자에게 바로 보여주는 텍스트)**
```
1. 정책 이름
- 어떤 도움인가요? : ...
- 누가 받을 수 있나요? : ...
- 어떻게 신청하나요? : ...
- 언제까지 신청하나요? : ...
- 더 알아보기 : URL
```

---

## Flow 실행 흐름

```
flow.kickoff(inputs)
    │
    ├─ @start()   run_intake()              # IntakeCrew 실행
    │
    ├─ @router    check_status()            # INCOMPLETE / COMPLETE 분기
    │       │
    │  "ask_followup"    "search_via_intake"
    │       │                  │
    │  ask_user()         search_policies() # or_("search_via_intake", "direct_search")
    │  역질문 반환              │             PolicySearchCrew 실행
    │                    translate_result() # @listen(search_policies)
    │                    쉬운 말 변환        TranslatorCrew 실행
    │                    → state.result 최종 저장
```

> `or_("search_via_intake", "direct_search")` — 추후 조건을 직접 주입하는 경로(예: Telegram 버튼) 확장용.

---

## 프로젝트 구조

```
WelCare/
├── crews/
│   ├── __init__.py
│   ├── intake_crew.py        # IntakeCrew       (intake_agent)
│   ├── policy_crew.py        # PolicySearchCrew (policy_researcher_agent)
│   └── translator_crew.py    # TranslatorCrew   (translator_agent)
├── config/
│   ├── agents.yaml           # agent role / goal / backstory
│   └── tasks.yaml            # task description / expected_output
├── flow.py                   # WelCareFlow (Flow 오케스트레이션)
├── main.py                   # 진입점 + 대화 루프
├── env.py                    # 환경변수 로딩
└── .env                      # API 키 (git 제외)
```

---

## 환경 변수 (.env)

```
TELEGRAM_BOT_TOKEN=...
GEMINI_API_KEY=...
SERPER_API_KEY=...
FIRECRAWL_API_KEY=...
```

---

## 실행

```bash
python main.py
```
