from abc import ABC, abstractmethod
from typing import List


class MultimodalEmbeddingClient(ABC):

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """텍스트를 CLIP 텍스트 인코더로 임베딩합니다."""
        ...

    @abstractmethod
    def embed_image_base64(self, base64_str: str) -> List[float]:
        """base64 인코딩된 이미지를 CLIP 이미지 인코더로 임베딩합니다."""
        ...
