# Apache AGE 마이그레이션 버그 수정 내역

## 배경
pgVector → Apache AGE(Graph DB) 마이그레이션 과정에서 발견된 버그 목록과 수정 내용을 정리합니다.

---

## Bug #1 — `rag_generation_service.py` : 존재하지 않는 메서드 호출

**파일:** `app/core/service/rag_generation_service.py`
**위치:** `_insert_to_collection` 메서드 (구 192~208줄)

### 문제
구 pgvector 전용 메서드를 여전히 호출하고 있어 런타임 `AttributeError` 발생.

| 호출 중이던 메서드 | 문제 |
|---|---|
| `vector_repository.collection_name_check()` | `AgeRepositoryImpl`에 없음 |
| `vector_repository.existing_vector_store()` | `AgeRepositoryImpl`에 없음 |
| `vector_repository.build_vector_storage()` | `AgeRepositoryImpl`에 없음 |
| `vector_store.add_documents()` | LangChain pgvector 전용 |

### 수정
- `collection_exists()` + `save_documents()` 로 교체
- 임베딩 생성 로직 추가 (`OpenAIEmbeddingClient` 사용)
  - 기존 pgvector는 LangChain이 내부적으로 임베딩을 처리했으나, AGE는 수동으로 임베딩 후 저장해야 함

---

## Bug #2 — `age_repository_impl.py` : `collection_exists` IndexError

**파일:** `app/infra/repository/age_repository_impl.py`
**위치:** `collection_exists` 메서드 (구 100~102줄)

### 문제
```python
# result가 빈 리스트([])일 경우 IndexError 발생
return result[0] > 0
```

### 수정
```python
if not result:
    return False
return result[0] > 0
```

---

## Bug #3 — `age_repository_impl.py` : 롤백 대상 커넥션 오류

**파일:** `app/infra/repository/age_repository_impl.py`
**위치:** `_execute_cypher` 예외 처리 (구 28줄)

### 문제
```python
# 새 커넥션을 생성하여 그 커넥션을 롤백 → 현재 트랜잭션에 아무런 효과 없음
self.connection_manager.engine.connect().connection.rollback()
```

### 수정
```python
# 현재 커서가 속한 커넥션을 롤백
self.cursor.connection.rollback()
```

---

## Bug #4 — `llm_client.py` : 미임포트 타입 `PGVector` 참조

**파일:** `app/core/interface/llm_client.py`
**위치:** `chat_llm` 추상 메서드 반환 타입

### 문제
```python
# PGVector가 import되지 않아 모듈 로드 시 NameError 발생
def chat_llm(self, collection_name: str, documents: List[Document]) -> PGVector:
```
- `PGVector`는 pgvector 전용 타입으로, AGE 전환 후 불필요
- 구현체(`OpenAIChatClient`)에서는 이미 `@property`로 다르게 재정의됨
- 서비스 레이어 어디에서도 호출되지 않는 dead code

### 수정
`chat_llm` 추상 메서드 전체 제거

---

## 수정 파일 요약

| 파일 | 수정 내용 |
|---|---|
| `app/core/interface/llm_client.py` | `chat_llm` 추상 메서드 제거 (NameError 방지) |
| `app/infra/repository/age_repository_impl.py` | `collection_exists` 방어 코드 추가, `_execute_cypher` 롤백 대상 수정 |
| `app/core/service/rag_generation_service.py` | `_insert_to_collection`을 AGE 인터페이스에 맞게 전면 재작성 + 임베딩 처리 추가 |

---

## Bug #5 — `age_repository_impl.py` : system_id 콜론이 AGE 레이블명에 사용돼 오류

**발생일:** 2026-03-04
**파일:** `app/infra/repository/age_repository_impl.py`
**위치:** `save_documents()`, `get_related_screens()` 메서드

### 문제
멀티시스템 격리 기능(13단계) 도입 이후 `collection_name`에 `system_id:collection_name` 형식이 사용됨.
Apache AGE에서 Cypher 노드 레이블에 `:` (콜론)이 포함되면 유효하지 않은 스키마명 오류 발생.

