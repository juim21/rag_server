import os
from dotenv import load_dotenv, find_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.interface.llm_client import LlmClient

load_dotenv(find_dotenv())


class GoogleChatClient(LlmClient):

    _llm = None

    def __init__(self):
        if GoogleChatClient._llm is None:
            self._initialize_llm()

    def _initialize_llm(self):
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            raise ValueError("GOOGLE API KEY가 없습니다.")

        GoogleChatClient._llm = ChatGoogleGenerativeAI(
            google_api_key=google_api_key,
            model="gemini-2.0-flash",
            temperature=0
        )

    @property
    def chat_llm(self):
        return GoogleChatClient._llm

    def llm_request(self, prompt) -> str:
        return self._llm.invoke(prompt).content
