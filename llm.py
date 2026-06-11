import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _get_api_key() -> str:
    return os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""


def _get_base_url() -> str:
    return os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL


def _get_model_name() -> str:
    return os.getenv("LLM_MODEL") or DEFAULT_MODEL


def _get_embedding_model_name() -> str:
    return os.getenv("LLM_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL


client = OpenAI(
    api_key=_get_api_key(),
    base_url=_get_base_url()
)

DEFAULT_TEMPERATURE = 0.7

def call_llm(prompt: str, system_message: str = "", temperature: float = DEFAULT_TEMPERATURE):
    if not _get_api_key():
        raise RuntimeError("Missing API key. Set LLM_API_KEY or DEEPSEEK_API_KEY in .env.")

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=_get_model_name(),
        messages=messages,
        temperature=temperature
    )

    return response.choices[0].message.content or ""


def get_embedding(text: str) -> list[float]:
    if not _get_api_key():
        raise RuntimeError("Missing API key. Set LLM_API_KEY or DEEPSEEK_API_KEY in .env.")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Embedding input text cannot be empty.")

    response = client.embeddings.create(
        model=_get_embedding_model_name(),
        input=cleaned,
    )
    return response.data[0].embedding
