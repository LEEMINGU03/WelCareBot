import os
import dotenv

dotenv.load_dotenv()


def get_env_variable(key: str) -> str:
    value = os.getenv(key)
    if value is None:
        raise ValueError(
            f"{key} 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요."
        )
    return value


TELEGRAM_BOT_TOKEN = get_env_variable("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY")
FIRECRAWL_API_KEY  = get_env_variable("FIRECRAWL_API_KEY")
SERPER_API_KEY = get_env_variable("SERPER_API_KEY")
