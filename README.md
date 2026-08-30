# JARVIS IA — Nia

Asistente virtual de escritorio con voz en tiempo real (Google Gemini Live), personalidad propia, sistema de evolución autónoma, control del sistema y 113 herramientas. Basada en el asistente de Iron Man: interfaz holográfica dorada, PNGtuber animado y control total del entorno.

## 🌟 Características Principales

* **Conversación por voz en vivo:** Gemini Live (audio bidireccional en tiempo real), wake word, VAD con puerta de ruido adaptativa y fallback a voz local (Piper) si la API rechaza el audio nativo.
* **PNGtuber:** modelo animado en esquina de pantalla que mueve la boca con el audio real y refleja estados (escuchando/hablando/pidiendo).
* **Interfaz holográfica:** orbe reactivo al nivel de audio con tema dorado estilo "Era de Ultrón", atajo global `Insert` para despertar/mutar el micrófono. UI 100% PyQt6 (ventana glassmorphism + WebEngine).
* **Personalidad persistente:** Nia tiene emociones, celos y estilo propio (ver `core/prompt.txt`); el contexto de conversación se resume y guarda en memoria a largo plazo al cerrar.
* **Sistema de evolución autónoma:** 5 pilares (memoria evolutiva, reflexión, proactividad, identidad emergente y esencia inalterable). Nia aprende de sus éxitos/errores, ajusta su personalidad con el tiempo y sus valores core quedan fijos en `memory/essence.json`. Ver `tests/test_evolution_system.py`.
* **Automatización:** reglas por frases, por tiempo (cron) y por estado del sistema (CPU/RAM altas), con runner en segundo plano y catch-up de tareas atrasadas.
* **Agente autónomo (`self_agent`):** Nia "piensa" en segundo plano cada ~3 min y ejecuta acciones proactivas.
* **Visión:** Vision Guardian vigila la pantalla, detección de ojos/movimientos y captura de pantalla.
* **113 herramientas:** búsqueda web, YouTube/música, calendario y Gmail, WhatsApp/Telegram/Discord, OBS, domótica, generación de imágenes, terminal, código, control de PC (teclado/mouse/ventanas), recordatorios, memoria semántica, resúmenes matutinos y más.

## 🛠️ Tecnologías

* **Python 3.14**, `google-genai` (Live API), `sounddevice`/PortAudio (ALSA), Vosk (STT offline en sleep), Piper (TTS local de respaldo), fastembed (embeddings semánticos), mediapipe (gestos por cámara).
* **UI:** PyQt6 (`ui.py`) + `PyQt6-WebEngine` para la ventana glassmorphism y el orbe WebGL (`assets/sphere.html`).
* **Control de sistema Linux:** `psutil`, `ydotool`, `xdg-open`, `notify-send`, DBus. (En Windows: `pycaw`/`comtypes` para audio.)
* **Subagentes NVIDIA NIM:** researcher/organizer/computer con `nemotron-3-ultra-550b-a55b`, coder con `qwen3-coder-480b-a35b` (gratis, 40 RPM).

## 🚀 Instalación y Uso (Linux)

