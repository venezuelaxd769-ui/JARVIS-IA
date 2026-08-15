#!/usr/bin/env bash
# setup_veadotube.sh — Rutas de audio para que Veadotube Mini haga lip sync con la voz de Nia.
#
# Crea:
#   - sink virtual "nia_loopback"      → Nia (y apps) reproducen ahí (default sink)
#   - module-loopback                  → reenvía el monitor a los auriculares (el usuario escucha igual)
#   - "nia_vsource" (virtual source)   → expone el monitor como micrófono real que Veadotube puede abrir
#   - data.yaml micName="Nia"          → Veadotube usa la fuente virtual
#
# Push-to-talk (controlado por Nia por WebSocket) activa el lip sync solo cuando ella habla.
#
# Uso:
#   ./setup_veadotube.sh setup      # crear rutas de audio + lanzar Veadotube
#   ./setup_veadotube.sh teardown   # deshacer las rutas y restaurar el sink por defecto
#   ./setup_veadotube.sh launch     # solo lanzar Veadotube Mini

set -u

SINK_NAME="nia_loopback"
VSOURCE_NAME="nia_vsource"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPIMAGE="$(ls "$SCRIPT_DIR"/Veadotube*.AppImage 2>/dev/null | head -1)"
[ -z "$APPIMAGE" ] && APPIMAGE="$(ls "$SCRIPT_DIR"/veadotube-mini 2>/dev/null | head -1)"
RUNNER="$(command -v steam-run 2>/dev/null || echo "")"
DATA_YAML="$HOME/.veadotube/data/mini/data.yaml"

# ── helpers ────────────────────────────────────────────────────────────────
find_module_id() {
    pactl list short modules | awk -v s="$SINK_NAME" '$2=="module-loopback" && $3 ~ s {print $1}' | head -1
}

find_vsource_id() {
    pactl list short modules | awk -v s="$VSOURCE_NAME" '$2=="module-virtual-source" && $0 ~ s {print $1}' | head -1
}

sink_exists() {
    pactl list short sinks | awk '{print $2}' | grep -qx "$SINK_NAME"
}

old_default_file="$SCRIPT_DIR/.old_default_sink"
default_source_file="$SCRIPT_DIR/.old_default_source"

find_real_mic() {
    # Un micrófono físico (alsa_input) que no sea la fuente virtual.
    pactl list short sources | awk '$2 ~ /alsa_input/ && $0 !~ /monitor/ {print $2}' | head -1
}

do_setup() {
    OLD_SINK="$(pactl get-default-sink 2>/dev/null || true)"
    echo "$OLD_SINK" > "$old_default_file"
    OLD_SOURCE="$(pactl get-default-source 2>/dev/null || true)"
    echo "$OLD_SOURCE" > "$default_source_file"

    if sink_exists; then
        echo "✔ nia_loopback ya existe"
    else
        echo "→ Creando sink virtual nia_loopback..."
        pactl load-module module-null-sink sink_name="$SINK_NAME" > /dev/null
    fi

    if find_module_id | grep -q .; then
        echo "✔ Loopback ya configurado"
    else
        echo "→ Conectando monitor de nia_loopback a '$OLD_SINK'..."
        pactl load-module module-loopback \
            source="$SINK_NAME.monitor" sink="$OLD_SINK" latency_msec=20 > /dev/null
    fi

    if find_vsource_id | grep -q .; then
        echo "✔ nia_vsource ya existe"
    else
        echo "→ Creando fuente virtual nia_vsource (el mic de Veadotube)..."
        pactl load-module module-virtual-source \
            master="$SINK_NAME.monitor" source_name="$VSOURCE_NAME" \
            source_properties="device.description=Nia" > /dev/null
    fi

    echo "→ Estableciendo nia_loopback como sink por defecto..."
    pactl set-default-sink "$SINK_NAME"

    # No dejar que el mic por defecto pase a ser el monitor del loopback:
    # las apps deben seguir grabando del micrófono real. Preferimos el que
    # estaba antes; si no, un mic físico.
    if [ -s "$default_source_file" ]; then
        SAVED_SOURCE="$(cat "$default_source_file")"
        case "$SAVED_SOURCE" in
            *nia*|*vsource*) ;;
            *) pactl set-default-source "$SAVED_SOURCE" 2>/dev/null || true ;;
        esac
    else
        REAL_MIC="$(find_real_mic)"
        [ -n "$REAL_MIC" ] && pactl set-default-source "$REAL_MIC" 2>/dev/null || true
    fi

    # Veadotube: forzar mic = fuente virtual y servidor WebSocket encendido
    if [ -f "$DATA_YAML" ]; then
        sed -i "s/^micName:.*/micName: 'Nia'/" "$DATA_YAML" 2>/dev/null || true
        sed -i "s/^websocket:.*/websocket: true/" "$DATA_YAML" 2>/dev/null || true
    fi

    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  Audio listo. Veadotube Mini usará el micrófono 'Nia'  "
    echo "  (nia_vsource ← nia_loopback ← voz de Nia)"
    echo "════════════════════════════════════════════════════════"
}

