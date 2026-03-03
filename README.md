# Application Analysis RAG Service

## 서비스 개요

애플리케이션 화면 이미지(또는 텍스트 설명)를 **Gemini 2.5 Flash Vision**으로 분석하고, 분석 결과를 벡터 임베딩으로 변환하여 **Apache AGE(그래프 DB)** 에 저장하는 RAG(Retrieval-Augmented Generation) 구축 서비스입니다.

소스코드 변경 시 영향받는 화면을 빠르게 검색할 수 있는 기반 데이터를 구축하고, 테스트 케이스 자동 생성을 위한 RAG 시스템을 제공합니다.

### 주요 목적

- 앱/웹 화면 이미지를 AI로 분석하여 UI 구성요소, 기능, 사용자 액션을 구조화된 JSON으로 추출
- 추출 결과를 벡터 임베딩으로 변환하여 Apache AGE 그래프 노드로 저장
- 이미지 없이 텍스트 설명만으로도 RAG 데이터 구축 지원
- 저장된 데이터를 코사인 유사도 기반으로 검색하여 관련 화면 정보 반환

---

## 아키텍처

### 시스템 흐름

```
Client
  │
  ▼
FastAPI (rag_controller)
  │
  ├─► RagGenerationService
  │       │
  │       ├─► ImageExtractor            (이미지 → base64 변환, Document 생성)
  │       ├─► GoogleChatClient          (Gemini 2.5 Flash Vision 이미지 분석)
  │       ├─► GoogleEmbeddingClient     (gemini-embedding-001 임베딩)
  │       └─► RagRepository            (Apache AGE 저장/검색)
  │               │
  │               └─► PGVectorManager  (PostgreSQL 연결풀, psycopg3)
  │
  └─► Google AI API (Gemini 2.5 Flash, gemini-embedding-001)
```

### 레이어 구조 (Clean Architecture)

| 레이어 | 역할 |
|--------|------|
| `api/` | HTTP 요청/응답 처리, 라우팅 |
| `core/interface/` | Repository·LLM 추상 인터페이스 정의 |
| `core/service/` | 비즈니스 로직 (이미지 분석, 임베딩, 저장/검색 흐름) |
| `infra/database/` | PostgreSQL 연결풀 관리 (SQLAlchemy + QueuePool) |
| `infra/repository/` | RagRepository 구현체 (Apache AGE Cypher 기반) |
| `infra/external/` | Google LLM·임베딩 클라이언트 (싱글톤) |
| `config/` | DB 설정, LLM 프롬프트 |
| `di_container.py` | 경량 DI 컨테이너 (인터페이스 → 구현체 매핑) |

### 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | FastAPI 0.115, Python 3.11, Uvicorn |
| Graph DB | PostgreSQL + Apache AGE 1.6.0 (Cypher 쿼리) |
| Vector | PostgreSQL + pgvector 0.8.1 (임베딩 저장) |
| AI/ML | Google Gemini 2.5 Flash (Vision), gemini-embedding-001 |
| Framework | LangChain 0.2 |
| ORM | SQLAlchemy 2.0, psycopg3 |
| Cache | Redis 7 (redis[asyncio]) |
| Monitoring | structlog 24.4, prometheus-client, prometheus-fastapi-instrumentator |
| Observability | Prometheus, Grafana |
| 컨테이너 | Docker, Docker Compose |

---

## 프로젝트 구조

