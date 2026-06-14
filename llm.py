import os
from openai import OpenAI
from dotenv import load_dotenv

from memory import load_llm_settings

load_dotenv()

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _get_api_key() -> str:
    return load_llm_settings().get("api_key", "")


def _get_base_url() -> str:
    return load_llm_settings().get("base_url", DEFAULT_BASE_URL)


def _get_model_name() -> str:
    return load_llm_settings().get("model_name", DEFAULT_MODEL)


def _get_embedding_model_name() -> str:
    return load_llm_settings().get("embedding_model_name", DEFAULT_EMBEDDING_MODEL)


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=_get_api_key(),
        base_url=_get_base_url(),
    )

DEFAULT_TEMPERATURE = 0.7

def call_llm(prompt: str, system_message: str = "", temperature: float = DEFAULT_TEMPERATURE):
    if not _get_api_key():
        raise RuntimeError("Missing API key. Configure LLM_API_KEY or DEEPSEEK_API_KEY in the app settings or .env.")

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})

    response = _get_client().chat.completions.create(
        model=_get_model_name(),
        messages=messages,
        temperature=temperature
    )

    return response.choices[0].message.content or ""


def get_embedding(text: str) -> list[float]:
    if not _get_api_key():
        raise RuntimeError("Missing API key. Configure LLM_API_KEY or DEEPSEEK_API_KEY in the app settings or .env.")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Embedding input text cannot be empty.")

    response = _get_client().embeddings.create(
        model=_get_embedding_model_name(),
        input=cleaned,
    )
    return response.data[0].embedding