```
psycopg.errors.InvalidSchemaName: label name is invalid
LINE 1: SELECT * FROM cypher('biz_rag_graph', $$
                                               ^
```

- `collection_name = "test:auto_test"` 일 때 `` CREATE (n:`test:auto_test` { ... }) `` 쿼리 생성
- AGE는 레이블명에 `:` 포함을 허용하지 않음

### 수정
레이블로 사용하기 전 `:` → `__`(이중 언더스코어)로 치환하는 `age_label` 변수 도입.
pgvector `collection_name` 컬럼(문자열 값)은 원본 유지.

```python
# save_documents() 상단
age_label = collection_name.replace(":", "__")

# Cypher 쿼리
CREATE (n:`{age_label}` { ... })

# pgvector insert는 원본 collection_name 그대로
self.connection_manager.insert_embedding(collection_name=collection_name, ...)
```

`get_related_screens()`도 동일하게 적용:
```python
age_label = collection_name.replace(":", "__")
query = f"MATCH (target:`{age_label}` {{ ... }}) ..."
```

---

## Bug #6 — Docker 볼륨 마운트 환경에서 `__pycache__` 충돌로 구버전 bytecode 실행

**발생일:** 2026-03-04
**파일:** 전체 (`app/**/__pycache__`)

### 문제
`docker-compose.yml`에서 `./app:/testcase-doc-rag/app`로 볼륨 마운트.
로컬 `./app` 내 `__pycache__`도 함께 마운트되어, 컨테이너가 이전 빌드의 `.pyc` 바이트코드를 실행.

증상:
- 소스 코드를 수정해도 변경이 반영되지 않음
- Python 에러 트레이스백의 줄 번호/코드가 실제 소스와 불일치

### 수정
코드 수정 후 반드시 `__pycache__` 삭제 → 컨테이너 재시작:

```bash
find ./app -type d -name "__pycache__" -exec rm -rf {} +
docker compose restart app
```

### 영구 해결 방안
`docker-compose.yml`의 앱 볼륨에 `__pycache__` 제외용 `.dockerignore` 처리,
또는 컨테이너 uvicorn 실행 옵션에 `--reload` 추가로 자동 재로드 설정.

---

---

## Bug #7 — `rag_generation_service.py` : 이미지 복수 업로드 시 첫 번째만 처리

**발생일:** 2026-03-06
**파일:** `app/core/service/rag_generation_service.py`
**위치:** `add_rag_data()` 메서드

### 문제
HTML 업로드 UI에서 이미지 2개를 동시에 업로드하면 1개만 저장됨.

원인: `service_name`, `version`, `access_level`은 폼에서 **단일 값**으로 전송되나,
루프를 `range(len(service_names))`로 순회하여 이미지 수와 무관하게 1회만 실행.

```python
# 버그 코드: service_names 길이(=1)만큼만 루프 → 이미지 2개 중 1개 누락
for i in range(len(service_names)):
    data_items.append({ ... "image": images[i] ... })
```

### 수정
루프 기준을 `images` 길이로 변경. 단일 메타데이터 값(공통 적용)은 `_get()` 헬퍼로 처리.

```python
def _get(lst, i, default=""):
    """단일 값이면 모든 이미지에 공통 적용, 복수이면 인덱스로 접근."""
    if not lst:
        return default
    return lst[i] if i < len(lst) else lst[0]

for i in range(len(images)):   # 이미지 수 기준으로 순회
    data_items.append({
        "service_name": _get(service_names, i),
        ...
    })
```

---

## 수정 파일 요약 (전체)

| 파일 | 수정 내용 |
|---|---|
| `app/core/interface/llm_client.py` | `chat_llm` 추상 메서드 제거 (NameError 방지) |
| `app/infra/repository/age_repository_impl.py` | `collection_exists` 방어 코드, `_execute_cypher` 롤백 수정, `age_label` sanitize (Bug#5) |
| `app/core/service/rag_generation_service.py` | `_insert_to_collection` AGE 전환, `screen_name` 패딩(Bug#6), 다중 이미지 루프 기준 수정(Bug#7) |