```
rag_server/
├── app/
│   ├── main.py                          # FastAPI 앱 진입점, 의존성 등록
│   ├── di_container.py                  # 경량 DI 컨테이너
│   ├── api/
│   │   ├── rag_controller.py            # API 엔드포인트 정의
│   │   └── model/
│   │       ├── request/rag_request.py   # RAGRequest, RAGSearchRequest (Pydantic)
│   │       └── response/rag_response.py # RAGResponse, RAGSearchResponse (Pydantic)
│   ├── core/
│   │   ├── interface/
│   │   │   ├── rag_repository.py        # RagRepository 추상 클래스
│   │   │   └── llm_client.py            # LlmClient 추상 클래스
│   │   └── service/
│   │       ├── rag_generation_service.py # 핵심 비즈니스 로직
│   │       └── data_extractor.py         # 이미지→base64, Document 변환
│   ├── infra/
│   │   ├── database/pgvectorDB.py        # PGVectorManager (연결풀)
│   │   ├── repository/
│   │   │   └── age_repository_impl.py   # Apache AGE 그래프 저장소 구현체
│   │   └── external/
│   │       ├── llm/google_client.py           # Google Gemini 2.5 Flash 클라이언트
│   │       └── embedding/google_embedding_client.py  # Google 임베딩 클라이언트
│   └── config/
│       ├── database_config.py           # DB 접속 환경변수 로드
│       └── prompt.py                    # 이미지 분석용 시스템/유저 프롬프트
├── test_images/                         # 일괄 처리 테스트용 이미지 (1.png ~ 8.png)
├── Dockerfile                           # FastAPI 앱 이미지
├── Dockerfile.db                        # pgvector + Apache AGE 포함 PostgreSQL 이미지
├── docker-compose.yml                   # 전체 스택 실행
├── init-db.sh                           # DB 초기화 (pgvector, AGE 확장 및 그래프 생성)
├── requirements.txt
└── .env.example
```

---

## API 엔드포인트

### POST `/api/rag/generation/vector`

`test_images/` 디렉토리의 이미지를 일괄 분석하여 그래프 저장합니다. (개발·테스트용)

```http
POST /api/rag/generation/vector
Content-Type: application/json

{
    "collection_name": "my_collection"
}
```

**처리 흐름**
1. `test_images/` 디렉토리에서 이미지를 base64로 읽음
2. ThreadPoolExecutor (max_workers=5)로 Gemini 2.5 Flash Vision 병렬 분석
3. 분석 결과를 LangChain Document로 변환
4. gemini-embedding-001 임베딩 생성 후 Apache AGE 그래프 노드 + pgvector 테이블에 저장

---

### POST `/api/rag/add/vector`

멀티파트 폼으로 이미지와 메타데이터를 전송하여 기존 컬렉션에 추가합니다.

```http
POST /api/rag/add/vector
Content-Type: multipart/form-data

collection_name: my_collection
service_name:    서비스명 (배열, 이미지 수만큼)
screen_name:     화면명  (배열)
version:         버전    (배열)
access_level:    접근권한 (배열, 예: user / admin)
images:          이미지 파일 (배열)
```

---

### POST `/api/rag/add/text`

이미지 없이 텍스트 설명만으로 컬렉션에 데이터를 추가합니다.

```http
POST /api/rag/add/text
Content-Type: multipart/form-data

collection_name: my_collection
service_name:    서비스명 (배열)
screen_name:     화면명  (배열)
version:         버전    (배열)
access_level:    접근권한 (배열)
text_content:    화면 설명 텍스트 (배열)
```

---

### POST `/api/rag/search`

저장된 데이터에서 쿼리와 가장 유사한 화면 정보를 검색합니다. 순수 벡터 검색과 하이브리드 검색(BM25 + 벡터 RRF) 두 가지 모드를 지원합니다.

```http
POST /api/rag/search
Content-Type: application/json

{
    "collection_name": "my_collection",
    "query": "검색 버튼이 있는 랭킹 목록 화면",
    "k": 5,
    "search_mode": "vector",
    "filters": {"service_name": "개발자 랭킹 서비스", "access_level": "user"}
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `collection_name` | string | 필수 | 검색할 컬렉션명 |
| `query` | string | 필수 | 검색 쿼리 |
| `k` | int | 5 | 반환할 결과 수 |
| `search_mode` | string | `"vector"` | `"vector"` (순수 벡터) \| `"hybrid"` (벡터+BM25 RRF) |
| `filters` | object | null | JSONB 메타데이터 필터 (예: `{"service_name": "서비스명"}`) |
| `rerank` | bool | `false` | `true`: 크로스인코더 재랭킹 적용 (k×3 오버패치 후 재정렬) |

**응답 예시**
```json
{
    "results": [
        {
            "content": "화면 분석 텍스트...",
            "metadata": {
                "service_name": "개발자 랭킹 서비스",
                "screen_name": "깃허브 전체 랭킹목록 페이지",
                "version": "3.1.1"
            },
            "score": 0.9123
        }
    ]
}
```

---

### POST `/api/rag/analyze/code`

소스코드를 분석하여 영향받는 화면을 탐지하고 테스트 영향도 리포트를 생성합니다.

```http
POST /api/rag/analyze/code
Content-Type: application/json