do_teardown() {
    VSID="$(find_vsource_id)"
    if [ -n "$VSID" ]; then
        echo "→ Descargando fuente virtual $VSID..."
        pactl unload-module "$VSID" 2>/dev/null || true
    fi
    MODID="$(find_module_id)"
    if [ -n "$MODID" ]; then
        echo "→ Descargando módulo de loopback $MODID..."
        pactl unload-module "$MODID" 2>/dev/null || true
    fi
    if sink_exists; then
        NSMOD="$(pactl list short modules | awk -v s="$SINK_NAME" '$2=="module-null-sink" && $3 ~ s {print $1}' | head -1)"
        if [ -n "$NSMOD" ]; then
            echo "→ Eliminando sink nia_loopback (módulo $NSMOD)..."
            pactl unload-module "$NSMOD" 2>/dev/null || true
        fi
    fi
    if [ -f "$old_default_file" ]; then
        OLD="$(cat "$old_default_file")"
        [ -n "$OLD" ] && pactl set-default-sink "$OLD" 2>/dev/null || true
        rm -f "$old_default_file"
    fi
    if [ -f "$default_source_file" ]; then
        OLD_SRC="$(cat "$default_source_file")"
        case "$OLD_SRC" in
            *nia*|*vsource*) ;;
            *) [ -n "$OLD_SRC" ] && pactl set-default-source "$OLD_SRC" 2>/dev/null || true ;;
        esac
        rm -f "$default_source_file"
    fi
    echo "✔ Rutas de audio eliminadas."
}

do_launch() {
    if [ -z "$APPIMAGE" ]; then
        echo "⚠ No encontré Veadotube*.AppImage en $SCRIPT_DIR"
        echo "  Descargalo de: https://olmewe.itch.io/veadotube-mini"
        echo "  (gratis → 'No thanks, just take me to the downloads')"
        echo "  y guardalo en: $SCRIPT_DIR/"
        return 1
    fi
    chmod +x "$APPIMAGE"

    # Lanzar como servicio transitorio de systemd (sobrevive al cierre del shell).
    # Fallback: setsid+nohup si systemd-run no está disponible.
    CMD_ARGS=()
    [ -n "$RUNNER" ] && CMD_ARGS+=("$RUNNER")
    CMD_ARGS+=("$APPIMAGE")

    if command -v systemd-run >/dev/null 2>&1; then
        systemctl --user is-active app-Hyprland-veadotube.scope >/dev/null 2>&1 && {
            echo "✔ Veadotube Mini ya está corriendo (app-Hyprland-veadotube.scope)."
            return 0
        }
        # Lanzar como scope gráfico igual que las apps de Hyprland (uwsm).
        systemd-run --user --scope --slice=app-graphical.slice \
            --unit=app-Hyprland-veadotube.scope --collect \
            --setenv="DISPLAY=${DISPLAY:-:0}" \
            --setenv="WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}" \
            --setenv="XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
            --working-directory="$SCRIPT_DIR" "${CMD_ARGS[@]}" >/dev/null 2>&1 && {
            echo "✔ Veadotube Mini lanzado (app-Hyprland-veadotube.scope)."
            return 0
        }
        echo "⚠ systemd-run falló; usando lanzamiento directo."
    fi

    setsid nohup "${CMD_ARGS[@]}" >/dev/null 2>&1 < /dev/null &
    disown || true
    echo "✔ Veadotube Mini lanzado ($APPIMAGE)."
}

case "${1:-setup}" in
    setup)   do_setup; do_launch; true ;;
    teardown) do_teardown ;;
    launch)  do_launch ;;
    *) echo "Uso: $0 [setup|teardown|launch]"; exit 1 ;;
esac
