@echo off
setlocal
set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
pushd "%SCRIPT_DIR%"

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.12+ nao encontrado. Instale Python e tente novamente.
        pause
        popd
        exit /b 1
    )
    set PY_CMD=python
) else (
    set PY_CMD=py
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PY_CMD% -m venv .venv
    if errorlevel 1 goto :install_failed
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :install_failed
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :install_failed
python -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed

echo.
echo Criando atalho...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\scripts\create-shortcut.ps1"
if errorlevel 1 echo Nao foi possivel criar o atalho. Use run.bat para iniciar.

echo.
echo Instalacao concluida. Abra pelo atalho app.bat.lnk ou por run.bat.
pause
popd
exit /b 0

:install_failed
echo.
echo Falha na instalacao das dependencias. Confira a mensagem acima e tente novamente.
pause
popd
exit /b 1
