import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv, find_dotenv
from app.config import vector_db_config

load_dotenv(find_dotenv())

class PGVectorManager:
    _engine = None
    _session_factory = None
    _connection_string = None

    def __init__(self):
        if PGVectorManager._engine is None:
            self._initialize_connection_pool()

    def _initialize_connection_pool(self):
        PGVectorManager._connection_string = (
            f"postgresql+psycopg://{vector_db_config['user']}:{vector_db_config['password']}@{vector_db_config['host']}:{vector_db_config['port']}/{vector_db_config['database']}"
        )
        PGVectorManager._engine = create_engine(
            PGVectorManager._connection_string,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True
        )
        PGVectorManager._session_factory = sessionmaker(bind=PGVectorManager._engine)

    EMBEDDING_DIM = 3072  # gemini-embedding-001

    def ensure_vector_table(self):
        """rag_embeddings 테이블과 인덱스가 없으면 생성합니다. 앱 시작 시 1회 호출."""
        with self.get_cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS rag_embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding vector({self.EMBEDDING_DIM})
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS rag_embeddings_collection_idx
                ON rag_embeddings (collection_name);
            """)
            # 주의: pgvector의 ivfflat/hnsw 인덱스는 최대 2000차원까지만 지원
            # gemini-embedding-001은 3072차원이므로 인덱스 없이 순차 검색(exact NN) 사용
            # 향후 차원 축소(output_dimensionality) 적용 시 인덱스 추가 가능

    def insert_embedding(self, collection_name: str, content: str, metadata: dict, embedding: list):
        """pgvector 테이블에 임베딩과 콘텐츠를 삽입합니다."""
        import json
        with self.get_cursor() as cursor:
            cursor.execute(
                "INSERT INTO rag_embeddings (collection_name, content, metadata, embedding) VALUES (%s, %s, %s, %s)",
                (collection_name, content, json.dumps(metadata), embedding)
            )

    def search_similar(self, collection_name: str, query_embedding: list, k: int = 5, filters: dict = None) -> list:
        """pgvector 코사인 유사도 검색. 상위 k개를 (content, metadata, score) 형태로 반환합니다.
        filters: JSONB 포함 조건 (예: {"service_name": "my_service", "access_level": "user"})
        """
        import json
        conditions = ["collection_name = %s"]
        params = [collection_name]

        if filters:
            # JSONB @> 연산자: metadata가 filters를 포함하는 행만 선택
            conditions.append("metadata @> %s::jsonb")
            params.append(json.dumps(filters))

        where_clause = " AND ".join(conditions)
        params_with_vec = [query_embedding] + params + [query_embedding, k]

        sql = f"""
            SELECT content, metadata, 1 - (embedding <=> %s::vector) AS score
            FROM rag_embeddings
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, params_with_vec)
            rows = cursor.fetchall()
        return [
            {"content": row[0], "metadata": row[1] if isinstance(row[1], dict) else json.loads(row[1]), "score": float(row[2])}
            for row in rows
        ]

    def collection_exists_in_vector_table(self, collection_name: str) -> bool:
        """pgvector 테이블에 해당 컬렉션 데이터가 있는지 확인합니다."""
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM rag_embeddings WHERE collection_name = %s LIMIT 1)",
                (collection_name,)
            )
            return cursor.fetchone()[0]

    @contextmanager
    def get_cursor(self):
        """커넥션 풀에서 커넥션을 체크아웃하고 커서를 반환하는 컨텍스트 매니저.
        블록 종료 시 자동으로 커밋/롤백 후 커넥션을 반납합니다."""
        conn = PGVectorManager._engine.connect()
        cursor = conn.connection.cursor()
        try:
            yield cursor
            conn.connection.commit()
        except Exception:
            conn.connection.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @property
    def engine(self):
        return PGVectorManager._engine

    @property
    def connection_string(self):
        return PGVectorManager._connection_string

    @classmethod
    def close_all_connections(cls):
        """모든 커넥션 정리"""
        if cls._engine:
            cls._engine.dispose()
            cls._engine = None
            cls._connection_string = None
            cls._session_factory = None