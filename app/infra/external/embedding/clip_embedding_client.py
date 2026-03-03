import base64
import io
from typing import List

from app.core.interface.multimodal_embedding_client import MultimodalEmbeddingClient


class ClipEmbeddingClient(MultimodalEmbeddingClient):
    """CLIP(clip-ViT-B-32) 기반 멀티모달 임베딩 클라이언트.
    싱글톤 패턴으로 모델을 한 번만 로드합니다.
    첫 요청 시 모델을 자동 다운로드합니다 (~600MB).
    텍스트와 이미지 모두 512차원 벡터로 인코딩합니다.
    """
    _model = None
    _model_name = "clip-ViT-B-32"

    def __init__(self):
        pass  # 모델은 첫 embed 호출 시 lazy load

    def _ensure_model(self):
        if ClipEmbeddingClient._model is None:
            import structlog
            logger = structlog.get_logger()
            logger.info("clip_model_loading", model=self._model_name)
            from sentence_transformers import SentenceTransformer
            ClipEmbeddingClient._model = SentenceTransformer(self._model_name)
            logger.info("clip_model_ready", model=self._model_name)

    def embed_text(self, text: str) -> List[float]:
        """텍스트를 CLIP 텍스트 인코더로 512차원 벡터로 변환합니다."""
        self._ensure_model()
        return ClipEmbeddingClient._model.encode([text])[0].tolist()

    def embed_image_base64(self, base64_str: str) -> List[float]:
        """base64 이미지를 CLIP 이미지 인코더로 512차원 벡터로 변환합니다."""
        from PIL import Image
        self._ensure_model()
        img = Image.open(io.BytesIO(base64.b64decode(base64_str))).convert("RGB")
        return ClipEmbeddingClient._model.encode([img])[0].tolist()