{
    "collection_name": "my_collection",
    "code": "def authenticate_user(username, password):\n    ...",
    "k": 5,
    "filters": {"service_name": "인증 서비스"}
}
```

**처리 흐름**
1. LLM으로 코드 기능 요약
2. 요약 텍스트 임베딩 → RAG 검색으로 관련 화면 탐색
3. LLM으로 영향도 분석 리포트 생성

**응답 예시**
```json
{
    "related_screens": [
        {
            "content": "로그인 화면 분석...",
            "metadata": {"screen_name": "로그인", "service_name": "인증 서비스"},
            "score": 0.7688
        }
    ],
    "analysis": "## 영향 화면\n- 로그인 화면 (우선순위: 높음)\n- 회원가입 화면 (우선순위: 중간)\n\n## 테스트 항목\n..."
}
```

---

### GET `/api/rag/graph/service/{service_name}`

AGE 그래프에서 특정 서비스에 속한 화면 전체 목록을 조회합니다.

```http
GET /api/rag/graph/service/개발자%20랭킹%20서비스
GET /api/rag/graph/service/개발자%20랭킹%20서비스?version=1.0.0
```

**응답 예시**
```json
{
    "screens": [
        {
            "screen_name": "깃허브 전체 랭킹목록 페이지",
            "content": "화면 분석 텍스트...",
            "metadata": {"service_name": "개발자 랭킹 서비스", "version": "1.0.0", "access_level": "user"}
        }
    ],
    "total": 4
}
```

---

### GET `/api/rag/graph/screen/{collection_name}/{screen_name}/related`

AGE 그래프에서 지정한 화면과 같은 서비스에 속한 연관 화면을 조회합니다.

```http
GET /api/rag/graph/screen/my_collection/깃허브%20전체%20랭킹목록%20페이지/related
```

**응답 예시**
```json
{
    "screens": [
        {
            "screen_name": "백준 전체 랭킹 목록 페이지",
            "content": "화면 분석 텍스트...",
            "metadata": {"service_name": "개발자 랭킹 서비스", "version": "1.0.0"}
        }
    ],
    "total": 3
}
```

---

### GET `/api/rag/health`

DB 및 Redis 실제 연결 상태를 확인합니다. 모두 정상이면 `200 OK`, 하나라도 실패하면 `503 Degraded`를 반환합니다.

```http
GET /api/rag/health
```

**정상 응답 (200)**
```json
{ "status": "ok", "db": "ok", "redis": "ok" }
```

**장애 응답 (503)**
```json
{ "status": "degraded", "db": "ok", "redis": "error: Connection refused" }
```

---

### GET `/metrics`

Prometheus 메트릭 엔드포인트입니다. `prometheus-fastapi-instrumentator`가 HTTP 요청 메트릭을 자동 수집하며, RAG 서비스 커스텀 메트릭도 포함됩니다.

```http
GET /metrics
```

**주요 커스텀 메트릭**

| 메트릭 | 타입 | 설명 |
|--------|------|------|
| `rag_cache_hits_total{collection}` | Counter | 캐시 히트 수 (컬렉션별) |
| `rag_cache_misses_total{collection}` | Counter | 캐시 미스 수 (컬렉션별) |
| `rag_llm_requests_total` | Counter | LLM API 호출 수 |
| `rag_embedding_requests_total` | Counter | 임베딩 API 호출 수 |
| `rag_search_latency_seconds{search_mode}` | Histogram | 검색 지연 시간 (버킷: 0.1~10s) |
| `http_requests_total` | Counter | FastAPI HTTP 요청 수 (자동 수집) |

---

## LLM 분석 결과 구조

GPT-4o가 화면을 분석하면 아래 JSON 구조로 결과를 반환하고, 이를 LangChain Document로 변환하여 그래프 저장합니다.

```json
{
    "input_metadata": {
        "service_name": "개발자 랭킹 서비스",
        "screen_name": "깃허브 전체 랭킹목록 페이지",
        "version": "3.1.1",
        "access_level": "user"
    },
    "screen_analysis": {
        "visible_title": "GitHub 랭킹",
        "screen_type": "목록",
        "layout_description": "상단 검색바 + 랭킹 테이블",
        "primary_purpose": "GitHub 기여도 기준 개발자 랭킹을 조회하는 화면"
    },
    "extracted_elements": {
        "all_visible_text": ["랭킹", "검색", "닉네임", "..."],
        "button_texts": ["검색", "비교"],
        "field_labels": ["닉네임 입력"],
        "menu_items": ["GitHub 랭킹", "백준 랭킹", "취업 현황"]
    },
    "ui_components": {
        "has_form": true,
        "has_table": true,
        "has_search": true,
        "has_charts": false
    },
    "functional_indicators": {
        "crud_operations": {
            "create": "없음",
            "read": "랭킹 목록 조회",
            "update": "없음",
            "delete": "없음"
        },
        "user_actions": ["닉네임으로 유저 검색", "랭킹 상세 조회"]
    },
    "search_keywords": ["GitHub", "랭킹", "개발자", "검색", "목록"]
}
```

---

## 환경 변수

`.env.example`을 복사하여 `.env`로 사용합니다.

```bash
cp .env.example .env
```

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `GOOGLE_API_KEY` | Google AI API 키 | (필수) |
| `VECTOR_DB_HOST` | PostgreSQL 호스트 | `postgres` |
| `VECTOR_DB_PORT` | 포트 | `5432` |
| `VECTOR_DB_NAME` | 데이터베이스명 | `biz_rag` |
| `VECTOR_DB_USER` | DB 사용자 | `postgres` |
| `VECTOR_DB_PASSWORD` | DB 비밀번호 | `postgres` |
| `REDIS_HOST` | Redis 호스트 (미설정 시 NullCacheClient 사용) | — |
| `REDIS_PORT` | Redis 포트 | `6379` |
| `REDIS_DB` | Redis DB 번호 | `0` |
| `REDIS_PASSWORD` | Redis 비밀번호 | — |

---

## 실행 방법

### Docker Compose (권장)

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일에서 GOOGLE_API_KEY 입력

# 2. 전체 스택 실행 (PostgreSQL + FastAPI)
docker-compose up -d

# 3. 로그 확인
docker-compose logs -f app
```

