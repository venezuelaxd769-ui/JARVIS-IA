# JARVIS-IA

## Resumen
📁 Proyecto 'JARVIS-IA' (C:\Users\venez\JARVIS-IA)
   Lenguaje: Python
   Archivos: 262 | Líneas: 42837
   Qué dice el README: Asistente virtual de escritorio con voz en tiempo real (Google Gemini Live), personalidad propia, sistema de evolución autónoma, control del sistema y 113 herramientas. Basada en el asistente de Iron Man: interfaz holográfica dorada, PNGtub
   Extensiones: .py(135), .json(26), .txt(17), .md(4), .sh(4), .conf(4)
   Punto de entrada: main.py
   Estructura:
    📁 actions
    📁 agent
    📁 assets
    📁 config
    📁 core
    📁 docs
    📁 launchers
    📁 memory
    📁 pngtuber
    📁 tests
    📄 AGENTS.md
    📄 beta_config.py
    📄 continuity.py
    📄 crash.log
    📄 download_vosk.py
    📄 file_events.py
    📄 Iniciar JARVIS Beta.vbs
    📄 inspect_bento_widgets.py
    ... (más elementos)
   Módulos y su función:
    • beta_config.py: beta_config.py — Clean configurations and tool checks.
    • continuity.py: Continuidad entre reinicios: Nia sabe cuánto tiempo estuvo apagada.  Un hilo daemon escribe a disco un heartbeat cada N segundos. Al arrancar, build_continuity_note() compara la úl
    • download_vosk.py: import urllib.request
    • file_events.py: file_events.py — Clean thread-safe event bus for JARVIS file modifications.
    • inspect_bento_widgets.py: import sys, io
    • install.py: -*- coding: utf-8 -*-
    • main.py: Vigila la RAM disponible. Si queda críticamente poca, fuerza un GC     y registra los mayores consumidores antes de un posible OOM kill.
    • run_debug.py: import os
    • sandbox.py: sandbox — frontera de acción de Nia (regla de autonomía).  Filosofía (regla de oro: el límite va en la autonomía, no en el conocimiento): - El sandbox es el espacio aislado donde N
    • sitecustomize.py: JARVIS Beta — custom importer for .pyc-only distribution.

## Módulos
| Archivo | Símbolos |
| --- | --- |
| .gitignore | 0 |
| AGENTS.md | 3 |
| Iniciar JARVIS Beta.vbs | 0 |
| Instalar_JARVIS.bat | 0 |
| Liberar_JARVIS.bat | 0 |
| README.md | 0 |
| beta_config.py | 5 |
| continuity.py | 8 |
| crash.log | 0 |
| download_vosk.py | 0 |
| file_events.py | 7 |
| inspect_bento_widgets.py | 0 |
| install.py | 1 |
| jarvis.log | 0 |
| jarvis.log.bak | 0 |
| jarvis.log.bak2 | 0 |
| jarvis.log.bak3 | 0 |
| main.py | 19 |
| requirements.txt | 0 |
| run_debug.py | 1 |
| run_jarvis.sh | 0 |
| sandbox.py | 2 |
| sitecustomize.py | 1 |
| stderr.log | 0 |
| stdout.log | 0 |
| training.py | 10 |
| ui.py | 21 |
| actions\__init__.py | 0 |
| actions\_chrome_launch.py | 1 |
| actions\_self_agent_core.pyc | 0 |
| actions\accessibility.py | 12 |
| actions\accessibility_overlay.py | 7 |
| actions\ambient_context.py | 7 |
| actions\anomaly_monitor.py | 8 |
| actions\arca_invoice.py | 1 |
| actions\auto_programmer.py | 2 |
| actions\backup_manager.py | 5 |
| actions\browser_control.py | 7 |
| actions\camera_bus.py | 1 |
| actions\clipboard.py | 6 |
| actions\code_editor.py | 10 |
| actions\code_executor.py | 2 |
| actions\code_helper.py | 1 |
| actions\code_search.py | 5 |
| actions\codebase.py | 19 |
| actions\computer_control.py | 1 |
| actions\computer_settings.py | 1 |
| actions\computer_use.py | 7 |
| actions\contextual_control.py | 9 |
| actions\csv_analyzer.py | 2 |
| actions\cuenta_dias.py | 1 |
| actions\custom_tools.json | 0 |
| actions\daily_summary.pyc | 0 |
| actions\describe_screen.py | 8 |
| actions\desktop.py | 14 |
| actions\desktop_kb.py | 13 |
| actions\desktop_kb.pyc | 0 |
| actions\dev_agent.pyc | 0 |
| actions\doc_generator.py | 6 |
| actions\document_creator.py | 1 |