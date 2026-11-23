@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute primeiro iniciar_windows.bat para configurar o projeto.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" gerenciar_postgresql.py iniciar
pause