서버 주소: `http://localhost:8000`
Swagger UI: `http://localhost:8000/docs`

### 코드 변경 시 재시작

앱 코드는 볼륨 마운트되어 있으므로 재빌드 없이 재시작만 하면 됩니다.

```bash
docker compose restart app
```

---

## 데이터베이스 초기화

`init-db.sh`가 Docker 컨테이너 최초 실행 시 자동으로 실행됩니다.

- `biz_rag` DB: `pgvector` 확장 + Apache AGE 확장 + 그래프(`biz_rag_graph`) 생성
- `biz_table` DB: `pgvector` 확장 설치

볼륨이 이미 존재하여 자동 초기화가 안 된 경우 수동으로 실행합니다.

```bash
docker exec backend_ai_postgres psql -U postgres -c "CREATE DATABASE biz_rag;"
docker exec backend_ai_postgres psql -U postgres -d biz_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec backend_ai_postgres psql -U postgres -d biz_rag -c "CREATE EXTENSION IF NOT EXISTS age;"
docker exec backend_ai_postgres psql -U postgres -d biz_rag -c \
  "LOAD 'age'; SET search_path = ag_catalog, '\$user', public; SELECT create_graph('biz_rag_graph');"
docker exec backend_ai_postgres psql -U postgres -c "CREATE DATABASE biz_table;"
docker exec backend_ai_postgres psql -U postgres -d biz_table -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

---

## 의존성 주입 구조

`DIContainer`는 인터페이스와 구현체를 런타임에 매핑하는 경량 컨테이너입니다.

```python
# main.py lifespan에서 등록
DIContainer.register(RagRepository, AgeRepositoryImpl())
DIContainer.register(LlmClient, GoogleChatClient())
DIContainer.register(RagGenerationService, RagGenerationService())

