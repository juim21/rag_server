from typing import List, Dict, Any, Tuple
import json
from app.core.interface.rag_repository import RagRepository
from app.infra.database import PGVectorManager


def _age_safe_label(collection_name: str) -> str:
    """AGE 노드 레이블용 안전한 이름 반환.
    system_id:collection 형식의 콜론(:)은 이중 언더스코어(__)로 치환.
    pgvector의 collection_name 컬럼값(원본)과 분리하여 사용.
    """
    return collection_name.replace(":", "__")


class AgeRepositoryImpl(RagRepository):

    def __init__(self):
        self.connection_manager = PGVectorManager()
        self.graph_name = 'biz_rag_graph'  # init-db.sh에서 생성한 그래프 이름
        self.connection_manager.ensure_vector_table()  # pgvector 테이블 자동 생성

    def health_check(self) -> bool:
        """DB 연결 상태를 확인합니다. SELECT 1 쿼리로 실제 연결 검증."""
        with self.connection_manager.get_cursor() as cursor:
            cursor.execute("SELECT 1")
        return True

    def _execute_cypher(self, query: str, cypher_params: dict = None):
        """Cypher 쿼리를 실행하는 도우미 함수.
        호출마다 커넥션 풀에서 커넥션을 체크아웃하고, 완료 후 자동 반납합니다.
        cypher_params: Cypher 쿼리 내 $param 자리를 채울 dict. JSON으로 인코딩되어 AGE에 전달됩니다."""
        with self.connection_manager.get_cursor() as cursor:
            # AGE 로드 및 search_path 설정
            cursor.execute("LOAD 'age';")
            cursor.execute("SET search_path = ag_catalog, '$user', public;")

            # Cypher 쿼리 실행 (파라미터가 있으면 AGE 파라미터 바인딩 사용)
            if cypher_params:
                params_json = json.dumps(cypher_params, ensure_ascii=False)
                full_query = f"SELECT * FROM cypher('{self.graph_name}', $$ {query} $$, %s) as (result agtype);"
                cursor.execute(full_query, (params_json,))
            else:
                full_query = f"SELECT * FROM cypher('{self.graph_name}', $$ {query} $$) as (result agtype);"
                cursor.execute(full_query)

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
        AGE 파라미터 바인딩($param)으로 따옴표/특수문자 안전 처리.
        """
        # AGE 레이블에는 콜론(:) 등 특수문자 불가 → _age_safe_label()로 치환
        age_label = _age_safe_label(collection_name)

        for doc in documents:
            content = doc.get("page_content", "")
            embedding = doc.get("embedding", [])
            metadata = doc.get("metadata", {})

            service_name = metadata.get("service_name", "unknown")
            screen_name = metadata.get("screen_name", "unknown")
            version = metadata.get("version", "1.0.0")

            # 1. AGE: Service 노드 MERGE (파라미터 바인딩으로 특수문자 안전 처리)
            service_query = """
            MERGE (s:Service {name: $service_name, version: $version})
            RETURN s
            """
            self._execute_cypher(service_query, {
                "service_name": service_name,
                "version": version
            })

            # 2. AGE: Screen 노드 CREATE + BELONGS_TO 관계 생성
            # age_label은 콜론 제거된 안전한 레이블명, 백틱으로 감싸서 직접 삽입
            screen_query = f"""
            MATCH (s:Service {{name: $service_name, version: $version}})
            CREATE (n:`{age_label}` {{
                content: $content,
                metadata: $metadata_str,
                screen_name: $screen_name
            }})-[:BELONGS_TO]->(s)
            RETURN n
            """
            self._execute_cypher(screen_query, {
                "service_name": service_name,
                "version": version,
                "content": content,
                "metadata_str": json.dumps(metadata, ensure_ascii=False),
                "screen_name": screen_name
            })

            # 3. pgvector 테이블: 임베딩 저장 (검색 전용)
            self.connection_manager.insert_embedding(
                collection_name=collection_name,
                content=content,
                metadata=metadata,
                embedding=embedding,
                image_embedding=doc.get("image_embedding")  # None이면 NULL 저장
            )

    def similarity_search(self, collection_name: str, query_embedding: List[float], k: int = 5,
                          filters: dict = None, search_mode: str = "vector", query_text: str = None,
                          image_embedding: list = None) -> List[Tuple[Dict[str, Any], float]]:
        """
        pgvector 코사인 유사도 검색 또는 하이브리드/비주얼 검색을 수행합니다.
        search_mode='hybrid' + query_text 전달 시 벡터+BM25 RRF 결합 결과를 반환합니다.
        search_mode='visual' + image_embedding 전달 시 CLIP 이미지 임베딩 검색을 수행합니다.
        """
        rows = self.connection_manager.search_similar(
            collection_name, query_embedding, k, filters, search_mode, query_text, image_embedding
        )
        return [
            ({"page_content": row["content"], "metadata": row["metadata"]}, row["score"])
            for row in rows
        ]

    def collection_exists(self, collection_name: str) -> bool:
        """
        pgvector 테이블에 해당 컬렉션 데이터가 있는지 확인합니다.
        """
        return self.connection_manager.collection_exists_in_vector_table(collection_name)

    def get_screens_by_service(self, service_name: str, version: str = None) -> list:
        """
        AGE 그래프에서 서비스에 속한 화면 노드 전체를 조회합니다.
        Screen 노드의 screen_name, content, metadata를 반환합니다.
        """
        if version:
            query = """
            MATCH (n)-[:BELONGS_TO]->(s:Service {name: $service_name, version: $version})
            RETURN n
            """
            params = {"service_name": service_name, "version": version}
        else:
            query = """
            MATCH (n)-[:BELONGS_TO]->(s:Service {name: $service_name})
            RETURN n
            """
            params = {"service_name": service_name}

        rows = self._execute_cypher(query, params)
        result = []
        for row in rows:
            props = row.get("properties", {})
            metadata = props.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            result.append({
                "screen_name": props.get("screen_name", ""),
                "content": props.get("content", ""),
                "metadata": metadata,
            })
        return result

    def get_related_screens(self, collection_name: str, screen_name: str) -> list:
        """
        AGE 그래프에서 같은 서비스에 속한 연관 화면 노드를 조회합니다.
        지정한 screen_name의 화면과 동일 서비스의 다른 화면들을 반환합니다.
        """
        age_label = _age_safe_label(collection_name)
        query = f"""
        MATCH (target:`{age_label}` {{screen_name: $screen_name}})-[:BELONGS_TO]->(s:Service)
        MATCH (other)-[:BELONGS_TO]->(s)
        WHERE id(other) <> id(target)
        RETURN other
        """
        rows = self._execute_cypher(query, {"screen_name": screen_name})
        result = []
        for row in rows:
            props = row.get("properties", {})
            metadata = props.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            result.append({
                "screen_name": props.get("screen_name", ""),
                "content": props.get("content", ""),
                "metadata": metadata,
            })
        return result
