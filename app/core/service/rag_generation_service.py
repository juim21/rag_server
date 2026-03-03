import asyncio
import hashlib
import json
import base64
from typing import List, Dict

import structlog
from starlette.datastructures import FormData
from langchain.prompts import ChatPromptTemplate
from langchain_core.documents import Document

from app.di_container import DIContainer
from app.core.interface import RagRepository
from app.core.interface.llm_client import LlmClient
from app.core.interface.cache_client import CacheClient
from app.core.interface.multimodal_embedding_client import MultimodalEmbeddingClient
from app.core.service.data_extractor import ImageExtractor
from app.config.prompt import app_analysis_prompt_user, app_analysis_prompt_system
from app.infra.monitoring.metrics import (
    cache_hits, cache_misses,
    llm_requests, embedding_requests,
    search_latency,
)

logger = structlog.get_logger()

_CACHE_TTL = 3600  # 1시간
_EMBED_BATCH_SIZE = 20  # Google AI API 배치 크기


def _make_search_key(collection_name: str, query: str, k: int,
                     search_mode: str, rerank: bool, filters: dict) -> str:
    raw = f"{query}|{k}|{search_mode}|{rerank}|{json.dumps(filters, sort_keys=True)}"
    digest = hashlib.md5(raw.encode()).hexdigest()
    return f"rag:search:{collection_name}:{digest}"


