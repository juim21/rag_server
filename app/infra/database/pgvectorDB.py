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
        """rag_embeddings 테이블과 인덱스가 없으면 생성합니다. 앱 시작 시 1회 호출.
        embedding 타입: halfvec(3072) — float16 저장으로 메모리 50% 절약, HNSW 인덱스 지원(pgvector 0.7.0+)
        """
        with self.get_cursor() as cursor:
            # halfvec 타입으로 테이블 생성 (신규)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS rag_embeddings (
                    id BIGSERIAL PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB,
                    embedding halfvec({self.EMBEDDING_DIM}),
                    content_tsv TSVECTOR
                );
            """)
            # 기존 vector(3072) 컬럼을 halfvec(3072)으로 마이그레이션 (이미 halfvec이면 무시됨)
            cursor.execute(f"""
                ALTER TABLE rag_embeddings
                ALTER COLUMN embedding TYPE halfvec({self.EMBEDDING_DIM})
                USING embedding::halfvec;
            """)
            # collection_name 필터 인덱스
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS rag_embeddings_collection_idx
                ON rag_embeddings (collection_name);
            """)
            # 기존 테이블에 content_tsv 컬럼이 없을 경우 추가
            cursor.execute("""
                ALTER TABLE rag_embeddings
                ADD COLUMN IF NOT EXISTS content_tsv TSVECTOR;
            """)
            # 전문 검색용 GIN 인덱스 (하이브리드 검색)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS rag_embeddings_tsv_idx
                ON rag_embeddings USING GIN (content_tsv);
            """)
            # halfvec HNSW 인덱스 — 코사인 유사도 기준 ANN 검색 (O(log n))
            # halfvec은 최대 16000차원까지 hnsw/ivfflat 인덱스 지원 (vector는 2000차원 제한)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS rag_embeddings_embedding_hnsw_idx
                ON rag_embeddings USING hnsw (embedding halfvec_cosine_ops);
            """)
            # 19단계: CLIP 이미지 임베딩 컬럼 추가 (512차원, NULL 허용)
            cursor.execute("""
                ALTER TABLE rag_embeddings
                ADD COLUMN IF NOT EXISTS image_embedding vector(512);
            """)
            # 부분 인덱스: image_embedding이 있는 행만 인덱싱하여 공간 절약
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS rag_embeddings_image_emb_hnsw_idx
                ON rag_embeddings USING hnsw (image_embedding vector_cosine_ops)
                WHERE image_embedding IS NOT NULL;
            """)

    def insert_embedding(self, collection_name: str, content: str, metadata: dict, embedding: list,
                         image_embedding: list = None):
        """pgvector 테이블에 임베딩과 콘텐츠를 삽입합니다. content_tsv도 자동 생성합니다.
        image_embedding: CLIP 이미지 임베딩(512차원). None이면 NULL 저장.
        """
        import json
        with self.get_cursor() as cursor:
            if image_embedding is not None:
                cursor.execute(
                    """INSERT INTO rag_embeddings
                       (collection_name, content, metadata, embedding, content_tsv, image_embedding)
                       VALUES (%s, %s, %s, %s::halfvec, to_tsvector('simple', %s), %s::vector)""",
                    (collection_name, content, json.dumps(metadata), embedding, content, image_embedding)
                )
            else:
                cursor.execute(
                    """INSERT INTO rag_embeddings
                       (collection_name, content, metadata, embedding, content_tsv, image_embedding)
                       VALUES (%s, %s, %s, %s::halfvec, to_tsvector('simple', %s), NULL)""",
                    (collection_name, content, json.dumps(metadata), embedding, content)
                )

    def _build_filter_clause(self, filters: dict) -> tuple:
        """filters dict를 WHERE 절 조건과 파라미터 리스트로 변환합니다."""
        import json
        conditions = []
        params = []
        if filters:
            conditions.append("metadata @> %s::jsonb")
            params.append(json.dumps(filters))
        return conditions, params

    def _visual_search(self, collection_name: str, query_image_embedding: list, k: int, filters: dict) -> list:
        """CLIP image_embedding 컬럼에 대한 코사인 유사도 검색.
        image_embedding이 NULL인 행은 제외합니다.
        """
        import json
        filter_conditions, filter_params = self._build_filter_clause(filters)
        conditions = ["collection_name = %s", "image_embedding IS NOT NULL"] + filter_conditions
        where_clause = " AND ".join(conditions)
        params = [query_image_embedding, collection_name] + filter_params + [query_image_embedding, k]

        sql = f"""
            SELECT content, metadata, 1 - (image_embedding <=> %s::vector) AS score
            FROM rag_embeddings
            WHERE {where_clause}
            ORDER BY image_embedding <=> %s::vector
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            {"content": row[0],
             "metadata": row[1] if isinstance(row[1], dict) else json.loads(row[1]),
             "score": float(row[2])}
            for row in rows
        ]

    def search_similar(self, collection_name: str, query_embedding: list, k: int = 5,
                       filters: dict = None, search_mode: str = "vector", query_text: str = None,
                       image_embedding: list = None) -> list:
        """벡터 유사도 검색 또는 하이브리드/비주얼 검색을 수행합니다.
        search_mode: 'vector' (기본) | 'hybrid' (벡터+BM25 RRF) | 'visual' (CLIP 이미지 임베딩)
        image_embedding: visual 모드에서 사용할 CLIP 벡터(512차원)
        """
        if search_mode == "visual" and image_embedding is not None:
            return self._visual_search(collection_name, image_embedding, k, filters)
        if search_mode == "hybrid" and query_text:
            return self._hybrid_search(collection_name, query_embedding, query_text, k, filters)
        return self._vector_search(collection_name, query_embedding, k, filters)

    def _vector_search(self, collection_name: str, query_embedding: list, k: int, filters: dict) -> list:
        """pgvector 코사인 유사도 순수 벡터 검색."""
        import json
        filter_conditions, filter_params = self._build_filter_clause(filters)
        conditions = ["collection_name = %s"] + filter_conditions
        where_clause = " AND ".join(conditions)
        params = [query_embedding, collection_name] + filter_params + [query_embedding, k]

        sql = f"""
            SELECT content, metadata, 1 - (embedding <=> %s::halfvec) AS score
            FROM rag_embeddings
            WHERE {where_clause}
            ORDER BY embedding <=> %s::halfvec
            LIMIT %s
        """
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            {"content": row[0], "metadata": row[1] if isinstance(row[1], dict) else json.loads(row[1]), "score": float(row[2])}
            for row in rows
        ]

    def _hybrid_search(self, collection_name: str, query_embedding: list, query_text: str, k: int, filters: dict) -> list:
        """벡터 검색 + BM25 키워드 검색 결과를 RRF(Reciprocal Rank Fusion)로 결합합니다."""
        import json
        filter_conditions, filter_params = self._build_filter_clause(filters)
        base_conditions = ["collection_name = %s"] + filter_conditions
        where_clause = " AND ".join(base_conditions)

        candidate_k = k * 3  # 각 검색에서 충분한 후보 확보
        base_params = [collection_name] + filter_params

        sql = f"""
            WITH vector_ranks AS (
                SELECT id, content, metadata,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> %s::halfvec) AS rank
                FROM rag_embeddings
                WHERE {where_clause}
                ORDER BY embedding <=> %s::halfvec
                LIMIT %s
            ),
            keyword_ranks AS (
                SELECT id, content, metadata,
                       ROW_NUMBER() OVER (ORDER BY ts_rank(content_tsv, plainto_tsquery('simple', %s)) DESC) AS rank
                FROM rag_embeddings
                WHERE {where_clause}
                AND content_tsv @@ plainto_tsquery('simple', %s)
                ORDER BY ts_rank(content_tsv, plainto_tsquery('simple', %s)) DESC
                LIMIT %s
            )
            SELECT
                COALESCE(v.id, k.id) AS id,
                COALESCE(v.content, k.content) AS content,
                COALESCE(v.metadata, k.metadata) AS metadata,
                COALESCE(1.0 / (60 + v.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0) AS rrf_score
            FROM vector_ranks v
            FULL OUTER JOIN keyword_ranks k ON v.id = k.id
            ORDER BY rrf_score DESC
            LIMIT %s
        """
        params = (
            [query_embedding] + base_params + [query_embedding, candidate_k] +  # vector_ranks
            [query_text] + base_params + [query_text, query_text, candidate_k] +  # keyword_ranks
            [k]
        )

        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [
            {"content": row[1], "metadata": row[2] if isinstance(row[2], dict) else json.loads(row[2]), "score": float(row[3])}
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