1. Clona y crea el entorno:
   ```bash
   cd JARVIS-IA
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Configura tus API keys en `config/api_keys.json` (copiá `config/api_keys.example.json`). Obligatorias: **Gemini** (`gemini_api_key`). Opcionales: **OpenRouter** (subagentes) y **NVIDIA NIM** (`nvidia_api_key`, gratis en build.nvidia.com, para los subagentes NIM). Sin llaves, Nia abre el diálogo de configuración inicial.
3. Arranca Nia en segundo plano (sobrevive al cierre de la terminal):
   ```bash
   ./run_jarvis.sh          # logs → logs/nia_run.log
   ```
4. **Verificación:** Nia no tiene tests de humo; comprobá que todo quedó sano con la suite del sistema de evolución:
   ```bash
   .venv/bin/python tests/test_evolution_system.py
   ```

## 🔍 Arquitectura

| Ruta | Rol |
|---|---|
| `main.py` | Loop Live (conectar/reconectar), dispatch de 113 tools, hilo de audio dedicado, scoring de evolución |
| `actions/` | 87 módulos de herramientas (`web_search`, `obs_control`, `reminder`, ...) |
| `memory/` | Memoria persistente (categorías), semántica, embeddings y **datos de evolución** (`evolution.py`, `evolution_data.json`) |
| `core/prompt.txt` | Personalidad de Nia + secciones dinámicas que evolucionan (`TU EVOLUCIÓN`, `TU INICIATIVA`, `TU IDENTIDAD`, `TU ESENCIA`) |
| `agent/` | Subagentes (researcher/coder/organizer/computer) con esquemas de tools en `agent/tool_schemas.json` |
| `pngtuber/` | Modelo animado con boca reactiva (proceso aparte, single-instance) |
| `tests/test_evolution_system.py` | Suite de tests del sistema de evolución (7 suites) |

## 🛡️ Seguridad

`config/api_keys.json` guarda las llaves maestras y **no debe subirse** a ningún repositorio (está protegido por `.gitignore`). Nia tiene control real sobre tu sistema: revisá `core/prompt.txt` y las herramientas habilitadas.

## 🪟 Migración a Windows — Checklist

> Nia nació para Windows y se portó a Linux. Guía de instalación EXACTAS para un Windows nuevo tras clonar el repo.

### 1. Lo que hay que descargar / configurar (no viene en git)

| Ítem | Dónde | Cómo obtenerlo |
|---|---|---|
| **API key de Gemini** (obligatoria) | `config/api_keys.json` → `gemini_api_key` | [aistudio.google.com](https://aistudio.google.com) |
| **API key de NVIDIA NIM** (subagentes) | `config/api_keys.json` → `nvidia_api_key` | [build.nvidia.com](https://build.nvidia.com) — gratis, dar "Get API Key" |
| **API key de OpenRouter** (opcional) | `config/api_keys.json` → `openrouter_api_key` | [openrouter.ai](https://openrouter.ai) |
| **Entorno Python** | `.venv` | `python -m venv .venv` + `pip install -r requirements.txt` |
| **Modelo de gestos** `hand_landmarker.task` | `config/hand_landmarker.task` | Se **auto-descarga** al primer uso del gesto; o manual: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` |
| **Voz local Piper** `es_ES-davefx-medium.onnx` | `~/.local/share/piper/` (en Windows: `%LOCALAPPDATA%\piper\`) | Se **auto-descarga** la primera vez que Piper se active |
| **Embeddings fastembed** (ONNX) | `~/.cache/fastembed/` | Se **auto-descarga** al primer uso de `knowledge_base` |
| **Vosk (STT offline)** | `config/vosk_model/` | **YA viene en el repo** (no hace falta descargarlo) |

### 2. Paquetes pip extra (incluidos en `requirements.txt`)

Además de lo obvio, `requirements.txt` ya incluye los paquetes de visión, embeddings y TTS local que Nia usa: **mediapipe** (gestos), **fastembed** + **onnxruntime** (memoria semántica) y **piper-tts** (voz de respaldo). Un simple `pip install -r requirements.txt` instala todo.

### 3. Arranque en Windows

`run_jarvis.sh` es de Linux. En Windows usá los atajos que ya están en el repo:

* **Instalar:** doble clic en `Instalar_JARVIS.bat`
* **Iniciar en 2º plano (sin terminal):** `Iniciar JARVIS Beta.vbs`
* **Liberar recursos/terminar:** `Liberar_JARVIS.bat`

### 4. Extensiones de voz oficiales (compatibles Windows)

Algunos sistemas tienen la voz "Leda" solo en Gemini; para voz local usá Piper. `requirements.txt` ya trae `pycaw` y `comtypes` (control de volumen de Windows).

### 5. Modelo visual (opcional)

`config/hand_landmarker.task` (gestos) y el PNGtuber (`pngtuber/`) ya están incluidos en el repo. Nada más que descargar ahí.

### 6. Memoria y personalidad

Nia **no necesita nada**: toda su memoria (largo plazo, embeddings, obsidian, evolución) viaja en el repo dentro de `memory/`. Al clonar, Nia recuerda todo.
