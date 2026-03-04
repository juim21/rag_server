"""security.py 단위 테스트"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ── _load_api_keys ───────────────────────────────────────────────────────────

def test_load_api_keys_empty(monkeypatch):
    """API_KEYS 미설정 시 빈 set 반환 → 인증 비활성화"""
    monkeypatch.delenv("API_KEYS", raising=False)
    from app.core.middleware.security import _load_api_keys
    assert _load_api_keys() == set()


def test_load_api_keys_single(monkeypatch):
    """단일 키 파싱"""
    monkeypatch.setenv("API_KEYS", "key-aaa")
    from app.core.middleware.security import _load_api_keys
    assert _load_api_keys() == {"key-aaa"}


def test_load_api_keys_multiple(monkeypatch):
    """쉼표 구분 복수 키 파싱"""
    monkeypatch.setenv("API_KEYS", "key-aaa,key-bbb")
    from app.core.middleware.security import _load_api_keys
    assert _load_api_keys() == {"key-aaa", "key-bbb"}


def test_load_api_keys_whitespace(monkeypatch):
    """공백 포함 입력도 정상 파싱"""
    monkeypatch.setenv("API_KEYS", " key-aaa , key-bbb ")
    from app.core.middleware.security import _load_api_keys
    result = _load_api_keys()
    assert "key-aaa" in result
    assert "key-bbb" in result


def test_load_api_keys_ignores_empty_items(monkeypatch):
    """연속 쉼표 등 빈 항목 무시"""
    monkeypatch.setenv("API_KEYS", "key-aaa,,key-bbb,")
    from app.core.middleware.security import _load_api_keys
    result = _load_api_keys()
    assert result == {"key-aaa", "key-bbb"}


# ── verify_api_key ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_api_key_disabled(monkeypatch):
    """API_KEYS 미설정 시 인증 비활성화, None 반환"""
    monkeypatch.delenv("API_KEYS", raising=False)
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    result = await verify_api_key(request=mock_request, api_key=None)
    assert result is None


@pytest.mark.asyncio
async def test_verify_api_key_missing_raises_401(monkeypatch):
    """키 설정 시 헤더 누락 → 401"""
    monkeypatch.setenv("API_KEYS", "key-aaa")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(request=mock_request, api_key=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_invalid_raises_403(monkeypatch):
    """잘못된 키 → 403"""
    monkeypatch.setenv("API_KEYS", "key-aaa")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(request=mock_request, api_key="wrong-key")
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_api_key_valid(monkeypatch):
    """유효한 키 → api_key 반환"""
    monkeypatch.setenv("API_KEYS", "key-aaa,key-bbb")
    from app.core.middleware.security import verify_api_key

    mock_request = MagicMock()
    mock_request.state = MagicMock()

    result = await verify_api_key(request=mock_request, api_key="key-aaa")
    assert result == "key-aaa"


# ── _prefixed_collection ────────────────────────────────────────────────────

def test_prefixed_collection_with_system_id():
    """system_id 있으면 prefix 붙임"""
    from app.api.rag_controller import _prefixed_collection
    assert _prefixed_collection("screens", "system01") == "system01:screens"


def test_prefixed_collection_no_system_id():
    """system_id 없으면 원본 반환"""
    from app.api.rag_controller import _prefixed_collection
    assert _prefixed_collection("screens") == "screens"
    assert _prefixed_collection("screens", None) == "screens"


def test_prefixed_collection_default_system_id():
    """system_id가 'default'이면 prefix 미적용"""
    from app.api.rag_controller import _prefixed_collection
    assert _prefixed_collection("screens", "default") == "screens"


def test_prefixed_collection_different_system_ids():
    """서로 다른 system_id는 서로 다른 collection 반환"""
    from app.api.rag_controller import _prefixed_collection
    assert _prefixed_collection("screens", "system01") != _prefixed_collection("screens", "system02")
    assert _prefixed_collection("screens", "system01") == "system01:screens"
    assert _prefixed_collection("screens", "system02") == "system02:screens"
