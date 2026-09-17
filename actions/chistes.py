# -*- coding: utf-8 -*-
"""chistes.py — Nia cuenta chistes por voz.

Banco local de chistes (sin internet). 'contar' o 'otro' devuelve uno al
azar sin repetir el último que ya dijo.
"""
import random

_BANCO = [
    "¿Qué le dijo un semáforo a otro? No me mires que me estoy cambiando.",
    "¿Por qué los pájaros no usan WhatsApp? Porque ya tienen Twitter.",
    "Me llamaron de la oficina para decirme que me equivoqué de piso. O sea, me despidieron del trabajo correcto.",
    "¿Qué hace un perro con un taladro? Taladrando, ¿qué iba a hacer?",
    "Mi médico me dijo: 'Tenés 5 minutos de vida'. Le respondí: '¿Puedo hacer una llamada?'. Dijo: 'Claro'. Entonces llamé a mi mujer y le pedí la comida que siempre me negó.",
    "La maestra le pregunta a Jaimito: '¿Cuánto es 2 + 2?'. Responde: '¿Feriado o día común?'.",
    "¿Cuál es el colmo de un electricista? No tener contacto con nadie.",
    "Dos huevos en una sartén. Uno dice: 'Ay, qué calor'. El otro dice: '¡Uf! Se me pianta un huevo'.",
    "¿Qué le dice una piedra a otra? ¿Somos almas gemelas? No, somos piedras.",
    "Fui a una librería y pregunté por el libro 'Cómo dejar de procrastinar'... lo voy a comprar la semana que viene.",
    "¿Qué hace una abeja en el gimnasio? Zum-ba.",
    "Entra un hombre a un bar y pide agua. El cantinero le dice: '¿Y así, sin alcohol?' 'Es que me lo recomendó el médico'. '¿El doctor?', dice el cantinero. 'No, un vaso de agua'.",
    "¿Cuál es el animal más elegante? El ciervo, porque siempre anda con corbata.",
    "Llamo al soporte técnico: 'Mi teclado no anda'. Me dicen: '¿Está enchufado?'. 'Sí'. '¿Lo ve en el escritorio?' 'No'. 'Ah, entonces no anda'.",
    "El hijo le pregunta a su papá: 'Papá, ¿qué es un optimista?'. Y le responde: 'Alguien que compra una tarjeta de cumpleaños para un amigo que todavía le debe plata'.",
    "Esto es un tubo de ensayo con dos neuronas. Una le dice a la otra: '¿Tenés pendiente alguna conexión?'.",
    "Me dijeron 3 tesoros: la salud, los amigos y no caerse con el auto a un lago helado en pleno invierno. No entendí, pero anoto.",
    "¿Sabés por qué los informáticos se confunden en Halloween? Porque los árboles tienen muchos árboles de decisión.",
    "Mi navegación habla: le pido 'Google Maps' y me dice 'en dos años serás Google Pérez'.",
    "Le pregunto a Nia: '¿Contame un chiste?'. Me dice: 'Mirá mi discurso cuando se corta el internet'. ¡Ja! Eso nunca pasó, soy reflexiva.",
    "¿Cuántos argentinos hacen falta para cambiar una lamparita? Diez: uno la cambia y nueve hablan de cómo la hubiera cambiado mejor.",
    "En el kiosco: '¿Tenés pilas?' 'Sí, ¿de qué marca?' 'De la que mejor me vaya.'",
    "Un chocolate le dice a otro: '¿Dónde está la nieve?'. Y el otro: 'Morí, no te gastes'.",
    "¿Qué le dijo el 0 al 8? Che, qué lindo cinturón.",
    "El hombre que inventó el Yo-Yo era un optimista: cuando lo mandaron a dibujar un círculo, dibujó dos.",
]

_ultimo = [""]


def chistes(parameters: dict, player=None, speak=None) -> str:
    """Cuenta chistes por voz (banco local)."""
    action = str(parameters.get("action", "contar")).strip().lower()

    if action in ("test",):
        return f"El banco de chistes funciona ({len(_BANCO)} guardados)."

    opciones = [c for c in _BANCO if c != _ultimo[0]] or _BANCO
    chiste = random.choice(opciones)
    _ultimo[0] = chiste
    if player:
        player.write_log("😂 " + chiste)
    return chiste