# Docker Compose 사용 가이드

이 문서는 Docker Compose를 사용하여 Backend AI 프로젝트를 실행하는 방법을 설명합니다.

## 사전 요구사항

- Docker 및 Docker Compose 설치
- OpenAI API Key

## 구성 요소

### 1. PostgreSQL with pgvector (postgres)
- PostgreSQL 16 기반
- pgvector 확장 설치
- 자동으로 `biz_rag` 및 `biz_table` 데이터베이스 생성
- 포트: 5432

### 2. FastAPI Application (app)
- Python 3.11 기반
- RAG 서비스 제공
- 포트: 8000

## 설정 방법

### 1. 환경 변수 설정

`.env` 파일에 OpenAI API Key를 설정하세요:

```bash
# .env.example을 복사하여 .env 파일 생성
cp .env.example .env

# .env 파일을 열어 API Key 설정
OPENAI_API_KEY=your_actual_openai_api_key_here
```

**중요:** `.env` 파일에서 `OPENAI_API_KEY`만 수정하면 됩니다. 다른 환경변수는 Docker Compose에서 자동으로 설정됩니다.

### 2. Docker Compose 실행

```bash
# 백그라운드에서 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그만 확인
docker-compose logs -f app
docker-compose logs -f postgres
```

### 3. 서비스 확인

```bash
# 실행 중인 컨테이너 확인
docker-compose ps

# API 헬스체크
curl http://localhost:8000/docs
```

## 주요 명령어

### 서비스 시작
```bash
docker-compose up -d
```

### 서비스 중지
```bash
docker-compose stop
```

### 서비스 중지 및 제거
```bash
docker-compose down
```

### 볼륨까지 완전히 제거 (데이터베이스 데이터 삭제)
```bash
docker-compose down -v
```

### 재빌드 후 시작
```bash
docker-compose up -d --build
```

### 로그 확인
```bash
# 전체 로그
docker-compose logs -f

# 특정 서비스 로그
docker-compose logs -f app
docker-compose logs -f postgres
```

## 데이터베이스 접속

### Docker 컨테이너 내부에서 접속
```bash
# PostgreSQL 컨테이너에 접속
docker-compose exec postgres psql -U postgres

# biz_rag 데이터베이스 접속
docker-compose exec postgres psql -U postgres -d biz_rag

# biz_table 데이터베이스 접속
docker-compose exec postgres psql -U postgres -d biz_table
```

### 호스트에서 직접 접속
```bash
psql -h localhost -p 5432 -U postgres -d biz_rag
```

## 트러블슈팅

### 포트 충돌
이미 5432 또는 8000 포트를 사용 중인 경우 `docker-compose.yml`에서 포트를 변경하세요:

```yaml
ports:
  - "5433:5432"  # PostgreSQL
  - "8001:8000"  # FastAPI
```

### 데이터베이스 초기화 실패
```bash
# 볼륨 제거 후 재시작
docker-compose down -v
docker-compose up -d
```

### 애플리케이션 로그 확인
```bash
docker-compose logs -f app
```

### pgvector 확장 확인
```bash
docker-compose exec postgres psql -U postgres -d biz_rag -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

## API 문서

서비스 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 개발 모드

코드 변경 시 자동으로 반영하려면 `docker-compose.yml`의 `app` 서비스에 볼륨이 마운트되어 있습니다:

```yaml
volumes:
  - ./app:/testcase-doc-rag/app
```

코드를 수정하면 uvicorn의 auto-reload 기능으로 자동으로 재시작됩니다.

## 프로덕션 배포

프로덕션 환경에서는 다음 사항을 고려하세요:

1. **환경 변수 보안**: `.env` 파일 대신 시크릿 관리 시스템 사용
2. **데이터베이스 비밀번호**: 기본값(`postgres`) 대신 강력한 비밀번호 사용
3. **볼륨 백업**: 정기적인 데이터베이스 백업 설정
4. **리소스 제한**: `docker-compose.yml`에 CPU/메모리 제한 추가
5. **로깅**: 중앙 집중식 로깅 시스템 구축
6. **모니터링**: 헬스체크 및 모니터링 설정

## 파일 구조

```
backend_ai/
├── docker-compose.yml          # Docker Compose 설정
├── Dockerfile                  # FastAPI 애플리케이션 Dockerfile
├── Dockerfile.db               # PostgreSQL + pgvector Dockerfile
├── init-db.sh                  # 데이터베이스 초기화 스크립트
├── .env                        # 환경 변수 (gitignore에 추가됨)
├── .env.example                # 환경 변수 예제
└── app/                        # 애플리케이션 소스 코드
```
