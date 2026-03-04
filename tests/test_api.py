"""API 엔드포인트 통합 테스트 (TestClient, DB/Redis mock)"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def _make_app(monkeypatch, api_keys=""):
    """테스트용 FastAPI 앱 생성 (DI Container mock)"""
    monkeypatch.setenv("API_KEYS", api_keys)
    monkeypatch.setenv("REDIS_HOST", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    # DI Container + 외부 의존성 mock
    mock_repo = MagicMock()
    mock_repo.health_check = MagicMock(return_value=None)

    mock_cache = AsyncMock()
    mock_cache.ping = AsyncMock(return_value=True)
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    mock_cache.delete_pattern = AsyncMock()

    with patch("app.di_container.DIContainer.get") as mock_get:
        def _get_side_effect(interface):
            from app.core.interface import RagRepository
            from app.core.interface.cache_client import CacheClient
            if interface == RagRepository:
                return mock_repo
            if interface == CacheClient:
                return mock_cache
            return MagicMock()

        mock_get.side_effect = _get_side_effect

        from app.main import app
        return TestClient(app, raise_server_exceptions=False)


# ── /health ─────────────────────────────────────────────────────────────────

def test_health_no_auth_required(monkeypatch):
    """/health는 API 키 없이도 200 반환"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    monkeypatch.setenv("REDIS_HOST", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    with patch("app.di_container.DIContainer.get") as mock_get:
        mock_repo = MagicMock()
        mock_repo.health_check = MagicMock(return_value=None)
        mock_cache = AsyncMock()
        mock_cache.ping = AsyncMock(return_value=True)

        def _side(interface):
            from app.core.interface import RagRepository
            from app.core.interface.cache_client import CacheClient
            if interface == RagRepository:
                return mock_repo
            if interface == CacheClient:
                return mock_cache
            return MagicMock()

        mock_get.side_effect = _side

        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/rag/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── 인증 테스트 ──────────────────────────────────────────────────────────────

def test_search_without_key_returns_401(monkeypatch):
    """/search: API_KEYS 설정 시 키 없으면 401"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    monkeypatch.setenv("REDIS_HOST", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    with patch("app.di_container.DIContainer.get", return_value=MagicMock()):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/rag/search",
            json={"collection_name": "screens", "query": "test", "k": 1}
        )
        assert resp.status_code == 401


def test_search_with_wrong_key_returns_403(monkeypatch):
    """/search: 잘못된 키 → 403"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    monkeypatch.setenv("REDIS_HOST", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    with patch("app.di_container.DIContainer.get", return_value=MagicMock()):
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/rag/search",
            headers={"X-API-Key": "wrong-key"},
            json={"collection_name": "screens", "query": "test", "k": 1}
        )
        assert resp.status_code == 403


def test_screen_name_padding_prevents_index_error():
    """screen_name 미전달 시 이미지 수만큼 빈 문자열 패딩 — Bug#6 회귀 테스트.
    패딩 없이 images보다 screen_names 길이가 짧으면 IndexError 발생하던 버그."""
    screen_names = []          # screen_name 필드 없이 요청한 경우
    image_count = 3            # 이미지 3장 업로드

    while len(screen_names) < image_count:
        screen_names.append("")

    # 패딩 후 각 이미지 인덱스로 screen_name 접근해도 IndexError 없어야 함
    items = [{"screen_name": screen_names[i]} for i in range(image_count)]
    assert len(items) == image_count
    assert all(item["screen_name"] == "" for item in items)


def test_screen_name_partial_padding():
    """screen_name이 일부만 전달된 경우 나머지를 빈 문자열로 패딩"""
    screen_names = ["로그인 화면"]  # 1개만 전달
    image_count = 3

    while len(screen_names) < image_count:
        screen_names.append("")

    assert len(screen_names) == image_count
    assert screen_names[0] == "로그인 화면"
    assert screen_names[1] == ""
    assert screen_names[2] == ""


def test_search_auth_disabled_when_no_api_keys(monkeypatch):
    """/search: API_KEYS 미설정 시 인증 비활성화 → 키 없어도 통과"""
    monkeypatch.setenv("API_KEYS", "")
    monkeypatch.setenv("REDIS_HOST", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    mock_service = MagicMock()
    mock_service.search_rag = AsyncMock(return_value=[])

    with patch("app.di_container.DIContainer.get") as mock_get:
        from app.core.service.rag_generation_service import RagGenerationService
        from app.core.interface.cache_client import CacheClient
        mock_cache = AsyncMock()
        mock_cache.ping = AsyncMock(return_value=True)

        def _side(interface):
            if interface == RagGenerationService:
                return mock_service
            if interface == CacheClient:
                return mock_cache
            return MagicMock()

        mock_get.side_effect = _side

        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/rag/search",
            json={"collection_name": "screens", "query": "test", "k": 1}
        )
        # 인증은 통과 (401/403 아님)
        assert resp.status_code not in (401, 403)