# 서비스/컨트롤러에서 사용
service = DIContainer.get(RagGenerationService)
```

---

## 주요 설계 결정사항

- **그래프 저장**: Apache AGE Cypher 쿼리로 `Screen` 노드와 `Service` 노드를 생성하고 `BELONGS_TO` 관계로 연결
- **이중 저장 구조**: AGE 그래프(관계 저장) + pgvector `rag_embeddings` 테이블(임베딩 저장) 역할 분리
- **비동기 병렬 처리**: `asyncio.gather()`로 다수 이미지·텍스트 LLM 분석을 동시 실행, DB/임베딩 동기 작업은 `asyncio.to_thread()`로 이벤트 루프 블로킹 방지
- **싱글톤 클라이언트**: `GoogleChatClient`, `GoogleEmbeddingClient`, `PGVectorManager` 모두 클래스 변수로 단일 인스턴스 유지
- **수동 임베딩**: Apache AGE는 LangChain의 임베딩 자동 처리를 지원하지 않으므로 `embed_documents()` / `embed_query()`를 직접 호출
- **halfvec + HNSW 인덱스**: 임베딩을 `halfvec(3072)` 타입(float16)으로 저장하여 메모리를 50% 절약하고 HNSW 인덱스(`halfvec_cosine_ops`) 지원. `vector(3072)`는 최대 2000차원까지만 hnsw/ivfflat 인덱스를 지원하지만 `halfvec`은 16000차원까지 지원하여 3072차원에서도 O(log n) ANN 검색 가능
- **하이브리드 검색**: tsvector + GIN 인덱스로 BM25 키워드 검색, RRF(Reciprocal Rank Fusion)로 벡터 결과와 결합
- **크로스인코더 재랭킹**: `rerank=true` 요청 시 k×3 결과를 오버패치한 뒤 `BAAI/bge-reranker-base` 크로스인코더로 재정렬. 바이인코더(임베딩 검색)는 속도 최적화된 근사 검색이지만, 크로스인코더는 쿼리-문서 쌍을 함께 인코딩하여 더 정밀한 관련도 판단 가능 (품질 ↑, 응답 시간 ↑ 트레이드오프)
- **AGE Cypher 파라미터 바인딩**: `$param` 방식 + JSON 직렬화로 LLM 생성 텍스트의 특수문자·따옴표 안전 처리
- **커넥션 풀 안전성**: `@contextmanager` 기반 `get_cursor()`로 자동 commit/rollback/반납 (멀티스레드 안전)

---

## E2E 테스트 결과 (2026-03-01)

전체 플로우 정상 동작 확인 완료.

### 텍스트 저장 → 검색

```bash
# 1. 텍스트 저장
curl -X POST http://localhost:8000/api/rag/add/text \
  -F "collection_name=test_collection" \
  -F "service_name=test_service" \
  -F "screen_name=home" \
  -F "version=1.0.0" \
  -F "access_level=public" \
  -F "text_content=FastAPI는 Python으로 빠른 API를 만드는 현대적인 웹 프레임워크입니다."
# Response: {"result":"ok"}

# 2. 검색
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "test_collection", "query": "FastAPI 웹 프레임워크", "k": 3}'
# Response: {"results": [...]} (score: 0.7229)
```

### 이미지 업로드 → 검색

```bash
# 1. 이미지 업로드 (Gemini가 자동 분석)
curl -X POST http://localhost:8000/api/rag/add/vector \
  -F "collection_name=image_collection" \
  -F "service_name=test_service" \
  -F "screen_name=main_screen" \
  -F "version=1.0.0" \
  -F "access_level=public" \
  -F "images=@./test_images/1.png"
