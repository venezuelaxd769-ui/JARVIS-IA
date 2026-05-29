"""system_monitor.py — Complete system hardware metrics, processes control and PC Health troubleshooter."""
import psutil
import time
import os
import subprocess
from datetime import datetime

def system_monitor(parameters: dict = None, player=None) -> str:
    """
    Diagnose PC issues, check system performance, hardware metrics, list/kill running processes.
    """
    if parameters is None:
        parameters = {}
        
    action = parameters.get("action", "report").lower().strip()
    sort_by = parameters.get("sort_by", "cpu").lower().strip()
    count = parameters.get("count", 10)
    name = parameters.get("name", "").strip()

    try:
        if action == "cpu":
            cpu_usage = psutil.cpu_percent(interval=0.5)
            cpu_freq = psutil.cpu_freq()
            cores_phys = psutil.cpu_count(logical=False)
            cores_log = psutil.cpu_count(logical=True)
            freq_msg = f"{cpu_freq.current:.1f} MHz" if cpu_freq else "N/A"
            report = (
                f"--- DETALLE DE CPU ---\n"
                f"Uso de CPU: {cpu_usage}%\n"
                f"Frecuencia actual: {freq_msg}\n"
                f"Núcleos físicos: {cores_phys} | Hilos lógicos: {cores_log}\n"
            )
            if player:
                player.write_log(f"💻 CPU: {cpu_usage}%")
            return report

        elif action == "ram":
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            used_gb = mem.used / (1024 ** 3)
            free_gb = mem.available / (1024 ** 3)
            report = (
                f"--- DETALLE DE MEMORIA RAM ---\n"
                f"Uso de RAM: {mem.percent}%\n"
                f"Total: {total_gb:.2f} GB | Usado: {used_gb:.2f} GB | Libre: {free_gb:.2f} GB\n"
            )
            if player:
                player.write_log(f"💻 RAM: {mem.percent}%")
            return report

        elif action == "disk":
            partitions = psutil.disk_partitions()
            report = "--- ESPACIO EN DISCOS ---\n"
            for part in partitions:
                if 'cdrom' in part.opts or not part.device:
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    total_gb = usage.total / (1024 ** 3)
                    used_gb = usage.used / (1024 ** 3)
                    free_gb = usage.free / (1024 ** 3)
                    report += (
                        f"Unidad {part.device} ({part.fstype}):\n"
                        f"  -> Uso: {usage.percent}% | Total: {total_gb:.1f} GB | Libre: {free_gb:.1f} GB\n"
                    )
                except Exception:
                    pass
            return report

        elif action == "network":
            # Realizar una prueba de latencia (ping) a Google DNS para comprobar internet
            latency_msg = "Prueba de Ping: "
            try:
                import socket
                start_time = time.time()
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                latency = (time.time() - start_time) * 1000
                latency_msg += f"Exitosa! Latencia: {latency:.1f} ms"
            except Exception:
                latency_msg += "¡Desconectado! Sin acceso a Internet."

            net_io = psutil.net_io_counters()
            sent_mb = net_io.bytes_sent / (1024 * 1024)
            recv_mb = net_io.bytes_recv / (1024 * 1024)
            
            report = (
                f"--- DIAGNÓSTICO DE RED ---\n"
                f"Estado: {latency_msg}\n"
                f"Datos Enviados: {sent_mb:.2f} MB\n"
                f"Datos Recibidos: {recv_mb:.2f} MB\n"
            )
            return report

        elif action == "gpu":
            # Intento de obtener estadísticas de GPU en Windows
            report = "--- ESTADO DE GPU ---\n"
            try:
                # Usar comando de Windows nvidia-smi si tiene NVIDIA
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
                )
                if res.returncode == 0 and res.stdout.strip():
                    parts = res.stdout.strip().split(",")
                    report += (
                        f"Modelo: {parts[0].strip()}\n"
                        f"Temperatura: {parts[1].strip()}°C\n"
                        f"Uso de GPU: {parts[2].strip()}%\n"
                        f"Memoria VRAM: {parts[3].strip()}MB / {parts[4].strip()}MB\n"
                    )
                else:
                    report += "GPU dedicada (NVIDIA) no detectada o no responde. Usando GPU del procesador / estándar."
            except Exception:
                report += "Información de GPU no disponible mediante nvidia-smi."
            return report

        elif action == "temperature":
            report = "--- TEMPERATURA DEL SISTEMA ---\n"
            try:
                # En Windows, psutil.sensors_temperatures() no funciona directamente, se usa wmi fallback
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root\\wmi | Select-Object -ExpandProperty CurrentTemperature"],
                    capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
                )
                if res.returncode == 0 and res.stdout.strip():
                    # Kelvin decikelvins to Celsius
                    val = float(res.stdout.strip().split()[0])
                    celsius = (val / 10.0) - 273.15
                    report += f"Temperatura CPU: {celsius:.1f}°C\n"
                else:
                    report += "Sensores de hardware de temperatura bloqueados o no disponibles bajo Windows estándar."
            except Exception:
                report += "Sensores de temperatura no soportados en esta PC."
            return report

        elif action == "battery":
            battery = psutil.sensors_battery()
            if battery:
                plugged = "Cargando (Conectado)" if battery.power_plugged else "Descargando (Batería)"
                mins_left = battery.secsleft // 60
                time_left = f"{mins_left} minutos" if battery.secsleft != -1 else "N/A"
                report = (
                    f"--- ESTADO DE BATERÍA ---\n"
                    f"Carga: {battery.percent}%\n"
                    f"Estado de carga: {plugged}\n"
                    f"Tiempo restante: {time_left}\n"
                )
            else:
                report = "Batería no detectada (esta PC parece ser de escritorio)."
            return report

        elif action == "uptime":
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_duration = datetime.now() - boot_time
            days = uptime_duration.days
            hours, remainder = divmod(uptime_duration.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            report = (
                f"--- TIEMPO DE ACTIVIDAD ---\n"
                f"Sistema iniciado el: {boot_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Uptime: {days} días, {hours} horas, {minutes} minutes.\n"
            )
            return report

        elif action == "processes":
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    p_info = p.info
                    p_info['cpu'] = p.cpu_percent(interval=None)
                    p_info['mem_mb'] = p.memory_info().rss / (1024 * 1024)
                    procs.append(p_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Ordenar
            if sort_by == "ram":
                procs = sorted(procs, key=lambda x: x['mem_mb'], reverse=True)
                header_sort = "Memoria (MB)"
            else:
                procs = sorted(procs, key=lambda x: x['cpu'], reverse=True)
                header_sort = "CPU (%)"
                
            report = f"--- PROCESOS ACTIVOS (TOP {count} por {sort_by.upper()}) ---\n"
            report += f"{'PID':<8}{'NOMBRE':<25}{'CPU (%)':<12}{'MEMORIA (MB)':<15}\n"
            for p in procs[:count]:
                name_trimmed = p['name'][:22]
                report += f"{p['pid']:<8}{name_trimmed:<25}{p['cpu']:<12.1f}{p['mem_mb']:<15.1f}\n"
            return report

        elif action == "kill":
            if not name:
                return "Error: Debes especificar el nombre o PID del proceso para detenerlo."
            
            killed = []
            # Intentar primero por PID
            if name.isdigit():
                try:
                    pid = int(name)
                    p = psutil.Process(pid)
                    p_name = p.name()
                    p.terminate()
                    return f"Proceso '{p_name}' (PID {pid}) detenido exitosamente, señor."
                except Exception as e:
                    return f"Error al detener proceso por PID: {e}"
            
            # Buscar por nombre
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    if name.lower() in p.info['name'].lower():
                        p.terminate()
                        killed.append(f"{p.info['name']} (PID {p.info['pid']})")
                except Exception:
                    pass
            
            if killed:
                return f"Procesos terminados exitosamente:\n" + "\n".join(killed)
            return f"No se encontró ningún proceso activo que coincida con '{name}'."

        elif action == "report":
            # --- COMPREHENSIVE PC HEALTH DIAGNOSTIC TROUBLESHOOTER ---
            cpu = psutil.cpu_percent(interval=0.3)
            ram = psutil.virtual_memory()
            disk_c = psutil.disk_usage("C:")
            battery = psutil.sensors_battery()
            
            # Diagnóstico de Internet
            connected = False
            latency = 999.0
            try:
                import socket
                start = time.time()
                socket.create_connection(("8.8.8.8", 53), timeout=2.0)
                latency = (time.time() - start) * 1000
                connected = True
            except Exception:
                pass

            # Obtener top 3 procesos pesados por CPU
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    p_info = p.info
                    p_info['cpu'] = p.cpu_percent(interval=None)
                    procs.append(p_info)
                except Exception:
                    pass
            top_cpu = sorted(procs, key=lambda x: x.get('cpu', 0), reverse=True)[:3]

            # Analizar anomalías y armar el reporte
            anomalies = []
            recommendations = []

            if cpu > 80:
                anomalies.append(f"⚠️ Alto Uso de CPU ({cpu}%)")
                recommendations.append("CPU sobrecargada. Te sugiero detener procesos pesados o tareas de renderizado inactivas.")
            if ram.percent > 85:
                anomalies.append(f"⚠️ Memoria RAM Crítica ({ram.percent}%)")
                recommendations.append("RAM casi llena. Cierra pestañas de navegador inactivas o aplicaciones en segundo plano.")
            
            free_disk_gb = disk_c.free / (1024 ** 3)
            if free_disk_gb < 15:
                anomalies.append(f"⚠️ Bajo Espacio en Disco C: ({free_disk_gb:.1f} GB libres)")
                recommendations.append("El disco de sistema C: está casi lleno. Te sugiero limpiar archivos temporales o desinstalar aplicaciones pesadas.")
            
            if not connected:
                anomalies.append("⚠️ Sin Conexión a Internet")
                recommendations.append("Comprueba tu router WiFi o cable Ethernet. La conexión externa está inactiva.")
            elif latency > 180:
                anomalies.append(f"⚠️ Latencia de Red Alta ({latency:.1f} ms)")
                recommendations.append("Red muy lenta o saturada. Evita descargas activas en este momento.")

            # Formatear el reporte de Salud de JARVIS
            diag_title = "📋 REPORTE DE SALUD Y DIAGNÓSTICO DE PC"
            status_text = "ÓPTIMO (Tu PC funciona sin problemas, señor)." if not anomalies else f"ATENCIÓN REQUERIDA ({len(anomalies)} alertas detectadas)"
            
            report = (
                f"==================================================\n"
                f"   {diag_title}\n"
                f"==================================================\n"
                f"Fecha del Diagnóstico: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Estado General: {status_text}\n\n"
                f"--- MÉTRICAS HARDWARE PRINCIPALES ---\n"
                f"• CPU: {cpu}% de uso continuo\n"
                f"• RAM: {ram.percent}% de uso ({ram.available / (1024**3):.2f} GB libres de {ram.total / (1024**3):.1f} GB total)\n"
                f"• Disco C: {disk_c.percent}% ocupado ({free_disk_gb:.1f} GB libres)\n"
                f"• Conectividad de Red: {'Conectado (' + f'{latency:.1f} ms)' if connected else 'Desconectado'}\n"
            )
            
            if battery:
                plug = "Conectado a la corriente" if battery.power_plugged else "Usando batería"
                report += f"• Batería: {battery.percent}% ({plug})\n"
                
            if anomalies:
                report += "\n--- ALERTAS DETECTADAS ---\n"
                for a in anomalies:
                    report += f" {a}\n"
                    
                report += "\n--- RECOMENDACIONES DE SOLUCIÓN ---\n"
                for r in recommendations:
                    report += f" -> {r}\n"
            else:
                report += "\n--- ANÁLISIS DE SENSORES DE SALUD ---\n"
                report += "✨ Todos los sensores operan dentro de los rangos normales. ¡Excelente desempeño, señor!\n"

            if top_cpu:
                report += "\n--- PROCESOS CON MAYOR CONSUMO DE CPU ---\n"
                for i, p in enumerate(top_cpu, 1):
                    report += f"{i}. {p['name']} (PID {p['pid']}) -> {p['cpu']:.1f}% CPU\n"

            if player:
                player.write_log("💻 Diagnóstico de PC completado.")
            return report

        else:
            return f"Error: Acción '{action}' no es soportada en system_monitor."

    except Exception as e:
        return f"Error al recuperar métricas de rendimiento y diagnóstico: {e}"
