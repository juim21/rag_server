"""19단계 멀티모달 CLIP 임베딩 단위 테스트"""
import sys
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# --- CI 환경에서 미설치 패키지 사전 Mock ---
_MOCKS = [
    "langchain", "langchain.prompts",
    "langchain_core", "langchain_core.documents",
    "langchain_core.language_models",
    "langchain_core.language_models.chat_models",
    "langchain_core.messages",
    "langchain_google_genai",
    "langchain_openai",
    "langchain_openai.chat_models",
    "langchain_openai.chat_models.azure",
    "sentence_transformers",
    "PIL", "PIL.Image",
    # pgvectorDB.py 모듈 레벨 import 대응
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.pool",
    "dotenv",
]
for _m in _MOCKS:
    sys.modules.setdefault(_m, MagicMock())

# PIL.Image.open mock
pil_mock = sys.modules["PIL.Image"]
pil_mock.open.return_value = MagicMock()


# ──────────────────────────────────────────────
# 1. 인터페이스 준수 검증
# ──────────────────────────────────────────────
class TestClipEmbeddingClientInterface:

    def test_is_subclass_of_interface(self):
        from app.core.interface.multimodal_embedding_client import MultimodalEmbeddingClient
        from app.infra.external.embedding.clip_embedding_client import ClipEmbeddingClient
        assert issubclass(ClipEmbeddingClient, MultimodalEmbeddingClient)

    def test_interface_abstract_methods(self):
        import inspect
        from app.core.interface.multimodal_embedding_client import MultimodalEmbeddingClient
        abstract_methods = {
            m for m, v in inspect.getmembers(MultimodalEmbeddingClient)
            if getattr(v, '__isabstractmethod__', False)
        }
        assert abstract_methods == {"embed_text", "embed_image_base64"}

    def test_clip_client_implements_embed_text(self):
        from app.infra.external.embedding.clip_embedding_client import ClipEmbeddingClient
        client = ClipEmbeddingClient()

        fake_vector = [0.1] * 512
        mock_array = MagicMock()
        mock_array.tolist.return_value = fake_vector

        mock_model = MagicMock()
        mock_model.encode.return_value = [mock_array]
        ClipEmbeddingClient._model = mock_model

        result = client.embed_text("로그인 화면")
        assert isinstance(result, list)
        assert result == fake_vector
        mock_model.encode.assert_called_once_with(["로그인 화면"])
        ClipEmbeddingClient._model = None  # 초기화

    def test_clip_client_implements_embed_image_base64(self):
        import base64
        from app.infra.external.embedding.clip_embedding_client import ClipEmbeddingClient
        client = ClipEmbeddingClient()

        fake_vector = [0.2] * 512
        mock_array = MagicMock()
        mock_array.tolist.return_value = fake_vector

        mock_model = MagicMock()
        mock_model.encode.return_value = [mock_array]
        ClipEmbeddingClient._model = mock_model

        b64 = base64.b64encode(b"fake_image_bytes").decode()
        result = client.embed_image_base64(b64)
        assert isinstance(result, list)
        assert result == fake_vector
        ClipEmbeddingClient._model = None  # 초기화


# ──────────────────────────────────────────────
# 2. pgvectorDB _visual_search / search_similar 분기
# ──────────────────────────────────────────────
class TestPGVectorVisualSearch:

    def _make_manager(self):
        """실제 DB 연결 없이 PGVectorManager 인스턴스 생성"""
        from app.infra.database.pgvectorDB import PGVectorManager
        mgr = object.__new__(PGVectorManager)
        return mgr

    def test_search_similar_visual_calls_visual_search(self):
        mgr = self._make_manager()
        fake_result = [{"content": "c", "metadata": {}, "score": 0.9}]
        with patch.object(mgr, '_visual_search', return_value=fake_result) as mock_vs:
            result = mgr.search_similar(
                "col", None, k=3, search_mode="visual",
                image_embedding=[0.1] * 512
            )
        mock_vs.assert_called_once_with("col", [0.1] * 512, 3, None)
        assert result == fake_result

    def test_search_similar_visual_without_embedding_falls_back_to_vector(self):
        """image_embedding=None 이면 visual이라도 vector_search fallback"""
        mgr = self._make_manager()
        with patch.object(mgr, '_vector_search', return_value=[]) as mock_vec:
            mgr.search_similar("col", [0.1] * 3072, k=3,
                               search_mode="visual", image_embedding=None)
        mock_vec.assert_called_once()

    def test_search_similar_hybrid_calls_hybrid_search(self):
        mgr = self._make_manager()
        with patch.object(mgr, '_hybrid_search', return_value=[]) as mock_h:
            mgr.search_similar("col", [0.1] * 3072, k=3,
                               search_mode="hybrid", query_text="로그인")
        mock_h.assert_called_once()

    def test_search_similar_vector_default(self):
        mgr = self._make_manager()
        with patch.object(mgr, '_vector_search', return_value=[]) as mock_v:
            mgr.search_similar("col", [0.1] * 3072, k=5)
        mock_v.assert_called_once()

    def test_insert_embedding_with_image(self):
        """image_embedding 있을 때 올바른 SQL 호출 확인"""
        mgr = self._make_manager()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        with patch.object(mgr, 'get_cursor', return_value=mock_cursor):
            mgr.insert_embedding("col", "content", {"k": "v"}, [0.1] * 3072,
                                 image_embedding=[0.2] * 512)
        sql = mock_cursor.execute.call_args[0][0]
        assert "image_embedding" in sql
        assert "%s::vector" in sql

    def test_insert_embedding_without_image(self):
        """image_embedding=None 이면 NULL 삽입 SQL 사용"""
        mgr = self._make_manager()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        with patch.object(mgr, 'get_cursor', return_value=mock_cursor):
            mgr.insert_embedding("col", "content", {}, [0.1] * 3072)
        sql = mock_cursor.execute.call_args[0][0]
        assert "NULL" in sql


