# -*- coding: utf-8 -*-
"""calculadora.py — Cuentas por voz con evaluación segura.

Traduce frases en español a una expresión aritmética y la resuelve con un
AST whitelist (solo números + operadores aritméticos + raíz cuadrada), sin
ejecutar código arbitrario.
"""
import ast
import math
import operator
import re

_OP = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


_FUENTE = ('más', 'mas', 'menos', 'por', 'dividido', 'sobre', 'cuadrado',
           'cubo', 'elevado', 'raiz', 'raíz', '%')


def _normalizar(expr):
    e = str(expr or "").strip().lower()
    e = re.sub(r"[¿?¡!]", " ", e)
    e = e.replace("raíz", "raiz")
    e = re.sub(r"\bcuanto es\b|\bcuánto es\b|\bcalc(ul[ai]?|úle?)\b|hac[eé]\b|s[aá]came\b", " ", e)
    e = e.replace("por ciento de", "% de")
    e = re.sub(r"(\d+(?:[.,]\d+)?)\s*%\s*de\s*(\d+(?:[.,]\d+)?)",
               r"((\1/100)*\2)", e)
    e = re.sub(r"raiz(?:\s+cuadrada)?\s+de\s+(\d+(?:[.,]\d+)?)", r"sqrt(\1)", e)
    e = e.replace("raiz(", "sqrt(")
    e = re.sub(r"\b(al )?cuadrado\b", "**2", e)
    e = re.sub(r"\b(al )?cubo\b", "**3", e)
    e = re.sub(r"\belevado\s+(a|al)\s+(\d+)\b", r"**\2", e)
    e = re.sub(r"\bmas\b|\bmás\b", "+", e)
    e = re.sub(r"\bes\b|\bde\b|\bdel\b", " ", e)
    e = e.replace("dividido", "/")
    e = e.replace("sobre", "/")
    e = re.sub(r"\bpor\b", "*", e)
    e = re.sub(r"\bmenos\b", "-", e)
    e = e.replace("x", "*").replace("×", "*").replace(":", "/").replace("÷", "/")
    e = e.replace(",", ".")
    e = e.replace("√", "sqrt(")
    e = e.replace("sqrt(", "%(")               # proteger "sqrt(" de la limpieza
    e = re.sub(r"[^0-9+\-*/().%\^<> ]", " ", e)
    e = e.replace("%(", "sqrt(")               # restaurar
    e = re.sub(r"\s+", " ", e).strip()
    abre = e.count("(")
    cierra = e.count(")")
    if abre > cierra:
        e += ")" * (abre - cierra)
    return e


class _Checker(ast.NodeVisitor):
    def visit_Expression(self, node):
        self.visit(node.body)

    def visit_BinOp(self, node):
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node):
        self.visit(node.operand)

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, float)):
            raise ValueError("solo números")

    def visit_Name(self, node):
        if node.id != "sqrt":
            raise ValueError("nombre no permitido")

    def visit_Call(self, node):
        if not (isinstance(node.func, ast.Name)
                and node.func.id == "sqrt"
                and len(node.args) == 1):
            raise ValueError("función no permitida")
        self.visit(node.args[0])


def _evaluar(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call):
        a = _evaluar(node.args[0])
        return math.sqrt(float(a))
    if isinstance(node, ast.UnaryOp):
        return _OP[type(node.op)](_evaluar(node.operand))
    a = _evaluar(node.left)
    b = _evaluar(node.right)
    fn = _OP.get(type(node.op))
    if fn is None:
        raise ValueError(f"operador no permitido: {type(node.op).__name__}")
    return fn(a, b)


def _formatear(v):
    if isinstance(v, float):
        if math.isinf(v) or math.isnan(v):
            return "infinito (no puedo dividir por cero)"
        if abs(v) > 1e12 or (0 < abs(v) < 1e-6):
            return f"{v:.4e}"
        v = round(v, 6)
        if v == int(v):
            v = int(v)
    return f"{v:,}".replace(",", ".")


def calculadora(parameters: dict, player=None, speak=None) -> str:
    """Resuelve una cuenta dicha por voz (expresión en español)."""
    expr = str(parameters.get("expression", "") or parameters.get("cuenta", "")).strip()
    if not expr:
        return "Decime una cuenta, por ejemplo: ¿cuánto es 15 por ciento de 800? o (6 por 2) más 9."
    limpia = _normalizar(expr)
    if not limpia or not re.search(r"\d", limpia):
        return (f"No entendí '{expr}' como cuenta. Decila con números y símbolos, "
                f"por ejemplo: 'cuánto es 12 más 8' o 'la raíz cuadrada de 144'.")
    try:
        arbol = ast.parse(limpia, mode="eval")
        _Checker().visit(arbol)
        resultado = _formatear(_evaluar(arbol.body))
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as e:
        return f"No pude resolver '{expr}'. {e}"
    except Exception:
        return f"Ups, algo salió mal resolviendo '{expr}'."
    if player:
        player.write_log(f"🧮 {expr} = {resultado}")
    return f"{resultado}"