"""Backends de modelo para los subagentes de Nia.

Cada subagente razona con su propio LLM (no-Live, más barato y paralelo).
Ambos backends exponen la misma interfaz:

    complete(messages, tools, max_tokens) -> dict
        messages: lista en formato neutro:
            {"role": "system"|"user"|"assistant"|"tool", "content": str, ...}
        tools: lista de declaraciones estilo Gemini:
            {"name", "description", "parameters"}
    Devuelve:
        {"text": str|None, "tool_calls": [{"id", "name", "args"}]}
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"


def _api_key(key_name: str) -> str:
    if not API_FILE.exists():
        return ""
    try:
        data = json.loads(API_FILE.read_text(encoding="utf-8"))
        return data.get(key_name, "") or ""
    except Exception:
        return ""


# ── Conversores al formato de cada proveedor ─────────────────────────────────

def _to_gemini_messages(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Convierte el formato neutro a messages de google-genai.

    Devuelve (contents, system_instruction).
    """
    system_parts = []
    contents = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_parts.append(m["content"])
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif role == "assistant":
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for call in m.get("tool_calls", []) or []:
                parts.append({"function_call": {"name": call["name"], "args": call["args"]}})
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif role == "tool":
            contents.append({
                "role": "user",
                "parts": [{"function_response": {
                    "name": m["name"],
                    "response": {"result": m["content"]},
                }}],
            })
    return contents, "\n".join(system_parts) or None


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        role = m["role"]
        if role == "system":
            out.append({"role": "system", "content": m["content"]})
        elif role == "user":
            out.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            msg = {"role": "assistant", "content": m.get("content")}
            calls = m.get("tool_calls") or []
            if calls:
                msg["tool_calls"] = [{
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c["args"], ensure_ascii=False),
                    },
                } for c in calls]
            out.append(msg)
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": m.get("tool_call_id", ""),
                "content": m["content"],
            })
    return out


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("parameters", {}),
        },
    } for t in tools]


# ── Gemini (no-RealTime) ─────────────────────────────────────────────────────

class GeminiClient:
    """Usa google-genai contra el modelo Gemini normal (más barato que Live)."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name
        self._client = None

    def _get(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=_api_key("gemini_api_key"))
        return self._client

    def complete(self, messages, tools=None, max_tokens=2048):
        from google.genai import types
        contents, system_instruction = _to_gemini_messages(messages)
        config = {
            "temperature": 0.3,
            "max_output_tokens": max_tokens,
        }
        if tools:
            config["tools"] = [{"function_declarations": tools}]
        if system_instruction:
            config["system_instruction"] = system_instruction

        resp = self._call_with_retry(
            lambda: self._get().models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(**config),
            )
        )

        text = None
        tool_calls = []
        try:
            texts = [p.text for p in resp.candidates[0].content.parts
                     if getattr(p, "text", None)]
            text = " ".join(texts).strip() or None
        except Exception:
            text = None
        try:
            for part in resp.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    args = dict(fc.args or {})
                    tool_calls.append({
                        "id": fc.id or f"fc_{len(tool_calls)}",
                        "name": fc.name,
                        "args": args,
                    })
        except Exception:
            tool_calls = []
        return {"text": text, "tool_calls": tool_calls}

    def _call_with_retry(self, fn):
        """Reintenta ante 429 (cuota agotada) respetando el retry sugerido."""
        import re
        import time
        for attempt in range(3):
            try:
                return fn()
            except Exception as e:
                msg = str(e)
                if "429" not in msg:
                    raise
                if attempt == 2:
                    raise
                m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg)
                wait = min(float(m.group(1)) if m else 30, 60)
                time.sleep(wait)
        return fn()


# ── OpenRouter (OpenAI-compatible) ───────────────────────────────────────────

class OpenRouterClient:
    """Habla con cualquier modelo de OpenRouter (claude, gpt, gemini, ...)."""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model_name: str = "google/gemini-2.5-flash"):
        self.model_name = model_name

    def complete(self, messages, tools=None, max_tokens=2048):
        import httpx

        api_key = _api_key("openrouter_api_key")
        if not api_key:
            return {"text": "No hay clave de OpenRouter en config/api_keys.json.", "tool_calls": []}

        payload = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "messages": _to_openai_messages(messages),
        }
        if tools:
            payload["tools"] = _to_openai_tools(tools)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/jarvis-beta",
            "X-Title": "JARVIS AI Assistant",
            "Content-Type": "application/json",
        }

        try:
            data = self._post_with_retry(httpx, api_key, payload, headers)
            message = data["choices"][0]["message"]
        except Exception as e:
            return {"text": f"Error de OpenRouter: {e}", "tool_calls": []}

        tool_calls = []
        for tc in message.get("tool_calls", []) or []:
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                args = {}
            tool_calls.append({
                "id": tc.get("id", f"tc_{len(tool_calls)}"),
                "name": tc["function"]["name"],
                "args": args,
            })
        return {"text": (message.get("content") or "").strip() or None, "tool_calls": tool_calls}

    def _post_with_retry(self, httpx, api_key, payload, headers):
        """Reintenta ante errores transitorios (429/5xx/red) con backoff
        exponencial y respetando el header retry-after cuando viene. Los
        4xx permanentes (401, 400, 404...) no se reintentan."""
        import time
        last_err = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120) as http:
                    resp = http.post(self.API_URL, json=payload, headers=headers)
                if resp.status_code in (408, 429) or 500 <= resp.status_code <= 599:
                    last_err = f"HTTP {resp.status_code}"
                    wait = min(max(1.5 * (2 ** attempt), 0.5), 30)
                    try:
                        wait = min(max(float(resp.headers.get("retry-after", wait)), 0.5), 30)
                    except ValueError:
                        pass
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.RequestError as e:
                # fallo de red o timeout → reintentar
                last_err = str(e)
                time.sleep(min(1.5 * (2 ** attempt), 30))
            except httpx.HTTPStatusError:
                # 4xx permanente (auth, request inválida): no reintentar
                raise
        raise RuntimeError(f"OpenRouter no respondió tras 3 intentos: {last_err}")


# ── Fábrica ──────────────────────────────────────────────────────────────────

def get_client(kind: str, model_name: str | None = None):
    kind = (kind or "gemini").lower()
    if kind == "openrouter":
        return OpenRouterClient(model_name or "google/gemini-2.5-flash")
    return GeminiClient(model_name or "gemini-2.5-flash")
