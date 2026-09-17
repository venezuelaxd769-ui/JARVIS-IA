"""sandbox — frontera de acción de Nia (regla de autonomía).

Filosofía (regla de oro: el límite va en la autonomía, no en el conocimiento):
- El sandbox es el espacio aislado donde Nia guarda y trabaja sin pedir permiso.
- Todo lo que toque fuera del sandbox (archivos, borrados, comandos no whitelisteados)
  exige la frase de confirmación explícita del Señor: "SÍ autorizo".
- Ninguna tool debería inventarse el permiso: solo se concede si el usuario lo dijo.
"""

from pathlib import Path

SANDBOX = Path.home() / "NiaSandbox"
CONFIRM_PHRASE = "SÍ autorizo"


def confirm_granted(parameters: dict) -> bool:
    """True solo si el usuario dio la frase exacta de autorización."""
    return str((parameters or {}).get("confirm", "")) == CONFIRM_PHRASE


def in_sandbox(path) -> bool:
    """True si el path está dentro del sandbox (o no se puede resolver)."""
    try:
        p = Path(path).expanduser().resolve()
        return p == SANDBOX.resolve() or SANDBOX.resolve() in p.parents
    except Exception:
        return False