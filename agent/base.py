"""Clase base SubAgent: un subagente con su propio LLM y toolkit acotado.

Nia (la orquestadora) delega tareas complejas a estos subagentes. Cada uno
razona en un hilo aparte, puede llamar sus propias herramientas en un bucle,
y devuelve un reporte en texto.
"""

from __future__ import annotations

import json

from agent.models import get_client, get_client_with_fallback
from agent.toolbox import call_tool, tool_declarations


class SubAgent:
    def __init__(
        self,
        name: str,
        description: str,
        tools: list[str],
        persona: str,
        model_kind: str = "gemini",
        model_name: str | None = None,
        fallback_kind: str | None = None,
        fallback_model: str | None = None,
        max_iterations: int = 8,
        max_tokens: int = 2048,
        player=None,
        speak=None,
    ):
        self.name = name
        self.description = description
        self.tools = tools
        self.persona = persona
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.player = player
        self.speak = speak

        # Usar fallback si se especifica
        if fallback_kind:
            self.client = get_client_with_fallback(
                model_kind, model_name, fallback_kind, fallback_model
            )
        else:
            self.client = get_client(model_kind, model_name)

    # ── Loop agéntico ────────────────────────────────────────────────────────

    def run(self, goal: str, context: str = "") -> str:
        messages = [
            {"role": "system", "content": self.persona},
            {"role": "user", "content": self._build_user_prompt(goal, context)},
        ]
        decls = tool_declarations(self.tools)

        last_text = None
        for _ in range(self.max_iterations):
            try:
                resp = self.client.complete(messages, decls, self.max_tokens)
            except Exception as e:
                return f"[{self.name}] Error del modelo: {e}"

            tool_calls = resp.get("tool_calls") or []
            text = resp.get("text")

            if tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": text,
                    "tool_calls": tool_calls,
                })
                for call in tool_calls:
                    result = call_tool(call["name"], call["args"], self.player, self.speak)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": result[:8000],
                    })
                continue

            if text:
                return text
            last_text = text

        return last_text or (f"[{self.name}] Sin respuesta tras "
                             f"{self.max_iterations} iteraciones.")

    def _build_user_prompt(self, goal: str, context: str) -> str:
        now = __import__("datetime").datetime.now().strftime("%A %d/%m/%Y %H:%M")
        parts = [
            f"Fecha y hora actual: {now}.",
            "",
            "TAREA DEL USUARIO:",
            goal,
        ]
        if context:
            parts += ["", "CONTEXTO ADICIONAL:", context]
        parts += [
            "",
            "INSTRUCCIONES:",
            "1. Usa tus herramientas cuando aporten datos reales (búsquedas, "
            "archivos, terminal, etc.). No inventes resultados.",
            "2. Si la herramienta falla, intentá otro enfoque o decilo claro.",
            "3. Responde SIEMPRE en español, con un reporte claro y conciso "
            "(títulos y viñetas si corresponde).",
            "4. No menciones que sos un subagente: sos Nia, la asistente.",
        ]
        return "\n".join(parts)
