from abc import ABC, abstractmethod
from typing import Optional


class CacheClient(ABC):

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """키에 해당하는 캐시 값을 반환합니다. 없으면 None."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int = 3600):
        """키-값을 캐시에 저장합니다. ttl은 초 단위."""
        pass

    @abstractmethod
    async def delete_pattern(self, pattern: str):
        """패턴에 매칭되는 모든 키를 삭제합니다."""
        pass

    @abstractmethod
    async def ping(self) -> bool:
        """캐시 연결 상태를 확인합니다. 정상이면 True."""
        pass
