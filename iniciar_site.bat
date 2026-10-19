@echo off
title Lojinha.com
if not exist .venv\Scripts\activate.bat (
    echo Execute primeiro iniciar_windows.bat para configurar o projeto.
    pause
    exit /b 1
)
call .venv\Scripts\activate
python manage.py runserver
pause
