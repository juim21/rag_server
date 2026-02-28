from abc import ABC, abstractmethod

class LlmClient(ABC):

    @abstractmethod
    def llm_request(self, prompt) -> str:
        pass
