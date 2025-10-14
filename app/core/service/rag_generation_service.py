from app.di_container import DIContainer
from app.core.interface import RagRepository
import json
from starlette.datastructures import FormData
from app.core.service.data_extractor import ImageExtractor
from app.core.interface.llm_client import LlmClient
from app.config.prompt import app_analysis_prompt_user, app_analysis_prompt_system
from langchain.prompts import ChatPromptTemplate
from typing import List, Dict
import concurrent.futures
from langchain_core.documents import Document
import base64


class RagGenerationService:
    
    def __init__(self):
    
        self.imageExtractor = ImageExtractor()
        self.vector_repository = DIContainer.get(RagRepository)
        self.llm_client = DIContainer.get(LlmClient)
    
    #대량의 데이터를 업로드 하는 방식 - 특정 디렉토리에 파일을 일괄로 저장 및 파일별 입력 데이터를 일괄로 업로드
    def generation_rag(self, collection_name : str):

        #디렉토리 - 임시로 지정
        directory_path = "./test_images"
        
        #데이터 임시로 읽어오기.
        test_data = self._test_input_data()
        
        #1. 이미지데이터 읽어오기 - 딕셔너리 형태.
        image_list = self.imageExtractor.image_to_base64(directory_path)
        
        result = []
        
        #2. llm에 요청해서 이미지 분석텍스트 받아오기
        # 한번에 다량의 이미지를 넘기는 경우, 속도가 느려서 멀티스레드로 처리
        # TODO : 추후에 asyncio로 개선 필요.
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 모든 작업을 스레드풀에 제출
            futures = [
                executor.submit(self._response_llm_data, temp, test_data) 
                for temp in image_list
            ]
        # 완료된 순서대로 결과 수집
        for future in concurrent.futures.as_completed(futures):
            try:
                temp_result = future.result()
                result.append(temp_result)
            except Exception as e:
                print(f"❌ 처리 실패: {e}")
                # 실패한 경우 에러 정보 추가하거나 건너뛰기
                # result.append({"error": str(e)})
        # for temp in image_list:
            
        #     temp_result = self._response_llm_data(temp, test_data)
            
        #     result.append()
                

        #3. Document로 변환.
        application_docuement_list = self.imageExtractor.create_column_document(result)
        print(application_docuement_list)
        print("test => " + collection_name)
        
        #4. 벡터에 넣기.
        self._insert_to_collection(
            collection_name=collection_name, 
            documents=application_docuement_list
        )
        
        
    
    ##기존에 있는 컬렉션에 데이터 임베딩.
    ##멀티파트 형식으로 데이터를 요청했을떄 처리.
    def add_rag_data(self, collection_name, formData: FormData):
        
        #form데이터 정제
        data_items = []
        
        service_names = formData.getlist("service_name")
        screen_names = formData.getlist("screen_name")
        versions = formData.getlist("version") 
        access_levels = formData.getlist("access_level")   
        images = formData.getlist("images")
        
        for i in range(len(service_names)):
            data_items.append({
                "service_name":service_names[i],
                "screen_name":screen_names[i],
                "version": versions[i],
                "access_level": access_levels[i],
                "image": base64.b64encode(images[i].file.read()).decode("utf-8"),
                "filename" : images[i].filename
            })
            
        
        
        result = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # 모든 작업을 스레드풀에 제출
            futures = [
                executor.submit(self._response_llm_data2, data_item) 
                for data_item in data_items
            ]
        # 완료된 순서대로 결과 수집
        for future in concurrent.futures.as_completed(futures):
            try:
                temp_result = future.result()
                result.append(temp_result)
            except Exception as e:
                # print(f"❌ 처리 실패: {e}")
                error_type = type(e).__name__
                if "OpenAI" in error_type or "API" in str(e):
                    print(f"❌ API 에러: {str(e)[:150]}...")
                elif "JSON" in str(e):
                    print(f"❌ JSON 파싱 에러: {str(e)[:100]}...")
                elif "timeout" in str(e).lower():
                    print(f"❌ 타임아웃 에러")
                else:
                    print(f"❌ {error_type}: {str(e)[:100]}...")
                
        
        application_docuement_list = self.imageExtractor.create_column_document(result)
        
        #4. 벡터에 넣기.
        self._insert_to_collection(
            collection_name=collection_name, 
            documents=application_docuement_list
        )
    
    
    def _insert_to_collection(self, collection_name: str, documents: List[Document]):
        #1. 컬렉션 확인.
        collection_check = self.vector_repository.collection_name_check(collection_name)[0]
        
        print("collection_name => " + collection_name)
        print("collection_check => " + str(collection_check))
        
        #2.이미 있다면 기존 컬렉션을 가져옴.
        if collection_check:
            vector_store = self.vector_repository.existing_vector_store(collection_name)
            vector_store.add_documents(documents)
            
        #3. 없다면 생성하고 vector디비에 넣기. 
        else:
            print("teadsfasdfa")
            self.vector_repository.build_vector_storage(
                collection_name = collection_name, 
                documents = documents
            )

    def _test_input_data(self):
        
        test_dict = {
            "1" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "깃허브 전체 랭킹목록 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "2" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "깃허브 랭킹 닉네임으로 유저 검색",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "3" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "백준 전체 랭킹 목록 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "4" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "다른 사용자와 랭킹정보 비교 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "5" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "레포지토리, 리드미 등 사용자 랭킹 정보 상세 조회 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "6" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "취업 공고를 통해 취업상태 등록 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "7" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "현재 취업 상태 관리 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            },
            "8" : {
                "service_name" : "개발자 랭킹 서비스",
                "screen_name" : "공고에 지원한 타 유저 및 평균조회 페이지",
                "version" : "3.1.1",
                "access_level" : "user"
            }
        }
        
        return test_dict
        
    def _create_image_url(slef,filename, base64_image):
        if filename.lower().endswith('.png'):
            return f"data:image/png;base64,{base64_image}"
        elif filename.lower().endswith('.webp'):
            return f"data:image/webp;base64,{base64_image}"
        else:  # jpg, jpeg 등
            return f"data:image/jpeg;base64,{base64_image}"
        
    ##응답 쿼리에서 코드블럭 제거
    def _delete_code_block(self, sql_response:str) -> str:
        
        if sql_response.startswith('```json'):
            sql_response = sql_response[7:]
        
        if sql_response.endswith('```'):
            sql_response = sql_response[:-3]
            
        return sql_response.strip()
    
    def _response_llm_data(self, image_dict:  Dict[str,str], test_data: List[Dict[str,str]]) -> Dict[str,str]:
        
        #2. llm에 요청해서 이미지 분석텍스트 받아오기.
        temp_key = image_dict['filename'].split(".")[0]
        temp_value = test_data[temp_key]
        
        
        prompt = ChatPromptTemplate.from_messages([
            ("system" , app_analysis_prompt_system),
            ("user" , app_analysis_prompt_user)
        ])
        
        formatted_messages = prompt.format_messages(
            service_name = temp_value['service_name'],
            screen_name = temp_value['screen_name'],
            version = temp_value['version'],
            access_level = temp_value['access_level'],
        )
        
        user_message = formatted_messages[-1]
        user_message.content = [
            {
                "type" : "text",
                "text" : user_message.content
            },
            {
                "type" :"image_url",
                "image_url": {
                    "url" : self._create_image_url(image_dict['filename'],image_dict['base64'])
                }
            }
        ]
        
        response = self._delete_code_block(
            self.llm_client.llm_request(formatted_messages)
        )
        
        return json.loads(response)
    
    ## 멀티파트로 넣을떄 사용하는 메서드
    ## TODO : _response_llm_data 메서드와 통합 필요 - 당장은 테스트 형식을 만드느라 데이터형식이 달라서 분할했지만 통합필요.
    def _response_llm_data2(self, data_item: Dict[str,str]) -> Dict[str,str]:
        
        
        
        prompt = ChatPromptTemplate.from_messages([
            ("system" , app_analysis_prompt_system),
            ("user" , app_analysis_prompt_user)
        ])
        
        formatted_messages = prompt.format_messages(
            service_name = data_item['service_name'],
            screen_name = data_item['screen_name'],
            version = data_item['version'],
            access_level = data_item['access_level'],
        )
        
        user_message = formatted_messages[-1]
        user_message.content = [
            {
                "type" : "text",
                "text" : user_message.content
            },
            {
                "type" :"image_url",
                "image_url": {
                    "url" : self. _create_image_url(filename = data_item['filename'], base64_image = data_item['image'])
                }
            }
        ]
        
        response = self._delete_code_block(
            self.llm_client.llm_request(formatted_messages)
        )
        
        return json.loads(response)