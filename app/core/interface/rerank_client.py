from abc import ABC, abstractmethod
from typing import List, Tuple


class RerankClient(ABC):

    @abstractmethod
    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        """쿼리와 문서 목록을 받아 재랭킹된 (원본 인덱스, 점수) 목록을 반환합니다.
        top_k: 반환할 최대 결과 수
        """
        pass
