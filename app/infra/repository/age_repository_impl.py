from typing import List, Dict, Any, Tuple
import json
from app.core.interface.rag_repository import RagRepository
from app.infra.database import PGVectorManager  # 기존 PG 접속 정보 재사용

class AgeRepositoryImpl(RagRepository):
    
    def __init__(self):
        self.connection_manager = PGVectorManager()
        self.graph_name = 'biz_rag_graph'  # init-db.sh에서 생성한 그래프 이름
        self.cursor = self.connection_manager.get_cursor()

    def _execute_cypher(self, query: str, params: tuple = None):
        """Cypher 쿼리를 실행하는 도우미 함수"""
        try:
            # AGE 로드 및 search_path 설정
            self.cursor.execute("LOAD 'age';")
            self.cursor.execute("SET search_path = ag_catalog, '$user', public;")
            
            # Cypher 쿼리 실행
            full_query = f"SELECT * FROM cypher('{self.graph_name}', $$ {query} $$) as (result agtype);"
            self.cursor.execute(full_query, params)

            # agtype 결과를 Python dict/list로 변환하여 반환
            rows = self.cursor.fetchall()
            self.cursor.connection.commit()
            return [json.loads(row[0]) for row in rows]
        except Exception as e:
            print(f"Cypher 쿼리 실행 오류: {e}")
            self.cursor.connection.rollback()
            raise

    def save_documents(self, collection_name: str, documents: List[Dict[str, Any]]):
        """
        문서를 그래프의 노드로 저장합니다.
        - collection_name을 Screen 노드의 라벨로 사용합니다.
        - Service 노드를 MERGE하고 Screen 노드와 BELONGS_TO 관계를 생성합니다.
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

            # 1. Service 노드 MERGE (없으면 생성, 있으면 재사용)
            service_query = """
            MERGE (s:Service {name: '%s', version: '%s'})
            RETURN s
            """ % (service_name, version)
            self._execute_cypher(service_query)

            # 2. Screen 노드 CREATE + Service와 BELONGS_TO 관계 생성
            screen_query = """
            MATCH (s:Service {name: '%s', version: '%s'})
            CREATE (n:%s {
                content: '%s',
                embedding: %s,
                metadata: '%s',
                screen_name: '%s'
            })-[:BELONGS_TO]->(s)
            RETURN n
            """ % (service_name, version, collection_name,
                   content.replace("'", "''"), embedding,
                   metadata_str, screen_name)
            self._execute_cypher(screen_query)

    def similarity_search(self, collection_name: str, query_embedding: List[float], k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        벡터 유사도 검색을 수행합니다.
        AGE는 아직 내장 벡터 검색 기능이 미흡하여, pgvector의 기능을 활용합니다.
        이를 위해, 노드 속성으로 저장된 임베딩 대신 별도의 테이블을 가정하거나,
        이 예제에서는 순수 Python으로 유사도를 계산하는 방식을 보여줍니다.
        (참고: 프로덕션 환경에서는 AGE와 pgvector를 연동하는 고급 전략이 필요합니다.)
        """
        # 1. 모든 문서 노드를 가져옵니다.
        query = f"MATCH (n:{collection_name}) RETURN n"
        nodes = self._execute_cypher(query)

        # 2. 코사인 유사도 계산 (numpy가 있다면 더 효율적)
        def cosine_similarity(v1, v2):
            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm_v1 = sum(a * a for a in v1) ** 0.5
            norm_v2 = sum(b * b for b in v2) ** 0.5
            if norm_v1 == 0 or norm_v2 == 0:
                return 0.0
            return dot_product / (norm_v1 * norm_v2)

        # 3. 유사도 계산 및 정렬
        results = []
        for node_container in nodes:
            node = node_container.get('n', {}).get('properties', {})
            if 'embedding' in node and 'content' in node:
                sim = cosine_similarity(query_embedding, node['embedding'])
                
                # metadata 문자열을 다시 dict로 변환
                metadata = json.loads(node.get('metadata', '{}'))
                
                document = {
                    "page_content": node['content'],
                    "metadata": metadata
                }
                results.append((document, sim))

        # 4. 유사도 높은 순으로 정렬하여 k개 반환
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def collection_exists(self, collection_name: str) -> bool:
        """
        해당 라벨을 가진 노드가 하나라도 있는지 확인하여 컬렉션 존재 여부를 판단합니다.
        """
        query = f"MATCH (n:{collection_name}) RETURN count(n) AS cnt"
        result = self._execute_cypher(query)
        if not result:
            return False
        cnt = result[0]
        if isinstance(cnt, dict):
            return cnt.get("cnt", 0) > 0
        return int(cnt) > 0

    def __del__(self):
        """객체 소멸 시 커서와 커넥션을 닫습니다."""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'connection_manager'):
            self.connection_manager.close_connection()