# ──────────────────────────────────────────────
# 3. RagGenerationService visual 검색 분기
# ──────────────────────────────────────────────
class TestRagGenerationServiceVisual:

    def _make_service(self):
        from app.core.service.rag_generation_service import RagGenerationService
        svc = object.__new__(RagGenerationService)
        svc.vector_repository = MagicMock()
        svc.cache_client = MagicMock()
        svc.cache_client.get = AsyncMock(return_value=None)
        svc.cache_client.set = AsyncMock()
        svc.rerank_client = None
        svc.embedding_client = MagicMock()
        svc.clip_client = MagicMock()
        svc.clip_client.embed_text.return_value = [0.1] * 512
        svc.vector_repository.similarity_search.return_value = [
            ({"page_content": "로그인 화면", "metadata": {}}, 0.88)
        ]
        return svc

    @pytest.mark.asyncio
    async def test_search_rag_visual_uses_clip_embed_text(self):
        svc = self._make_service()
        results = await svc.search_rag("col", "로그인", k=3, search_mode="visual")
        svc.clip_client.embed_text.assert_called_once_with("로그인")
        svc.vector_repository.similarity_search.assert_called_once()
        call_kwargs = svc.vector_repository.similarity_search.call_args
        # image_embedding이 clip 결과로 전달됐는지 확인
        args = call_kwargs[0]
        assert args[4] == "visual"  # search_mode
        assert args[6] == [0.1] * 512  # image_embedding
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_rag_visual_no_google_embed(self):
        """visual 모드에서 Google 임베딩 호출 없음"""
        svc = self._make_service()
        await svc.search_rag("col", "query", k=3, search_mode="visual")
        svc.embedding_client.embeddings.embed_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_by_image(self):
        svc = self._make_service()
        svc.clip_client.embed_image_base64.return_value = [0.5] * 512
        import base64
        dummy_b64 = base64.b64encode(b"fake_image").decode()
        results = await svc.search_by_image("col", dummy_b64, k=2)
        svc.clip_client.embed_image_base64.assert_called_once_with(dummy_b64)
        svc.vector_repository.similarity_search.assert_called_once()
        assert len(results) == 1

    def test_insert_to_collection_calls_clip_for_images(self):
        svc = self._make_service()
        svc.embedding_client.embeddings.embed_documents.return_value = [[0.1] * 3072]
        svc.clip_client.embed_image_base64.return_value = [0.2] * 512
        svc.vector_repository.collection_exists.return_value = False
        svc.vector_repository.save_documents.return_value = None

        doc = MagicMock()
        doc.page_content = "로그인 화면 설명"
        doc.metadata = {"service_name": "test"}

        import base64
        b64 = base64.b64encode(b"image_data").decode()
        svc._insert_to_collection("col", [doc], base64_images=[b64])

        svc.clip_client.embed_image_base64.assert_called_once_with(b64)
        saved = svc.vector_repository.save_documents.call_args[0][1]
        assert saved[0]["image_embedding"] == [0.2] * 512

    def test_insert_to_collection_no_images_sets_none(self):
        """base64_images 미전달 시 image_embedding=None"""
        svc = self._make_service()
        svc.embedding_client.embeddings.embed_documents.return_value = [[0.1] * 3072]
        svc.vector_repository.collection_exists.return_value = False
        svc.vector_repository.save_documents.return_value = None

        doc = MagicMock()
        doc.page_content = "텍스트 문서"
        doc.metadata = {}

        svc._insert_to_collection("col", [doc])

        saved = svc.vector_repository.save_documents.call_args[0][1]
        assert saved[0]["image_embedding"] is None
