# -*- coding: utf-8 -*-
"""system_network.py — Red y WiFi del equipo por voz (Windows).

Estado de conexión, IPs de los adaptadores activos, listar redes WiFi,
conectarse (con o sin contraseña) y desconectarse.
"""
import os
import re
import subprocess
import tempfile

_IS_WIN = os.name == "nt"


def _ps(cmd):
    kw = {}
    if _IS_WIN:
        kw["creationflags"] = 0x08000000
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + cmd],
            capture_output=True, timeout=45, **kw)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return r.returncode, out, err
    except Exception as e:
        return None, "", str(e)


def _health():
    code, out, err = _ps(
        "Get-NetIPConfiguration | Where-Object { $_.IPv4Address } | "
        "ForEach-Object { \"$($_.InterfaceAlias)|$(($_.IPv4Address.IPAddress))\" }")
    if code != 0:
        return "No pude leer el estado de red."
    lineas = []
    for l in out.splitlines():
        l = l.strip()
        if not l:
            continue
        partes = l.split("|")
        if len(partes) >= 2:
            lineas.append(f"   • {partes[0]}: {partes[1] or 'sin IP'}")
    if not lineas:
        return "No hay conexión de red activa en este momento."
    return "🌐 Conexiones activas:\n" + "\n".join(lineas)


def _wifi_list():
    code, out, err = _ps("netsh wlan show networks mode=bssid")
    if code != 0 or not out.strip():
        return "No pude listar las redes WiFi (¿el WiFi está activo?)."
    redes = []
    ssid = signal = actual = None
    for l in out.splitlines():
        l = l.strip()
        if not l:
            continue
        m = re.search(r"^SSID\s*\d+\s*:\s*(.*)", l, re.I)
        if m:
            if ssid:
                redes.append((ssid, signal or "?"))
            ssid = m.group(1).strip()
            signal = None
            continue
        m = re.search(r"(Señal|Signal)\s*:\s*(\d+)%", l, re.I)
        if m and ssid:
            cur = int(m.group(2))
            if signal is None or cur > signal:
                signal = cur
            continue
    if ssid:
        redes.append((ssid, signal or "?"))
    if not redes:
        return "No encontré redes WiFi cercanas."
    _code, iout, _err = _ps("netsh wlan show interfaces")
    for l in iout.splitlines():
        m = re.search(r"SSID\s*:\s*(.*)", l, re.I)
        if m:
            actual = m.group(1).strip()
            break
    lineas = [f"📶 {len(redes)} red(es) WiFi:"]
    for s, sig in networks_top(redes):
        marca = " (conectada)" if s.lower() == (actual or "").lower() else ""
        chips = "🟢🟢🟢🟢" if sig == "?" else ("🟢🟢🟢🟢" if sig > 75 else "🟢🟢🟢" if sig > 50 else "🟢🟢" if sig > 25 else "🟢")
        lineas.append(f"   • {s}{marca} {chips}")
    return "\n".join(lineas)


def networks_top(redes):
    by_name = {}
    for s, sig in redes:
        prev = by_name.get(s)
        if prev is None or sig == "?":
            pass
        if prev is None or (prev == "?" and sig != "?") or (sig != "?" and prev != "?" and sig > int(prev)):
            by_name[s] = sig
    out = [(s, sig if sig is not None else "?") for s, sig in by_name.items()]
    out.sort(key=lambda t: 0 if t[1] == "?" else -int(t[1]))
    return out[:10]


def _wifi_connect(ssid, password):
    if password:
        escaped = ssid.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        xmlesc = password.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        xml = (
            '<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
            f"<name>{escaped}</name>"
            "<SSIDConfig><SSID><name>%s</name></SSID></SSIDConfig>"
            "<connectionType>ESS</connectionType><connectionMode>auto</connectionMode>"
            "<MSM><security><authEncryption><authentication>WPA2PSK</authentication>"
            "<encryption>AES</encryption><useOneX>false</useOneX></authEncryption>"
            "<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>%s</keyMaterial></sharedKey>"
            "</security></MSM></WLANProfile>" % (escaped, xmlesc)
        )
        tmp = os.path.join(tempfile.gettempdir(), "nia_wifi_tmp.xml")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(xml)
        code, out, err = _ps(f'netsh wlan add profile filename="{tmp}" user=current')
        try:
            os.remove(tmp)
        except OSError:
            pass
        if code != 0:
            return f"No pude guardar el perfil de '{ssid}': {err or out}"
    code, out, err = _ps(f'netsh wlan connect name="{ssid}"')
    if code == 0:
        return f"Conectando a '{ssid}'…"
    return f"No pude conectarme a '{ssid}': {err or out}"


