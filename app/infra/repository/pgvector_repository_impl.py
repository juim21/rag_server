import os
from langchain_core.documents import Document
from app.core.interface import RagRepository
from langchain_postgres import PGVector
from typing import List
from sqlalchemy import text

#db 커넥션
from app.infra.database import PGVectorManager
#임베딩
from app.infra.external.embedding import OpenAIEmbeddingClient

# from app.config import vector_db_config


# vector_db_config = {
#     "host": "localhost",
#     "port": "5432",
#     "database": "biz_rag",
#     "user": "postgres",
#     "password": ""
# }

class PGVectorRepositoryImpl(RagRepository):
    
    
    #디비 접속 정보 및 open AI 키 로드
    def __init__(self):
        
        self.connection_manager = PGVectorManager()
        self.embedding_client = OpenAIEmbeddingClient()
        

    ## 벡터 스토리지가 생성되지 않은 상태이면 해당 방식 사용.
    def build_vector_storage(self, collection_name:str, documents:List[Document]) -> PGVector:
        ## 도큐먼트 받아서 임베딩 후 넣기.
        return PGVector.from_documents(
                    documents=documents,
                    embedding=self.embedding_client.embeddings,
                    connection=self.connection_manager.engine,
                    collection_name=collection_name, #테이블 명이며
                    use_jsonb=True, #메타데이터를 jsonB형식으로 저장. - 이러면 빠른 json 쿼리가 가능함.(안써도 되긴 함. - 얘가 디스크를 더 먹긴함.)
                    pre_delete_collection=True  # 기존 컬렉션 삭제 후 재생성
                )
    
    ## 기존에 이미 구축한 것을 사용하려면 해당 방식
    def existing_vector_store(self, collection_name:str) -> PGVector:
        return PGVector(
                    embeddings=self.embedding_client.embeddings,
                    connection=self.connection_manager.engine,
                    collection_name = collection_name
                )
    #유사도 검색
    def similarity_search_with_score(self, collection_name: str, query:str, k:int = 5) -> List[Document]:
        vector_store = self.existing_vector_store(collection_name)
        return vector_store.similarity_search_with_score(query, k=k)
    
    def similarity_search(self, collection_name: str, query:str, k:int = 5) -> List[tuple]:
        vector_store = self.existing_vector_store(collection_name)
        return vector_store.similarity_search(query, k=k)
    
    ##컬렉션 생성 유무 확인.
    def collection_name_check(self, collection_name:str) -> bool:


        try:
            with self.connection_manager.engine.connect() as conn:
                # 테이블 존재 여부 확인
                table_exists = conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'langchain_pg_collection')")
                ).fetchone()[0]

                # 테이블이 없으면 컬렉션도 없는 것으로 간주
                if not table_exists:
                    return [False]

                result = conn.execute(
                    text("SELECT EXISTS (SELECT 1 FROM langchain_pg_collection WHERE name = :name)"),
                    {"name": collection_name}
                )
                print(str(result))

                collections = [row[0] for row in result]
                return collections

        except Exception as e:
            print(f"컬렉션 조회 실패: {e}")
            return [False]
        
    
