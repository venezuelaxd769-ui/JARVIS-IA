import datetime

def cuenta_dias(parameters: dict, player=None) -> str:
    fecha_str = parameters.get("fecha")
    if not fecha_str:
        return "Che, necesito que me pases una fecha en formato YYYY-MM-DD."
    
    try:
        fecha_obj = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Esa fecha no tiene pinta de estar en formato YYYY-MM-DD. Probá de nuevo."
    
    hoy = datetime.date.today()
    
    if fecha_obj < hoy:
        return "Ya pasó esa fecha, capo."
    
    dias_faltantes = (fecha_obj - hoy).days
    
    if dias_faltantes == 0:
        return "¡Es hoy! ¡Dale que se puede!"
    elif dias_faltantes == 1:
        return "Falta solo 1 día. ¡A prepararse!"
    else:
        return f"Faltan {dias_faltantes} días. ¡Vamos que llegas!"