import os
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
        self.conn = None
        self.cursor = None

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

    def get_cursor(self):
        """새로운 커서를 반환합니다."""
        self.conn = PGVectorManager._engine.connect()
        # psycopg2 커서를 사용하기 위해 raw_connection을 사용합니다.
        self.cursor = self.conn.connection.cursor()
        return self.cursor

    def close_connection(self):
        """현재 커서와 연결을 닫습니다."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

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