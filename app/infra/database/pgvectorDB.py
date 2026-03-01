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