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
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo.
echo Instalacao concluida. Execute run.bat para iniciar.
pause
popd
