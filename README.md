# JARVIS IA — Nia

Asistente virtual de escritorio con voz en tiempo real (Google Gemini Live), personalidad propia, control del sistema y 80+ herramientas. Basada en el asistente de Iron Man: interfaz holográfica dorada, PNGtuber animado y control total del entorno.

## 🌟 Características Principales

* **Conversación por voz en vivo:** Gemini Live (audio bidireccional en tiempo real), wake word, VAD con puerta de ruido adaptativa y fallback a voz local (Piper) si la API rechaza el audio nativo.
* **PNGtuber:** modelo animado en esquina de pantalla que mueve la boca con el audio real y refleja estados (escuchando/hablando/pidiendo).
* **Interfaz holográfica:** orbe reactivo al nivel de audio con tema dorado estilo "Era de Ultrón", atajo global `Insert` para despertar/mutar el micrófono.
* **Personalidad persistente:** Nia tiene emociones, celos y estilo propio (ver `core/prompt.txt`); el contexto de conversación se resume y guarda en memoria a largo plazo al cerrar.
* **Automatización:** reglas por frases, por tiempo (cron) y por estado del sistema (CPU/RAM altas), con runner en segundo plano y catch-up de tareas atrasadas.
* **Agente autónomo (`self_agent`):** Nia "piensa" en segundo plano cada ~3 min y ejecuta acciones proactivas.
* **Visión:** Vision Guardian vigila la pantalla, detección de ojos/movimientos y captura de pantalla.
* **80+ herramientas:** búsqueda web, YouTube/música, calendario y Gmail, WhatsApp/Telegram/Discord, OBS, domótica, generación de imágenes, terminal, código, control de PC (teclado/mouse/ventanas), recordatorios, memoria semántica, resúmenes matutinos y más.

## 🛠️ Tecnologías

* **Python 3.14**, `google-genai` (Live API), `sounddevice`/PortAudio (ALSA), Vosk (STT offline en sleep), Piper (TTS local de respaldo).
* **UI híbrida:** tkinter (`ui.py`) + capa PyQt6 para la ventana glassmorphism y widgets nativos.
* Control de sistema Linux: `psutil`, `ydotool`, `xdg-open`, `notify-send`, DBus.

## 🚀 Instalación y Uso (Linux)

1. Clona y crea el entorno:
   ```bash
   cd JARVIS-IA
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Configura tus API keys en `config/api_keys.json` (Gemini obligatoria; OpenRouter opcional). Sin llaves, Nia abre el diálogo de configuración inicial.
3. Arranca Nia en segundo plano (sobrevive al cierre de la terminal):
   ```bash
   ./run_jarvis.sh          # logs → logs/nia_run.log
   ```
4. **Supervisión automática (opcional):** el watchdog mantiene a Nia en línea y la reinicia si se cae:
   ```bash
   setsid nohup bash nia_watchdog.sh >> logs/watchdog.log 2>&1 &
   # Apagar:  touch logs/.watchdog_off && pkill -f nia_watchdog.sh
   ```
5. Verifica que todo quedó sano:
   ```bash
   .venv/bin/python tests/smoke_tools.py
   ```

## 🔍 Arquitectura

| Ruta | Rol |
|---|---|
| `main.py` | Loop Live (conectar/reconectar), dispatch de 80+ tools, hilo de audio dedicado |
| `actions/` | 73 módulos de herramientas (`web_search`, `obs_control`, `reminder`, ...) |
| `rules_engine.py` / `scheduler.py` | Reglas por tiempo/frase/sistema y tareas programadas |
| `memory/` | Memoria persistente (categorías) y semántica |
| `pngtuber/` | Modelo animado con boca reactiva (proceso aparte, single-instance) |
| `nia_watchdog.sh` | Supervisor anti-caídas (detecta el proceso real por `pgrep`) |
| `tests/smoke_tools.py` | Smoke test: dispatch completo, imports y handlers |

## 🛡️ Seguridad

`config/api_keys.json` guarda las llaves maestras y **no debe subirse** a ningún repositorio (está protegido por `.gitignore`). Nia tiene control real sobre tu sistema: revisá `core/prompt.txt` y las herramientas habilitadas.
