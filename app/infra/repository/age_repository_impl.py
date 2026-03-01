from typing import List, Dict, Any, Tuple
import json
from app.core.interface.rag_repository import RagRepository
from app.infra.database import PGVectorManager


class AgeRepositoryImpl(RagRepository):

    def __init__(self):
        self.connection_manager = PGVectorManager()
        self.graph_name = 'biz_rag_graph'  # init-db.sh에서 생성한 그래프 이름
        self.connection_manager.ensure_vector_table()  # pgvector 테이블 자동 생성

    def _execute_cypher(self, query: str, params: tuple = None):
        """Cypher 쿼리를 실행하는 도우미 함수.
        호출마다 커넥션 풀에서 커넥션을 체크아웃하고, 완료 후 자동 반납합니다."""
        with self.connection_manager.get_cursor() as cursor:
            # AGE 로드 및 search_path 설정
            cursor.execute("LOAD 'age';")
            cursor.execute("SET search_path = ag_catalog, '$user', public;")

            # Cypher 쿼리 실행
            full_query = f"SELECT * FROM cypher('{self.graph_name}', $$ {query} $$) as (result agtype);"
            cursor.execute(full_query, params)

            # agtype 결과를 Python dict/list로 변환하여 반환
            # AGE는 ::vertex, ::edge 등의 타입 접미사를 붙이므로 제거 후 파싱
            rows = cursor.fetchall()
            result = []
            for row in rows:
                s = str(row[0])
                if "::" in s:
                    s = s[:s.rfind("::")]
                result.append(json.loads(s))
            return result

    def save_documents(self, collection_name: str, documents: List[Dict[str, Any]]):
        """
        문서를 두 곳에 저장합니다.
        1. Apache AGE 그래프: Screen 노드와 Service 노드의 BELONGS_TO 관계
        2. pgvector 테이블: 코사인 유사도 검색을 위한 임베딩 저장
        구조: (Screen:collection_name)-[:BELONGS_TO]->(Service)
        """
        for doc in documents:
            content = doc.get("page_content", "")
            embedding = doc.get("embedding", [])
            metadata = doc.get("metadata", {})

            service_name = metadata.get("service_name", "unknown").replace("'", "''")
            screen_name = metadata.get("screen_name", "unknown").replace("'", "''")
            version = metadata.get("version", "1.0.0").replace("'", "''")
            metadata_str = json.dumps(metadata).replace("'", "''")

            # 1. AGE: Service 노드 MERGE
            service_query = """
            MERGE (s:Service {name: '%s', version: '%s'})
            RETURN s
            """ % (service_name, version)
            self._execute_cypher(service_query)

            # 2. AGE: Screen 노드 CREATE + BELONGS_TO 관계 생성
            screen_query = """
            MATCH (s:Service {name: '%s', version: '%s'})
            CREATE (n:%s {
                content: '%s',
                metadata: '%s',
                screen_name: '%s'
            })-[:BELONGS_TO]->(s)
            RETURN n
            """ % (service_name, version, collection_name,
                   content.replace("'", "''"),
                   metadata_str, screen_name)
            self._execute_cypher(screen_query)

            # 3. pgvector 테이블: 임베딩 저장 (검색 전용)
            self.connection_manager.insert_embedding(
                collection_name=collection_name,
                content=content,
                metadata=metadata,
                embedding=embedding
            )

    def similarity_search(self, collection_name: str, query_embedding: List[float], k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        pgvector의 코사인 유사도 연산자(<=>)를 사용하여 DB 레벨에서 ANN 검색을 수행합니다.
        Python 루프 방식 대비 대용량 데이터에서 월등히 빠릅니다.
        """
        rows = self.connection_manager.search_similar(collection_name, query_embedding, k)
        return [
            ({"page_content": row["content"], "metadata": row["metadata"]}, row["score"])
            for row in rows
        ]

    def collection_exists(self, collection_name: str) -> bool:
        """
        pgvector 테이블에 해당 컬렉션 데이터가 있는지 확인합니다.
        """
        return self.connection_manager.collection_exists_in_vector_table(collection_name)