def _dispositivos():
    vendor = {
        "A4:83:E7": "Realtek?/AP chico", "30:DE:4B": "TP-Link", "78:02:F8": "TP-Link",
        "3C:97:0E": "TP-Link", "98:DE:D0": "TP-Link", "BC:E9:FC": "Intel",
        "48:B0:2D": "Xiaomi", "8C:DE:F9": "Xiaomi", "F0:9F:C2": "Xiaomi",
        "5C:F9:DD": "Apple", "A8:XX": "Apple", "00:17:88": "Samsung",
        "5C:93:A2": "Samsung", "F0:43:47": "Samsung", "10:27:F5": "Samsung",
        "FE:FF:FF": "Multicast", "01:00:5E": "Multicast",
    }

    def vend(mac):
        for pref, name in vendor.items():
            if mac.replace(":", "")[:6].upper() == pref.replace(":", "")[:6].upper():
                return name
        return "desconocido"

    def _arp():
        try:
            r = subprocess.run(["arp", "-a"], capture_output=True,
                               timeout=15, creationflags=0x08000000)
            return (r.stdout or b"").decode("utf-8", "replace")
        except Exception:
            return ""

    out = _arp()
    grupos = {}
    my_iface = "tu red"
    for l in (out or "").splitlines():
        l = l.strip()
        if not l:
            continue
        if l.lower().startswith("interfaz:") and "---" in l:
            my_iface = l.split(":")[1].split("---")[0].strip()
            continue
        partes = l.split()
        if len(partes) >= 3 and (":" in partes[1] or "-" in partes[1]):
            ip = partes[0]
            mac = partes[1].upper().replace("-", ":")
            if mac.startswith("FF:") or ip.startswith(("224.", "239.", "255.")):
                continue
            if mac == "00:00:00:00:00:00":
                continue
            grupos.setdefault(my_iface, []).append((ip, mac, vend(mac)))
    total = sum(len(v) for v in grupos.values())
    if total == 0:
        return ("No logré armar el mapa (probá con Nia con permisos de admin). "
                "Datos que conozco hoy:")
    lineas = [f"🛰️ {total} dispositivo(s) en tu red:"]
    for red, items in grupos.items():
        lineas.append(f"  {red}:")
        for ip, mac, v in items:
            lineas.append(f"   • {ip} — {mac} ({v})")
    return "\n".join(lineas)


def system_network(parameters: dict, player=None, speak=None) -> str:
    """Red y WiFi: estado de conexión, listar redes, conectar o desconectar."""
    action = str(parameters.get("action", "estado")).strip().lower()
    ssid = str(parameters.get("ssid", "")).strip()
    password = str(parameters.get("password", "")).strip()
    if player:
        player.write_log(f"🌐 system_network: {action}")
    if not _IS_WIN:
        return "Solo en Windows gestiono la red."

    if action in ("estado", "info", "ver"):
        return _health()

    if action in ("wifi", "redes", "listar"):
        return _wifi_list()

    if action in ("conectar", "connect", "unirse"):
        if not ssid:
            return "Decime a qué red conectarme (ssid) y, si es nueva, la contraseña (password)."
        return _wifi_connect(ssid, password)

    if action in ("desconectar", "disconnect", "salir"):
        code, out, err = _ps("netsh wlan disconnect")
        return "Desconecté el WiFi." if code == 0 else f"No pude desconectarme: {err or out}"

    if action in ("dispositivos", "devices", "quien", "quién", "red_local"):
        return _dispositivos()

    return "Acciones: estado | wifi | conectar (ssid, password opcional) | desconectar | dispositivos."


if __name__ == "__main__":
    import sys
    print(system_network({"action": sys.argv[1] if len(sys.argv) > 1 else "estado",
                          "ssid": sys.argv[2] if len(sys.argv) > 2 else ""}))