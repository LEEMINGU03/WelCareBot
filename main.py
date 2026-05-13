import env  # noqa: F401  — loads .env
import sys
from flow import WelCareFlow


def _fresh_state() -> dict:
    return {
        "phase": "intake",
        "policies": [],
        "selected_policy": {},
        "conditions": {},
    }


def run_agent(user_message: str, history: list[str], state_data: dict) -> WelCareFlow:
    flow = WelCareFlow()
    flow.kickoff(inputs={
        "message": user_message,
        "history": list(history),
        **state_data,
    })
    return flow


def _sync_state(state_data: dict, flow: WelCareFlow) -> None:
    state_data["phase"] = flow.state.phase
    state_data["policies"] = flow.state.policies
    state_data["selected_policy"] = flow.state.selected_policy
    state_data["conditions"] = flow.state.conditions


if __name__ == "__main__":
    print("\nWelCare 복지 정책 챗봇  |  종료: exit\n")

    history: list[str] = []
    state_data = _fresh_state()

    initial_message = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "안녕하세요"
    history.append(f"사용자: {initial_message}")

    flow = run_agent(initial_message, history, state_data)
    print(f"\n봇 : {flow.state.result}\n")
    history.append(f"봇: {flow.state.result}")
    _sync_state(state_data, flow)

    if flow.state.phase == "done":
        state_data = _fresh_state()
        history = []

    while True:
        user_message = input("나 : ").strip()
        if user_message.lower() == "exit":
            break
        if not user_message:
            continue

        history.append(f"사용자: {user_message}")
        flow = run_agent(user_message, history, state_data)
        print(f"\n봇 : {flow.state.result}\n")
        history.append(f"봇: {flow.state.result}")
        _sync_state(state_data, flow)

        if flow.state.phase == "done":
            state_data = _fresh_state()
            history = []
