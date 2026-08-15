#!/bin/bash
# run_jarvis.sh — Arranca Nia en segundo plano, despegada de la terminal.
#
#   - setsid + nohup: Nia sigue viva aunque cierres esta terminal (sin SIGHUP).
#   - NO borra /tmp/.jarvis_single_instance.lock: borrarlo anula la protección
#     de instancia única (flock) y permite levantar dos Nias a la vez.
#   - Logs: stdout/stderr a logs/nia_run.log.
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/logs"
cd "$DIR"
setsid nohup "$DIR/.venv/bin/python" "$DIR/main.py" >> "$DIR/logs/nia_run.log" 2>&1 < /dev/null &
disown
echo "Nia arrancando en segundo plano (pid $!). Logs: $DIR/logs/nia_run.log"