class RagGenerationService:

    def __init__(self):
        from app.infra.external.embedding.google_embedding_client import GoogleEmbeddingClient
        from app.core.interface.rerank_client import RerankClient

        self.imageExtractor = ImageExtractor()
        self.vector_repository = DIContainer.get(RagRepository)
        self.llm_client = DIContainer.get(LlmClient)
        self.rerank_client = DIContainer.get(RerankClient)
        self.cache_client: CacheClient = DIContainer.get(CacheClient)
        self.embedding_client = GoogleEmbeddingClient()
        self.clip_client: MultimodalEmbeddingClient = DIContainer.get(MultimodalEmbeddingClient)

    # 대량의 데이터를 업로드 하는 방식 - 특정 디렉토리에 파일을 일괄로 저장 및 파일별 입력 데이터를 일괄로 업로드
    async def generation_rag(self, collection_name: str):
        directory_path = "./test_images"
        test_data = self._test_input_data()
        image_list = self.imageExtractor.image_to_base64(directory_path)

        data_items = []
        for temp in image_list:
            key = temp['filename'].split(".")[0]
            meta = test_data[key]
            data_items.append({
                "service_name": meta['service_name'],
                "screen_name": meta['screen_name'],
                "version": meta['version'],
                "access_level": meta['access_level'],
                "filename": temp['filename'],
                "image": temp['base64'],
            })

        tasks = [self._call_llm_with_image(item) for item in data_items]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        result = []
        for r in results_raw:
            if isinstance(r, Exception):
                logger.error("llm_image_failed", error=str(r))
            else:
                result.append(r)

        application_docuement_list = self.imageExtractor.create_column_document(result)
        logger.info("generation_rag", collection_name=collection_name, doc_count=len(application_docuement_list))

        await asyncio.to_thread(self._insert_to_collection, collection_name, application_docuement_list)

    # 기존에 있는 컬렉션에 데이터 임베딩 (멀티파트 이미지)
    async def add_rag_data(self, collection_name: str, formData: FormData):
        service_names = formData.getlist("service_name")
        screen_names = formData.getlist("screen_name")
        versions = formData.getlist("version")
        access_levels = formData.getlist("access_level")
        images = formData.getlist("images")

        data_items = []
        for i in range(len(service_names)):
            data_items.append({
                "service_name": service_names[i],
                "screen_name": screen_names[i],
                "version": versions[i],
                "access_level": access_levels[i],
                "image": base64.b64encode(images[i].file.read()).decode("utf-8"),
                "filename": images[i].filename
            })

        tasks = [self._call_llm_with_image(item) for item in data_items]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        result = []
        base64_images_filtered = []
        for i, r in enumerate(results_raw):
            if isinstance(r, Exception):
                error_type = type(r).__name__
                if "OpenAI" in error_type or "API" in str(r):
                    logger.error("add_rag_data_api_error", error=str(r)[:150])
                elif "JSON" in str(r):
                    logger.error("add_rag_data_json_error", error=str(r)[:100])
                elif "timeout" in str(r).lower():
                    logger.error("add_rag_data_timeout")
                else:
                    logger.error("add_rag_data_error", error_type=error_type, error=str(r)[:100])
            else:
                result.append(r)
                base64_images_filtered.append(data_items[i]["image"])

        application_docuement_list = self.imageExtractor.create_column_document(result)
        await asyncio.to_thread(self._insert_to_collection, collection_name,
                                application_docuement_list, base64_images_filtered)
        await self.cache_client.delete_pattern(f"rag:search:{collection_name}:*")

    # 기존에 있는 컬렉션에 텍스트 데이터 임베딩 (멀티파트 텍스트)
    async def add_rag_text_data(self, collection_name: str, formData: FormData):
        service_names = formData.getlist("service_name")
        screen_names = formData.getlist("screen_name")
        versions = formData.getlist("version")
        access_levels = formData.getlist("access_level")
        text_contents = formData.getlist("text_content")

        data_items = []
        for i in range(len(service_names)):
            data_items.append({
                "service_name": service_names[i],
                "screen_name": screen_names[i],
                "version": versions[i],
                "access_level": access_levels[i],
                "text_content": text_contents[i]
            })

        tasks = [self._response_llm_text_data(item) for item in data_items]
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        result = []
        for r in results_raw:
            if isinstance(r, Exception):
                error_type = type(r).__name__
                if "OpenAI" in error_type or "API" in str(r):
                    logger.error("add_rag_text_api_error", error=str(r)[:150])
                elif "JSON" in str(r):
                    logger.error("add_rag_text_json_error", error=str(r)[:100])
                elif "timeout" in str(r).lower():
                    logger.error("add_rag_text_timeout")
                else:
                    logger.error("add_rag_text_error", error_type=error_type, error=str(r)[:100])
            else:
                result.append(r)

        application_docuement_list = self.imageExtractor.create_column_document(result)
        await asyncio.to_thread(self._insert_to_collection, collection_name, application_docuement_list)
        await self.cache_client.delete_pattern(f"rag:search:{collection_name}:*")

    async def search_rag(self, collection_name: str, query: str, k: int = 5,
                         filters: dict = None, search_mode: str = "vector",
                         rerank: bool = False):
        cache_key = _make_search_key(collection_name, query, k, search_mode, rerank, filters or {})

        cached = await self.cache_client.get(cache_key)
        if cached is not None:
            cache_hits.labels(collection=collection_name).inc()
            logger.info("search_cache_hit", collection_name=collection_name, search_mode=search_mode)
            return json.loads(cached)
        cache_misses.labels(collection=collection_name).inc()

        # 재랭킹 사용 시 충분한 후보를 오버패치
        fetch_k = k * 3 if rerank else k

        if search_mode == "visual":
            clip_emb = await asyncio.to_thread(self.clip_client.embed_text, query)
            with search_latency.labels(search_mode=search_mode).time():
                results = await asyncio.to_thread(
                    self.vector_repository.similarity_search,
                    collection_name, None, fetch_k, filters, "visual", None, clip_emb
                )
        else:
            embedding_requests.inc()
            query_embedding = await asyncio.to_thread(
                self.embedding_client.embeddings.embed_query, query
            )
            with search_latency.labels(search_mode=search_mode).time():
                results = await asyncio.to_thread(
                    self.vector_repository.similarity_search,
                    collection_name, query_embedding, fetch_k, filters,
                    search_mode, query if search_mode == "hybrid" else None
                )

        logger.info("search_rag", collection_name=collection_name, query=query,
                    k=k, search_mode=search_mode, rerank=rerank, result_count=len(results))

        if rerank and results and self.rerank_client:
            docs = [r[0]["page_content"] for r in results]
            reranked_indices = await asyncio.to_thread(
                self.rerank_client.rerank, query, docs, k
            )
            results = [(results[idx][0], score) for idx, score in reranked_indices]

        await self.cache_client.set(cache_key, json.dumps(results), _CACHE_TTL)
        return results

    async def analyze_code_impact(self, collection_name: str, code: str,
                                   k: int = 5, filters: dict = None) -> dict:
        """
        소스코드를 분석하여 영향받는 화면을 탐지하고 테스트 영향도 리포트를 생성합니다.
        1단계: LLM으로 코드 기능 요약
        2단계: 요약 텍스트 임베딩 → RAG 검색으로 관련 화면 탐색
        3단계: LLM으로 영향도 분석 리포트 생성
        """
        from app.config.prompt import code_summary_prompt, code_impact_prompt

        llm_requests.inc()
        summary_prompt = code_summary_prompt.format(code=code)
        code_summary = await self.llm_client.async_llm_request(summary_prompt)

        embedding_requests.inc()
        query_embedding = await asyncio.to_thread(
            self.embedding_client.embeddings.embed_query, code_summary
        )
        related = await asyncio.to_thread(
            self.vector_repository.similarity_search, collection_name, query_embedding, k, filters
        )

        screens_text = "\n\n".join([
            f"[화면 {i+1}] 서비스: {doc['metadata'].get('service_name', '')}, "
            f"화면명: {doc['metadata'].get('screen_name', '')}, 유사도: {round(score, 4)}\n{doc['page_content'][:300]}..."
            for i, (doc, score) in enumerate(related)
        ])

        llm_requests.inc()
        impact_prompt = code_impact_prompt.format(code=code, screens=screens_text if screens_text else "관련 화면 없음")
        analysis = await self.llm_client.async_llm_request(impact_prompt)

        logger.info("analyze_code_impact", collection_name=collection_name,
                    k=k, related_count=len(related))

        return {
            "related_screens": related,
            "analysis": analysis
        }

    async def get_screens_by_service(self, service_name: str, version: str = None) -> list:
        """AGE 그래프에서 서비스에 속한 화면 목록을 조회합니다."""
        v_key = version or "all"
        cache_key = f"rag:graph:service:{service_name}:{v_key}"

        cached = await self.cache_client.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        result = await asyncio.to_thread(
            self.vector_repository.get_screens_by_service, service_name, version
        )
        await self.cache_client.set(cache_key, json.dumps(result), _CACHE_TTL)
        return result

    async def get_related_screens(self, collection_name: str, screen_name: str) -> list:
        """AGE 그래프에서 같은 서비스의 연관 화면을 조회합니다."""
        cache_key = f"rag:graph:screen:{collection_name}:{screen_name}"

        cached = await self.cache_client.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        result = await asyncio.to_thread(
            self.vector_repository.get_related_screens, collection_name, screen_name
        )
        await self.cache_client.set(cache_key, json.dumps(result), _CACHE_TTL)
        return result

    async def search_by_image(self, collection_name: str, base64_image: str,
                               k: int = 5, filters: dict = None) -> list:
        """이미지 파일을 CLIP 인코더로 임베딩하여 시각적으로 유사한 문서를 검색합니다."""
        clip_emb = await asyncio.to_thread(
            self.clip_client.embed_image_base64, base64_image
        )
        results = await asyncio.to_thread(
            self.vector_repository.similarity_search,
            collection_name, None, k, filters, "visual", None, clip_emb
        )
        logger.info("search_by_image", collection_name=collection_name, k=k,
                    result_count=len(results))
        return results

    def _embed_in_batches(self, texts: list) -> list:
        """대량 텍스트를 배치로 나누어 임베딩 처리.
        Google AI API 호출당 _EMBED_BATCH_SIZE개씩 분할하여 API 제한 회피."""
        all_embeddings = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i:i + _EMBED_BATCH_SIZE]
            embedding_requests.inc()
            all_embeddings.extend(
                self.embedding_client.embeddings.embed_documents(batch)
            )
        logger.info("embed_batches_done",
                    total=len(texts),
                    batches=max(1, (len(texts) + _EMBED_BATCH_SIZE - 1) // _EMBED_BATCH_SIZE))
        return all_embeddings

    def _insert_to_collection(self, collection_name: str, documents: List[Document],
                              base64_images: list = None):
        logger.info("insert_to_collection_start", collection_name=collection_name,
                    doc_count=len(documents))

        texts = [doc.page_content for doc in documents]
        embeddings = self._embed_in_batches(texts)

        docs_with_embeddings = []
        for i, (doc, emb) in enumerate(zip(documents, embeddings)):
            image_emb = None
            if base64_images and i < len(base64_images) and base64_images[i] and self.clip_client:
                image_emb = self.clip_client.embed_image_base64(base64_images[i])
            docs_with_embeddings.append({
                "page_content": doc.page_content,
                "embedding": emb,
                "metadata": doc.metadata,
                "image_embedding": image_emb,
            })

        exists = self.vector_repository.collection_exists(collection_name)
        logger.info("insert_to_collection", collection_name=collection_name,
                    collection_exists=exists)

        self.vector_repository.save_documents(collection_name, docs_with_embeddings)

    def _test_input_data(self):
        test_dict = {
            "1": {"service_name": "개발자 랭킹 서비스", "screen_name": "깃허브 전체 랭킹목록 페이지", "version": "3.1.1", "access_level": "user"},
            "2": {"service_name": "개발자 랭킹 서비스", "screen_name": "깃허브 랭킹 닉네임으로 유저 검색", "version": "3.1.1", "access_level": "user"},
            "3": {"service_name": "개발자 랭킹 서비스", "screen_name": "백준 전체 랭킹 목록 페이지", "version": "3.1.1", "access_level": "user"},
            "4": {"service_name": "개발자 랭킹 서비스", "screen_name": "다른 사용자와 랭킹정보 비교 페이지", "version": "3.1.1", "access_level": "user"},
            "5": {"service_name": "개발자 랭킹 서비스", "screen_name": "레포지토리, 리드미 등 사용자 랭킹 정보 상세 조회 페이지", "version": "3.1.1", "access_level": "user"},
            "6": {"service_name": "개발자 랭킹 서비스", "screen_name": "취업 공고를 통해 취업상태 등록 페이지", "version": "3.1.1", "access_level": "user"},
            "7": {"service_name": "개발자 랭킹 서비스", "screen_name": "현재 취업 상태 관리 페이지", "version": "3.1.1", "access_level": "user"},
            "8": {"service_name": "개발자 랭킹 서비스", "screen_name": "공고에 지원한 타 유저 및 평균조회 페이지", "version": "3.1.1", "access_level": "user"},
        }
        return test_dict

    def _create_image_url(self, filename: str, base64_image: str) -> str:
        if filename.lower().endswith('.png'):
            return f"data:image/png;base64,{base64_image}"
        elif filename.lower().endswith('.webp'):
            return f"data:image/webp;base64,{base64_image}"
        else:
            return f"data:image/jpeg;base64,{base64_image}"

    def _delete_code_block(self, sql_response: str) -> str:
        if sql_response.startswith('```json'):
            sql_response = sql_response[7:]
        if sql_response.endswith('```'):
            sql_response = sql_response[:-3]
        return sql_response.strip()

    async def _call_llm_with_image(self, data_item: Dict[str, str]) -> Dict[str, str]:
        """이미지 기반 LLM 호출 (generation_rag, add_rag_data 공통 사용)"""
        llm_requests.inc()
        prompt = ChatPromptTemplate.from_messages([
            ("system", app_analysis_prompt_system),
            ("user", app_analysis_prompt_user)
        ])
        formatted_messages = prompt.format_messages(
            service_name=data_item['service_name'],
            screen_name=data_item['screen_name'],
            version=data_item['version'],
            access_level=data_item['access_level'],
        )
        user_message = formatted_messages[-1]
        user_message.content = [
            {"type": "text", "text": user_message.content},
            {"type": "image_url", "image_url": {"url": self._create_image_url(data_item['filename'], data_item['image'])}}
        ]
        response = self._delete_code_block(
            await self.llm_client.async_llm_request(formatted_messages)
        )
        return json.loads(response)

    async def _response_llm_text_data(self, data_item: Dict[str, str]) -> Dict[str, str]:
        """텍스트 기반 LLM 호출 (add_rag_text_data 사용)"""
        llm_requests.inc()
        prompt = ChatPromptTemplate.from_messages([
            ("system", app_analysis_prompt_system),
            ("user", app_analysis_prompt_user)
        ])
        formatted_messages = prompt.format_messages(
            service_name=data_item['service_name'],
            screen_name=data_item['screen_name'],
            version=data_item['version'],
            access_level=data_item['access_level'],
        )
        user_message = formatted_messages[-1]
        user_message.content = [
            {"type": "text", "text": user_message.content + "\n\n[화면 설명]\n" + data_item['text_content']}
        ]
        response = self._delete_code_block(
            await self.llm_client.async_llm_request(formatted_messages)
        )
        return json.loads(response)
