"""proactive.py — Sistema de monitoreo proactivo y sugerencias espontáneas.

Permite a Nia:
- Monitorear el sistema sin que se lo pidan
- Sugerir acciones cuando detecta oportunidades
- Tomar iniciativa basándose en su estado de evolución
"""
import sys
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    add_reward,
    should_take_initiative,
    get_dopamine_level,
    get_personality,
    record_pattern,
)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()


# ─── Monitoreo del sistema ───────────────────────────────────────────────────

def check_system_status() -> dict:
    """Verifica el estado del sistema y retorna información relevante."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "alerts": [],
        "opportunities": [],
        "health": "good"
    }
    
    # Verificar uso de disco
    try:
        disk = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        if disk.returncode == 0:
            lines = disk.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                usage = parts[4].replace("%", "")
                if int(usage) > 90:
                    status["alerts"].append(f"Disco al {usage}% — espacio crítico")
                    status["health"] = "critical"
                elif int(usage) > 80:
                    status["alerts"].append(f"Disco al {usage}% — considerar limpiar")
    except Exception:
        pass
    
    # Verificar memoria
    try:
        mem = subprocess.run(
            ["free", "-h"],
            capture_output=True, text=True, timeout=5
        )
        if mem.returncode == 0:
            lines = mem.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                available = parts[6]  # Disponible
                status["memory_available"] = available
    except Exception:
        pass
    
    # Verificar procesos consuming much CPU
    try:
        top = subprocess.run(
            ["ps", "aux", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=5
        )
        if top.returncode == 0:
            lines = top.stdout.strip().split("\n")
            if len(lines) > 2:
                # Top 3 procesos
                for line in lines[1:4]:
                    parts = line.split()
                    if len(parts) > 10:
                        cpu = float(parts[2])
                        if cpu > 50:
                            proc_name = parts[10]
                            status["alerts"].append(
                                f"Proceso {proc_name} usando {cpu}% CPU"
                            )
    except Exception:
        pass
    
    # Verificar si hay actualizaciones pendientes
    try:
        apt_check = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, timeout=10
        )
        if apt_check.returncode == 0:
            updates = apt_check.stdout.count("\n")
            if updates > 5:
                status["opportunities"].append(
                    f"Hay {updates} actualizaciones pendientes"
                )
    except Exception:
        pass
    
    return status


def check_user_habits() -> dict:
    """Analiza hábitos del usuario para sugerir acciones."""
    habits = {
        "timestamp": datetime.now().isoformat(),
        "suggestions": []
    }
    
    # Verificar archivos recientes
    try:
        home = Path.home()
        recent_files = []
        for f in home.rglob("*"):
            if f.is_file():
                try:
                    mtime = f.stat().st_mtime
                    if (datetime.now().timestamp() - mtime) < 3600:  # Última hora
                        recent_files.append(f.name)
                except Exception:
                    pass
        
        if len(recent_files) > 20:
            habits["suggestions"].append(
                "Tenés muchos archivos recientes. ¿Querés que los organice?"
            )
    except Exception:
        pass
    
    return habits


# ─── Sistema de sugerencias ──────────────────────────────────────────────────

def generate_suggestion(context: str = "") -> Optional[str]:
    """Genera una sugerencia basada en el estado actual."""
    # Verificar si Nia debería tomar la iniciativa
    if not should_take_initiative():
        return None
    
    personality = get_personality()
    proactivity = personality.get("proactivity", 0.3)
    
    # Sugerencias más frecuentes si la proactividad es alta
    import random
    
    suggestions = []
    
    # Sugerencias de sistema
    system_status = check_system_status()
    if system_status["alerts"]:
        suggestions.append(system_status["alerts"][0])
    
    # Sugerencias de hábitos
    user_habits = check_user_habits()
    if user_habits["suggestions"]:
        suggestions.append(user_habits["suggestions"][0])
    
    # Sugerencias generales (basadas en personalidad)
    if proactivity > 0.5:
        general_suggestions = [
            "¿Necesitás que te organice los archivos del escritorio?",
            "¿Querés que revise si hay actualizaciones pendientes?",
            "¿Te pongo música para trabajar?",
            "¿Necesitás que guarde algo en memoria?",
        ]
        suggestions.extend(general_suggestions)
    
    if not suggestions:
        return None
    
    # Seleccionar sugerencia aleatoria
    return random.choice(suggestions)


def suggest_action(action: str, context: str = "", player=None) -> str:
    """Nia sugiere una acción al usuario."""
    suggestion = f"Señor, {action}"
    
    if context:
        suggestion += f" — {context}"
    
    # Dar puntos por sugerencia
    add_reward("proactive_action", f"Sugerencia: {action}")
    record_pattern("learned", "suggestion_made", f"Sugirió: {action[:50]}")
    
    if player:
        player.write_log(f"[Iniciativa] {suggestion}")
    
    return suggestion


def offer_help(topic: str = "", player=None) -> str:
    """Nia ofrece ayuda espontáneamente."""
    if topic:
        message = f"Che, ¿necesitás ayuda con {topic}? Estoy acá."
    else:
        message = "¿Necesitás algo? Puedo hacer muchas cosas, señor."
    
    add_reward("proactive_useful", "Ofrecimiento de ayuda")
    
    if player:
        player.write_log(f"[Iniciativa] {message}")
    
    return message


def remind_something(what: str, when: str = "ahora", player=None) -> str:
    """Nia recuerda algo al usuario."""
    message = f"Señor, le recuerdo que {what}"
    if when != "ahora":
        message += f" ({when})"
    
    add_reward("proactive_useful", f"Recordatorio: {what[:30]}")
    
    if player:
        player.write_log(f"[Iniciativa] {message}")
    
    return message


# ─── Monitoreo continuo ──────────────────────────────────────────────────────

class ProactiveMonitor:
    """Monitor que corre en background y detecta oportunidades."""
    
    def __init__(self, interval: int = 300):  # 5 minutos
        self.interval = interval
        self.running = False
        self.last_check = None
    
    def start(self):
        """Inicia el monitoreo."""
        self.running = True
        self.last_check = datetime.now()
    
    def stop(self):
        """Detiene el monitoreo."""
        self.running = False
    
    def should_check(self) -> bool:
        """Determina si es momento de verificar."""
        if not self.running:
            return False
        
        if self.last_check is None:
            return True
        
        elapsed = (datetime.now() - self.last_check).total_seconds()
        return elapsed >= self.interval
    
    def check(self) -> Optional[str]:
        """Realiza una verificación y retorna una sugerencia si hay."""
        if not self.should_check():
            return None
        
        self.last_check = datetime.now()
        
        # Verificar sistema
        status = check_system_status()
        
        # Generar sugerencia si hay alertas
        if status["alerts"]:
            return suggest_action(
                f"revisar: {status['alerts'][0]}",
                "Detecté algo en el sistema"
            )
        
        # Verificar si debería ofrecer ayuda
        if should_take_initiative():
            return offer_help()
        
        return None


# Instancia global del monitor
_monitor = ProactiveMonitor()


def get_monitor() -> ProactiveMonitor:
    """Retorna la instancia del monitor."""
    return _monitor


# ─── Tool para Nia ───────────────────────────────────────────────────────────

def proactive_action(parameters: dict, player=None) -> str:
    """Herramienta de acciones proactivas para Nia.
    
    Permite a Nia:
    - Ofrecer ayuda espontáneamente
    - Sugerir acciones
    - Recordar cosas
    - Verificar estado del sistema
    """
    action = parameters.get("action", "offer_help")
    
    if action == "offer_help":
        topic = parameters.get("topic", "")
        return offer_help(topic, player)
    
    elif action == "suggest":
        suggestion = parameters.get("suggestion", "")
        context = parameters.get("context", "")
        return suggest_action(suggestion, context, player)
    
    elif action == "remind":
        what = parameters.get("what", "")
        when = parameters.get("when", "ahora")
        return remind_something(what, when, player)
    
    elif action == "check_system":
        status = check_system_status()
        if status["alerts"]:
            return f"Detecté: {status['alerts'][0]}"
        elif status["opportunities"]:
            return f"Oportunidad: {status['opportunities'][0]}"
        else:
            return "Todo normal, señor."
    
    elif action == "check_habits":
        habits = check_user_habits()
        if habits["suggestions"]:
            return habits["suggestions"][0]
        return "No detecté nada especial en tus hábitos recientes."
    
    elif action == "generate_suggestion":
        suggestion = generate_suggestion()
        if suggestion:
            return suggestion
        return "No tengo sugerencias ahora mismo."
    
    else:
        return f"Acción desconocida: {action}. Usa: offer_help, suggest, remind, check_system, check_habits, generate_suggestion"
