"""Minimal OpenAI-compatible chat completions client."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse


def call_llm(prompt: str) -> str:
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("缺少 LLM_API_KEY，请设置 API key 后重试。")
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or any(c in base for c in "[]()"):
        raise RuntimeError("LLM_BASE_URL 必须是纯 HTTP(S) 地址，不能包含 Markdown 链接。")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    print(f"LLM 请求地址: {base}/chat/completions；模型: {model}")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    request = urllib.request.Request(base + "/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = json.load(response)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"真实 LLM 请求失败：HTTP {exc.code}（未降级，响应正文未打印）") from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(f"真实 LLM 网络请求失败：{type(exc).__name__}（超时或连接失败，未降级）") from exc
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RuntimeError("真实 LLM 响应格式无效，未降级") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM 返回了空内容或非文本内容。")
    return content.strip()
