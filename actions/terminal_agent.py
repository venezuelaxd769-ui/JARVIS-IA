import subprocess
import os
import uuid
import time
from pathlib import Path

def terminal_agent(parameters: dict, player=None) -> str:
    """
    Ejecuta cualquier comando en la terminal de Linux (bash/sh).
    Nia puede usar esto para cualquier tarea del sistema operativo:
    instalar/desinstalar programas, consultar información, ejecutar scripts,
    manejar archivos, redes, configuraciones, etc.
    """
    command = parameters.get("command", "")
    shell_type = parameters.get("shell", "bash").lower()
    timeout_sec = int(parameters.get("timeout", 120))
    working_dir = parameters.get("working_directory", None)

    if not command:
        return "No se proporcionó ningún comando para ejecutar."

    # Capa de seguridad: Pre-filtro de comandos destructivos
    DANGEROUS_PATTERNS = [
        # Borrado destructivo de raíz/sistema
        "rm -rf /", "rm -fr /", "rm -rf /*", "rm -fr /*", "rm -rf ~", "rm -fr ~",
        "rm -rf .", "rm -fr .", "rm -rf $home", "rm -fr $home",
        "chmod -r 000 /", "chmod -r 000 *", "chown -r nobody /",
        # Formateo/particionado de discos
        "mkfs", "format ", "dd if=", "dd of=/dev", "> /dev/sda", "> /dev/hda",
        "fdisk", "parted", "wipefs", "gparted",
        # Apagado / reinicio del sistema
        "poweroff", "shutdown", "init 0", "init 6", "reboot", "halt",
        "systemctl poweroff", "systemctl reboot",
        # Fork bomb / abuso de recursos
        "|| :(){ :|:& };:", ":(){ :|:& };:", "chmod -r 000 /",
        # Borrado de directorios críticos
        "mv / /dev/null", "mv /* /dev/null", "rm -rf /boot", "rm -rf /etc",
        "rm -rf /usr", "rm -rf /var", "rm -rf /home/*", "rm -rf ~/.*",
        "truncate -s 0 /dev/", "shred -", "> /etc/passwd", "> /etc/shadow",
        "echo > /dev/sd", "yes > /dev/null &",
        # Descargar y ejecutar remoto (riesgo de malware)
        "curl ... | sh", "curl ... | bash", "wget ... | sh", "wget ... | bash",
        "sudo rm", "sudo dd", "sudo mkfs",
    ]
    cmd_lower = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return (
                "⚠️ ALERTA DE SEGURIDAD: Se ha bloqueado la ejecución automática de este comando "
                f"debido a la presencia de un patrón peligroso ('{pattern}')."
            )

    # Limitar timeout a un rango razonable
    timeout_sec = max(10, min(timeout_sec, 600))

    # Ejecución en Linux
    try:
        if shell_type == "sh":
            cmd_args = ["sh", "-c", command]
        else:
            cmd_args = ["bash", "-c", command]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=working_dir,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            if output:
                if len(output) > 3000:
                    output = output[:3000] + "\n...[Salida truncada]"
                return f"Comando ejecutado exitosamente:\n{output}"
            else:
                return "Comando ejecutado exitosamente (sin salida)."
        else:
            combined = ""
            if error:
                combined += f"STDERR:\n{error}\n"
            if output:
                combined += f"STDOUT:\n{output}"
            if not combined:
                combined = "(sin salida de error)"
            return f"El comando finalizó con código {result.returncode}:\n{combined}"

    except subprocess.TimeoutExpired:
        return f"Error: El comando excedió el timeout de {timeout_sec} segundos y fue terminado."
    except FileNotFoundError:
        return f"Error: No se encontró el ejecutable para shell '{shell_type}'."
    except Exception as e:
        return f"Excepción ejecutando terminal: {str(e)}"
