@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute primeiro iniciar_windows.bat para configurar o projeto.
    pause
    exit /b 1
)
if not defined LOJINHA_PG_DUMP if exist "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" set "LOJINHA_PG_DUMP=C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"
".venv\Scripts\python.exe" gerenciar_postgresql.py backup
pause
