@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%"

set "PY=%ROOT%\.venv\Scripts\python.exe"
set "MAIN=%ROOT%\main.py"
set "MAINC=%ROOT%\main.pyc"

REM verificar RAM libre: si está justa, avisar (la PC tiene 4 GB físicos)
for /f "tokens=2 delims==" %%A in ('wmic OS get FreePhysicalMemory /value') do set "FREEMB=%%A"
if not "%FREEMB%"=="" if %FREEMB% LSS 600000 (
    echo.
    echo  AVISO: la RAM libre es baja (%FREEMB:~0,-0% KB aprox).
    echo  Cerra el navegador y programas abiertos para que Nia funcione estable.
    echo  Sin RAM libre, Nia se cierra sola al arrancar.
    echo.
)
REM OJO: se usa python.exe (no pythonw.exe) con salida a archivo: en este equipo
REM pythonw.exe / stdout nulo hace que el proceso muera a los ~15s.
if exist "%PY%" (
    if exist "%MAIN%"  ( start "Nia - Asistente" /MIN cmd /c ""%PY%" "%MAIN%" >> "%ROOT%\stdout.log" 2>&1" & goto :done )
    if exist "%MAINC%" ( start "Nia - Asistente" /MIN cmd /c ""%PY%" "%MAINC%" >> "%ROOT%\stdout.log" 2>&1" & goto :done )
)

echo JARVIS Beta: no se encontro Python o main.py.
echo Ejecuta primero "Instalar_JARVIS.bat" para instalar el entorno.
pause
:done
popd
endlocal
