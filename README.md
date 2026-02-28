# Application Analysis RAG Service

## 서비스 개요

애플리케이션 화면 이미지(또는 텍스트 설명)를 GPT-4o Vision으로 분석하고, 분석 결과를 벡터 임베딩으로 변환하여 **Apache AGE(그래프 DB)** 에 저장하는 RAG(Retrieval-Augmented Generation) 구축 서비스입니다.

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
  │       ├─► OpenAIChatClient          (GPT-4o Vision 이미지 분석)
  │       ├─► OpenAIEmbeddingClient     (text-embedding-3-small 임베딩)
  │       └─► RagRepository            (Apache AGE 저장/검색)
  │               │
  │               └─► PGVectorManager  (PostgreSQL 연결풀, psycopg3)
  │
  └─► OpenAI API (GPT-4o, text-embedding-3-small)
```

### 레이어 구조 (Clean Architecture)

| 레이어 | 역할 |
|--------|------|
| `api/` | HTTP 요청/응답 처리, 라우팅 |
| `core/interface/` | Repository·LLM 추상 인터페이스 정의 |
| `core/service/` | 비즈니스 로직 (이미지 분석, 임베딩, 저장/검색 흐름) |
| `infra/database/` | PostgreSQL 연결풀 관리 (SQLAlchemy + QueuePool) |
| `infra/repository/` | RagRepository 구현체 (Apache AGE Cypher 기반) |
| `infra/external/` | OpenAI LLM·임베딩 클라이언트 (싱글톤) |
| `config/` | DB 설정, LLM 프롬프트 |
| `di_container.py` | 경량 DI 컨테이너 (인터페이스 → 구현체 매핑) |

### 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | FastAPI 0.115, Python 3.11, Uvicorn |
| Graph DB | PostgreSQL + Apache AGE 1.6.0 (Cypher 쿼리) |
| Vector | PostgreSQL + pgvector 0.8.1 (임베딩 저장) |
| AI/ML | OpenAI GPT-4o (Vision), text-embedding-3-small |
| Framework | LangChain 0.2 |
| ORM | SQLAlchemy 2.0, psycopg3 |
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
│   │       ├── llm/openai_client.py          # OpenAI GPT-4o 클라이언트
│   │       └── embedding/openai_embedding_client.py  # OpenAI 임베딩 클라이언트
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
2. ThreadPoolExecutor (max_workers=5)로 GPT-4o Vision 병렬 분석
3. 분석 결과를 LangChain Document로 변환
4. OpenAI 임베딩 생성 후 Apache AGE 그래프 노드로 저장

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

저장된 데이터에서 쿼리와 가장 유사한 화면 정보를 검색합니다.

```http
POST /api/rag/search
Content-Type: application/json

{
    "collection_name": "my_collection",
    "query": "검색 버튼이 있는 랭킹 목록 화면",
    "k": 5
}
```

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

### GET `/api/rag/health`

```http
GET /api/rag/health

Response: { "status": "healthy", "service": "rag-generation" }
```

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
| `OPENAI_API_KEY` | OpenAI API 키 | (필수) |
| `VECTOR_DB_HOST` | PostgreSQL 호스트 | `postgres` |
| `VECTOR_DB_PORT` | 포트 | `5432` |
| `VECTOR_DB_NAME` | 데이터베이스명 | `biz_rag` |
| `VECTOR_DB_USER` | DB 사용자 | `postgres` |
| `VECTOR_DB_PASSWORD` | DB 비밀번호 | `postgres` |

---

## 실행 방법

### Docker Compose (권장)

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일에서 OPENAI_API_KEY 입력

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
DIContainer.register(LlmClient, OpenAIChatClient())
DIContainer.register(RagGenerationService, RagGenerationService())

# 서비스/컨트롤러에서 사용
service = DIContainer.get(RagGenerationService)
```

---

## 주요 설계 결정사항

- **그래프 저장**: Apache AGE Cypher 쿼리로 `Screen` 노드와 `Service` 노드를 생성하고 `BELONGS_TO` 관계로 연결
- **병렬 처리**: 다수의 이미지를 분석할 때 `ThreadPoolExecutor(max_workers=5)`로 OpenAI API 요청을 병렬 처리
- **싱글톤 클라이언트**: `OpenAIChatClient`, `OpenAIEmbeddingClient`, `PGVectorManager` 모두 클래스 변수로 단일 인스턴스 유지
- **수동 임베딩**: Apache AGE는 LangChain의 임베딩 자동 처리를 지원하지 않으므로 `embed_documents()` / `embed_query()`를 직접 호출
- **코사인 유사도 검색**: AGE 내장 벡터 검색 미지원으로 Python에서 직접 코사인 유사도 계산 후 상위 k개 반환

---

## 향후 개선 계획

- `asyncio` 기반 비동기 처리로 전환 (현재 ThreadPoolExecutor 사용)
- 메타데이터 필터링·복합 조건 검색 지원
- AGE + pgvector 연동을 통한 네이티브 벡터 검색 적용
- 소스코드 API 단위 분석 및 화면 매핑 RAG 구축
