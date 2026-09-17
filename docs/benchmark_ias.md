# Benchmark: IAs personales de la comunidad vs Nia

Investigación profunda (2026) sobre ~35 proyectos reales de gente que construyó
su propia IA: GitHub, Reddit (r/LocalLLaMA, r/selfhosted, r/homeassistant),
Hacker News, IndieHackers, dev.to, X/LinkedIn, papers académicos.

## Fortalezas que destacaron (y quién)

| Fortaleza | Quién | Fuente |
|---|---|---|
| Auto-reescritura de su propio código | Sakana Darwin Gödel Machine (SWE-bench 20%→50%), te menciona: sakana.ai/dgm · arxiv 2505.22954; Nova (DPO fine-tune) HN 47393086; Kora (genera apps) HN 47531594 | sakana.ai |
| Genera sus propias tools/skills por voz | CAAL (n8n/MCP) r/LocalLLaMA 1pybbjg; Moltis HN 46993587; OpenClaw (ClawHub, 800+ skills) openclaw.ai | reddit/HN |
| Proactividad que aprende CUÁNDO hablar | Loyca (bandit RL accept/reject) github.com/Vokturz/loyca-ai; ContextAgent (umbral θ + percepción por niveles) arxiv 2505.14668 | github/arxiv |
| Contexto ambiental continuo (pantalla texto) | AYO (heyayo, on-device ~1% CPU); Samuel screen-voice-agent (sub-500ms + audio sistema); Screenpipe (OCR+audio local) | heyayo/github |
| Memoria con arquitectura | Letta/MemGPT (W/S/E + bloques auto-editables) github.com/letta-ai/letta; Magi (memoria con recibos/procedencia) github.com/asukaonly/magi; Yours (no llamar memoria por turno) | github |
| Anomalías del sistema (2σ) | Cryp (HUD + patrones); agentomaly (perfiles de comportamiento) github.com/sushaan-k/agentomaly | github |
| GUI/OS automation con safety rails | Rosply (cap 200 acciones + kill); UFO/UI-TARS (accessibility tree + OCR) microsoft/ufo | github |
| OS-como-asistente / agent OS | AIOS (arxiv 2403.16971); Kora (370K líneas Rust, compositor AI-aware) | arxiv/HN |
| Memoria episódica con "qué dijo la compu" | Samuel; CielChan (audio del sistema); Screenpipe como sustrato | github |
| Fine-tuning personal / digital twin | BuddAI (corrige una vez, no repite) r/LocalLLaMA 1q7a9di; Nova | reddit |
| Briefing + proactivos con relojes | ramsbaby (council de agentes por LaunchAgent); Ron Forbes (RonOS) | dev.to/blog |

## La comunidad: tipos dominantes

- **Chat-first / agentes de corazón** (OpenClaw, Moltis, LocalGPT): memoria markdown,
  skills auto-generadas, heartbeats, Telegram/Discord. No voz ni pantalla.
- **Voice-first que compite en latencia** (RealtimeVoiceChat ~500ms, Samuel,
  Shadow AI): wake word local + STT + TTS, pero sin tools profundas.
- **Ambient / screen-aware** (AYO, Loyca, Rosply, Wizper): la PC como contexto;
  casi todos sin voz o sin memoria.
- **Deep / local hostiles** (Solus en GTX 1650, ATOM con robot, NightDeck en Pi Zero):
  optimizan para VRAM bajita - como Nia.
- **GM clásicos** (Nova, Kora, CAAL): lo *raro* es auto-modificación + memoria rica.

## Gap real de Nia (identificado y en curso)

1. ✅ Contexto ambiental automático por turno → **implementado** (`actions/ambient_context.py`).
2. ✅ Proactiva que aprende cuándo hablar → **implementado** (`proactive_action` decide/feedback/status).
3. ✅ Generar tools/skills a pedido → **implementado** (`actions/skill_creator.py`; ejemplo: `cuenta_dias`).
4. ✅ Detector de anomalías con baseline 2σ → **implementado** (`actions/anomaly_monitor.py`, integrado a la proactiva como señal `system_anomaly`).
5. ✅ Memoria episódica con recibos (Magi) → **implementado** (`actions/episodic_memory.py`: proveniencia por recuerdo, revocación con lápida, sync de importantes al prompt).
6. ✅ Mantenimiento nocturno programado ("Neuro-sleep") → **implementado** (`actions/nightly_maintenance.py`: regresión + rotas + backup zip + limpieza, ventana 02:00–06:00).
7. 💡 Opcional wow: audio del sistema en Windows (loopback WASAPI/pyaudiowpatch) — riesgo medio.
8. ✅ Barra de texto para escribirle a Nia ("modo escritura") → **implementado** (botón ⌨ en el header, Enter envía, Esc cierra; mismo funnel que la voz; el mic se pausa mientras se escribe).

## Qué NO perseguir
- Fine-tuning DPO tipo Nova (no cabe en 4 GB; Nia lo cubre con learning+heal).
- Multi-dispositivo/Telegram (descartado por el usuario).
- Factarios de marketing (iFlytek, ElevenLabs, Necto = empresas).