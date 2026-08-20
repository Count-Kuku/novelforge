"""对已配置的真实 OpenAI-compatible provider 做一次安全的流式 smoke。

仅从环境变量读取凭据，不打印密钥；未配置时返回 2，方便 CI 将该门标记为
明确的可选发布检查，而不是把 stub 或本地协议夹具误报成真实 provider 证据。
"""
from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> int:
    api_key = str(os.getenv("NOVELFORGE_LLM_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    base_url = str(os.getenv("NOVELFORGE_LLM_BASE_URL") or os.getenv("LLM_BASE_URL") or "").strip()
    model = str(os.getenv("NOVELFORGE_LLM_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    if not api_key or not base_url or not model:
        print("真实 provider smoke skipped: NOVELFORGE_LLM_API_KEY/BASE_URL/MODEL 未完整配置")
        return 2

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=60.0)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "只回复：NovelForge stream ok"}],
        temperature=0,
        stream=True,
    )
    content = "".join(
        chunk.choices[0].delta.content or ""
        for chunk in response
        if chunk.choices and chunk.choices[0].delta
    ).strip()
    if not content:
        raise RuntimeError("真实 provider 返回了空的流式文本")
    print(f"真实 provider stream verification passed: model={model!r}, chars={len(content)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
