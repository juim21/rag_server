from typing import List, Tuple

from app.core.interface.rerank_client import RerankClient


class CrossEncoderClient(RerankClient):
    """BAAI/bge-reranker-base 크로스인코더 기반 재랭킹 클라이언트.
    싱글톤 패턴으로 모델을 한 번만 로드합니다.
    첫 요청 시 모델을 자동 다운로드합니다 (~280MB).
    """
    _model = None
    _model_name = "BAAI/bge-reranker-base"

    def __init__(self):
        if CrossEncoderClient._model is None:
            from sentence_transformers import CrossEncoder
            print(f"[RerankClient] 크로스인코더 모델 로드 중: {self._model_name}")
            CrossEncoderClient._model = CrossEncoder(self._model_name)
            print("[RerankClient] 모델 로드 완료")

    def rerank(self, query: str, documents: List[str], top_k: int) -> List[Tuple[int, float]]:
        """쿼리와 문서 쌍의 관련도 점수를 계산하여 재랭킹합니다.
        반환: [(원본_인덱스, 점수), ...] (점수 내림차순, top_k 개)
        """
        if not documents:
            return []

        pairs = [[query, doc] for doc in documents]
        scores = CrossEncoderClient._model.predict(pairs)
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(int(idx), float(score)) for idx, score in indexed[:top_k]]
