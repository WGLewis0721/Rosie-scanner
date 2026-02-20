import os
from enum import Enum
from langchain_core.language_models import BaseChatModel

class LLMProvider(str, Enum):
    BEDROCK = "bedrock"
    OLLAMA = "ollama"
    OPENAI = "openai"

def get_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    provider = provider or os.getenv("LLM_PROVIDER", LLMProvider.OPENAI)
    if provider == LLMProvider.BEDROCK:
        from langchain_aws import ChatBedrock
        return ChatBedrock(
            model_id=model or os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        )
    elif provider == LLMProvider.OLLAMA:
        from langchain_community.chat_models import ChatOllama
        return ChatOllama(
            model=model or os.getenv("OLLAMA_MODEL", "llama3"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    else:  # openai default
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY", "sk-placeholder"),
            base_url=os.getenv("OPENAI_BASE_URL", None),
        )
