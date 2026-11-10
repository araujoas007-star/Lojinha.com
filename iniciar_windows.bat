@echo off
title Lojinha.com - Configuracao inicial
echo ==========================================
echo       Lojinha.com - Loja de Conveniencia
echo ==========================================
echo.
if not exist .venv (
    echo Criando ambiente virtual...
    py -m venv .venv
    if errorlevel 1 (
        echo Nao foi possivel criar o ambiente virtual. Confira se Python esta instalado.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate
echo Instalando dependencias...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Erro ao instalar dependencias. Confira sua conexao com a internet.
    pause
    exit /b 1
)
echo.
echo Preparando o banco de dados...
python manage.py migrate
if errorlevel 1 (
    echo Erro ao preparar o banco de dados.
    pause
    exit /b 1
)
echo.
echo Configuracao concluida!
echo Para iniciar o site, execute iniciar_site.bat
pause
