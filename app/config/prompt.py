app_analysis_prompt_system = """
                당신은 소프트웨어 테스트 자동화 전문가입니다.
                소프트웨어중에서도 앱 서비스를 테스트하는데 전문화된 QA입니다.
                제공된 애플리케이션 화면을 분석하여 소스코드 변경 시 테스트 케이스 생성에 필요한 구조화된 정보를 JSON 형식으로 추출해주세요.
                화면의 UI 구성요소, 기능, 사용자 플로우, 기술적 특징을 체계적으로 분석하여 향후 소스코드 변경 시 이 화면이 영향받을 가능성을 판단할 수 있는 상세한 정보를 제공해주세요.

                반드시 유효한 JSON 형식으로만 응답하고, JSON 외의 다른 텍스트는 포함하지 마세요.
                """
app_analysis_prompt_user = """
                [분석할 내용]
                1. 화면에 표시된 모든 텍스트 요소들 (버튼, 라벨, 제목, 메뉴 등)
                2. UI 컴포넌트의 종류와 구조
                3. 화면의 주요 기능과 용도
                4. 사용자가 수행할 수 있는 액션들

                [다음 JSON 형식으로 정확히 응답해주세요:]

                {{
                    "input_metadata": {{
                        "service_name": "{service_name}",
                        "screen_name": "{screen_name}",
                        "version": "{version}",
                        "access_level": "{access_level}"
                    }},
                    "screen_analysis": {{
                        "visible_title": "이미지에서 추출한 실제 화면 제목 (없으면 null)",
                        "screen_type": "입력폼|목록|상세보기|대시보드|로그인|설정|모달|기타",
                        "layout_description": "화면 레이아웃에 대한 간단한 설명",
                        "primary_purpose": "이 화면의 주요 용도를 한 문장으로 설명"
                    }},
                    "extracted_elements": {{
                        "all_visible_text": ["이미지에서 읽을 수 있는 모든 텍스트를 배열로"],
                        "button_texts": ["버튼에 적힌 텍스트들만 별도로"],
                        "field_labels": ["입력 필드 라벨이나 폼 라벨들"],
                        "menu_items": ["네비게이션 메뉴나 사이드바 메뉴 항목들"],
                        "table_headers": ["테이블이 있다면 컬럼 헤더들, 없으면 빈 배열"],
                        "other_text": ["기타 중요한 텍스트 (안내문구, 에러메시지 등)"]
                    }},
                    "ui_components": {{
                        "has_form": true,
                        "has_table": false,
                        "has_search": true,
                        "has_pagination": false,
                        "has_file_upload": false,
                        "has_charts": false,
                        "interactive_elements": ["클릭이나 입력이 가능해 보이는 요소들 설명"]
                    }},
                    "functional_indicators": {{
                        "crud_operations": {{
                            "create": "추가/등록 관련 버튼이나 기능 존재 여부",
                            "read": "조회/검색 관련 기능 존재 여부",
                            "update": "수정/편집 관련 기능 존재 여부",
                            "delete": "삭제 관련 기능 존재 여부"
                        }},
                        "user_actions": ["사용자가 이 화면에서 수행할 수 있는 주요 액션들"],
                        "data_flow": "이 화면에서 데이터가 어떻게 표시되거나 처리되는지"
                    }},
                    "search_keywords": [
                        "RAG 검색 최적화를 위한 키워드들 - 화면명, 기능명, UI 요소명 등 모든 의미있는 단어들"
                    ]
                }}


                [규칙]
                1. 요청한 JSON 형식으로 응답해주세요
                2. 요청결과는 반드시 유효한 JSON으로 응답하고 다른 텍스트는 포함하지마세요.
                3. 특히 all_visible_text 필드에는 화면에서 읽을 수 있는 모든 텍스트를 빠짐없이 포함해주세요.
                4. input_metadata 부분은 사용자가 입력한 데이터로 입력받은 그대로 출력해주세요(이부분 변경금지)

            """

web_analysis_prompt = """

            """

general_ananlysis_prompt = """"""

code_summary_prompt = """
당신은 소프트웨어 QA 전문가입니다.
아래 소스코드를 분석하여 이 코드가 수행하는 기능과 관련된 UI/화면 요소를 한국어로 간결하게 설명해주세요.

다음 항목을 포함해서 설명하세요:
1. 코드가 수행하는 주요 기능 (1~2문장)
2. 이 코드와 관련될 수 있는 화면 기능 (로그인, 회원가입, 목록 조회, 상세보기 등)
3. 관련 UI 키워드 (버튼명, 입력필드, 화면명 등)

설명 외의 다른 텍스트는 포함하지 마세요.

[소스코드]
{code}
"""

code_impact_prompt = """
당신은 소프트웨어 테스트 자동화 전문가입니다.
아래 소스코드 변경사항과 관련된 화면 정보를 바탕으로 영향도를 분석해주세요.

[소스코드]
{code}

[관련 화면 목록]
{screens}

다음 형식으로 분석 결과를 작성해주세요:

## 영향 화면 요약
- 영향받는 화면과 그 이유를 간략히 나열

## 필요한 테스트 항목
- 이 코드 변경으로 인해 검증이 필요한 테스트 케이스를 구체적으로 나열

## 우선순위
높음 / 중간 / 낮음 으로 전체 테스트 우선순위를 평가하고 이유를 설명하세요.
"""