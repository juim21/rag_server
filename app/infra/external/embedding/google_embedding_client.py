import os
from dotenv import load_dotenv, find_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv(find_dotenv())


class GoogleEmbeddingClient:

    _embeddings = None

    def __init__(self):
        if GoogleEmbeddingClient._embeddings is None:
            self._initialize_embeddings()

    def _initialize_embeddings(self):
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            raise ValueError("GOOGLE API KEY가 없습니다.")

        GoogleEmbeddingClient._embeddings = GoogleGenerativeAIEmbeddings(
            google_api_key=google_api_key,
            model="models/text-embedding-004"
        )

    @property
    def embeddings(self):
        return GoogleEmbeddingClient._embeddings
