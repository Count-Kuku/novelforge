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


PROVIDER_PRESETS = {
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model_name": "deepseek-v4-flash",
        "embedding_model_name": "text-embedding-3-small",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model_name": "gpt-4o",
        "embedding_model_name": "text-embedding-3-small",
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model_name": "auto",
        "embedding_model_name": "text-embedding-3-small",
    },
    "阿里云通义千问 (Qwen)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen-plus",
        "embedding_model_name": "text-embedding-v3",
    },
    "硅基流动 (SiliconFlow)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-v4-flash",
        "embedding_model_name": "BAAI/bge-m3",
    },
    "本地 Ollama": {
        "base_url": "http://localhost:11434/v1",
        "model_name": "llama3",
        "embedding_model_name": "nomic-embed-text",
    },
    "自定义": {
        "base_url": "",
        "model_name": "",
        "embedding_model_name": "",
    },
}


def test_llm_connection(base_url: str, api_key: str, model_name: str) -> str:
    if not api_key:
        raise RuntimeError("接口密钥不能为空。")
    if not base_url:
        raise RuntimeError("模型服务网址不能为空。")
    try:
        test_client = OpenAI(api_key=api_key, base_url=base_url)
        test_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "回复 OK 即可。"}],
            max_tokens=8,
            temperature=0,
        )
        return "连接成功。"
    except Exception as exc:
        raise RuntimeError(f"连接测试失败（{type(exc).__name__}）：请检查服务地址、密钥和模型名是否正确。") from exc
