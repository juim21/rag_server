"""security.py 단위 테스트"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ── _load_key_tenant_map ────────────────────────────────────────────────────

def test_load_key_tenant_map_empty(monkeypatch):
    """API_KEYS 미설정 시 빈 dict 반환 → 인증 비활성화"""
    monkeypatch.delenv("API_KEYS", raising=False)
    from app.core.middleware.security import _load_key_tenant_map
    assert _load_key_tenant_map() == {}


def test_load_key_tenant_map_tenant_format(monkeypatch):
    """tenant:key 형식 파싱"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa,svc_b:key-bbb")
    from app.core.middleware.security import _load_key_tenant_map
    result = _load_key_tenant_map()
    assert result == {"key-aaa": "svc_a", "key-bbb": "svc_b"}


def test_load_key_tenant_map_key_only(monkeypatch):
    """키만 있고 tenant 없으면 'default' tenant 할당"""
    monkeypatch.setenv("API_KEYS", "plainkey123")
    from app.core.middleware.security import _load_key_tenant_map
    result = _load_key_tenant_map()
    assert result == {"plainkey123": "default"}


def test_load_key_tenant_map_mixed(monkeypatch):
    """tenant:key 와 key-only 혼용"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa,legacykey")
    from app.core.middleware.security import _load_key_tenant_map
    result = _load_key_tenant_map()
    assert result["key-aaa"] == "svc_a"
    assert result["legacykey"] == "default"


def test_load_key_tenant_map_whitespace(monkeypatch):
    """공백 포함 입력도 정상 파싱"""
    monkeypatch.setenv("API_KEYS", " svc_a : key-aaa , svc_b : key-bbb ")
    from app.core.middleware.security import _load_key_tenant_map
    result = _load_key_tenant_map()
    assert "key-aaa" in result
    assert "key-bbb" in result


# ── verify_api_key ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_api_key_disabled(monkeypatch):
    """API_KEYS 미설정 시 인증 비활성화, tenant=None 주입"""
    monkeypatch.delenv("API_KEYS", raising=False)
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    result = await verify_api_key(request=mock_request, api_key=None)
    assert result is None
    assert mock_request.state.tenant is None


@pytest.mark.asyncio
async def test_verify_api_key_missing_raises_401(monkeypatch):
    """키 설정 시 헤더 누락 → 401"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(request=mock_request, api_key=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_invalid_raises_403(monkeypatch):
    """잘못된 키 → 403"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(request=mock_request, api_key="wrong-key")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_api_key_valid_injects_tenant(monkeypatch):
    """유효한 키 → tenant를 request.state에 주입"""
    monkeypatch.setenv("API_KEYS", "svc_a:key-aaa")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    result = await verify_api_key(request=mock_request, api_key="key-aaa")
    assert result == "key-aaa"
    assert mock_request.state.tenant == "svc_a"


# ── _prefixed_collection ────────────────────────────────────────────────────

def test_prefixed_collection_with_tenant():
    """tenant 있으면 prefix 붙임"""
    from app.api.rag_controller import _prefixed_collection

    mock_request = MagicMock()
    mock_request.state.tenant = "system01"

    result = _prefixed_collection(mock_request, "screens")
    assert result == "system01:screens"


def test_prefixed_collection_no_tenant():
    """tenant 없으면 원본 반환"""
    from app.api.rag_controller import _prefixed_collection

    mock_request = MagicMock()
    mock_request.state.tenant = None

    result = _prefixed_collection(mock_request, "screens")
    assert result == "screens"


def test_prefixed_collection_default_tenant():
    """tenant가 'default'이면 prefix 미적용"""
    from app.api.rag_controller import _prefixed_collection

    mock_request = MagicMock()
    mock_request.state.tenant = "default"

    result = _prefixed_collection(mock_request, "screens")
    assert result == "screens"


def test_prefixed_collection_different_tenants():
    """서로 다른 tenant는 서로 다른 collection 반환"""
    from app.api.rag_controller import _prefixed_collection

    req_a = MagicMock()
    req_a.state.tenant = "system01"

    req_b = MagicMock()
    req_b.state.tenant = "system02"

    assert _prefixed_collection(req_a, "screens") != _prefixed_collection(req_b, "screens")
    assert _prefixed_collection(req_a, "screens") == "system01:screens"
    assert _prefixed_collection(req_b, "screens") == "system02:screens"
