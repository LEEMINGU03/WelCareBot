import env  # noqa: F401  — loads .env
import sys
from flow import WelCareFlow


def run_agent(user_message: str, history: list[str]) -> WelCareFlow:
    flow = WelCareFlow()
    flow.kickoff(inputs={
        "message": user_message,
        "history": list(history),
    })
    return flow


if __name__ == "__main__":
    print("\nWelCare 복지 정책 챗봇  |  종료: exit\n")

    history: list[str] = []

    # 실행 시 인자가 있으면 바로 agent 작동
    initial_message = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "안녕하세요"

    history.append(f"사용자: {initial_message}")
    flow = run_agent(initial_message, history)
    print(f"\n봇 : {flow.state.result}\n")

    if flow.state.status == "INCOMPLETE":
        history.append(f"봇: {flow.state.follow_up}")
    else:
        history = []

    while True:
        user_message = input("나 : ").strip()
        if user_message.lower() == "exit":
            break
        if not user_message:
            continue

        history.append(f"사용자: {user_message}")
        flow = run_agent(user_message, history)
        print(f"\n봇 : {flow.state.result}\n")

        if flow.state.status == "INCOMPLETE":
            history.append(f"봇: {flow.state.follow_up}")
        else:
            history = []
