"""테스트 환경 공통 설정 - CI에 설치되지 않은 무거운 패키지 사전 모킹"""
import sys
from unittest.mock import MagicMock

# CI 환경에서 설치되지 않는 패키지를 sys.modules에 Mock으로 등록.
# 실제 사용 코드는 DIContainer.get()으로 의존성을 주입하므로 모킹해도 무방.
_HEAVY_MODULES = [
    "langchain",
    "langchain.prompts",
    "langchain_core",
    "langchain_core.documents",
    "langchain_core.language_models",
    "langchain_core.messages",
    "langchain_google_genai",
]

for _mod in _HEAVY_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