# Response: {"result":"ok"}

# 2. 검색
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"collection_name": "image_collection", "query": "메인 화면 UI 구성", "k": 3}'
# Response: {"results": [...]} (score: 0.7863)
```

### 하이브리드 검색

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my_collection",
    "query": "로그인 화면",
    "k": 3,
    "search_mode": "hybrid"
  }'
# hybrid 모드 RRF score 예시: login(0.0328), signup(0.0161)
```

### 소스코드 영향도 분석

```bash
curl -X POST http://localhost:8000/api/rag/analyze/code \
  -H "Content-Type: application/json" \
  -d '{
    "collection_name": "my_collection",
    "code": "def authenticate_user(username, password):\n    user = db.query(User).filter(User.username == username).first()\n    if not user or not verify_password(password, user.hashed_password):\n        raise HTTPException(status_code=401)\n    return user",
    "k": 5
  }'
# Response: {"related_screens": [...], "analysis": "## 영향 화면\n- 로그인 화면 (우선순위: 높음)..."}
```

### 그래프 탐색

```bash
# 서비스에 속한 화면 전체 조회
curl "http://localhost:8000/api/rag/graph/service/%EA%B0%9C%EB%B0%9C%EC%9E%90%20%EB%9E%AD%ED%82%B9%20%EC%84%9C%EB%B9%84%EC%8A%A4"
# Response: {"screens": [...], "total": 4}

# 특정 화면의 연관 화면 탐색
curl "http://localhost:8000/api/rag/graph/screen/my_collection/%EA%B9%83%ED%97%88%EB%B8%8C%20%EC%A0%84%EC%B2%B4%20%EB%9E%AD%ED%82%B9%EB%AA%A9%EB%A1%9D%20%ED%8E%98%EC%9D%B4%EC%A7%80/related"
# Response: {"screens": [...], "total": 3}
```

---

## 고도화 이력

| 단계 | 내용 | 상태 |
|------|------|------|
| 1단계 | `@contextmanager` 기반 커넥션 풀 안전 관리 | ✅ 완료 |
| 2단계 | pgvector `rag_embeddings` 테이블 + DB 레벨 코사인 검색 | ✅ 완료 |
| 3단계 | JSONB `@>` 메타데이터 필터 검색 | ✅ 완료 |
| 4단계 | `POST /api/rag/analyze/code` 소스코드 영향도 분석 API | ✅ 완료 |
| 5단계 | 하이브리드 검색 (BM25 tsvector + pgvector RRF) | ✅ 완료 |
| 6단계 | asyncio 비동기 처리 전환 (LLM 병렬 호출, to_thread 래핑) | ✅ 완료 |
| 7단계 | `halfvec(3072)` 전환 + HNSW 인덱스 도입 (메모리 50% 절약, ANN 검색) | ✅ 완료 |
| 8단계 | AGE 그래프 탐색 API (서비스별 화면 목록 / 연관 화면 탐색) | ✅ 완료 |
| 9단계 | 크로스인코더 재랭킹 (`BAAI/bge-reranker-base`, `rerank=true` 선택 적용) | ✅ 완료 |
| 10단계 | Redis 캐싱 레이어 도입 (TTL 1시간, SCAN 기반 무효화, NullCacheClient 하위 호환) | ✅ 완료 |
| 11단계 | 모니터링 / 관찰가능성 (structlog JSON 로그, Prometheus 메트릭, `/health` 강화) | ✅ 완료 |
| 12단계 | Grafana 대시보드 연동 (Prometheus + Grafana 컨테이너, RAG 전용 대시보드) | ✅ 완료 |
| 13단계 | API 보안 강화 (X-API-Key 인증, Redis Rate Limiting, /health 공개 유지) | ✅ 완료 |

## 향후 개선 계획

- 멀티모달 임베딩 적용 (이미지 직접 임베딩)
- AGE 그래프 심화 탐색 (다단계 관계 순회, 서비스 간 의존성 분석)
