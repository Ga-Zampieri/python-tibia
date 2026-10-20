@echo off
setlocal
set SCRIPT_DIR=%~dp0
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
pushd "%SCRIPT_DIR%"

if exist ".venv\Scripts\python.exe" (
    call ".venv\Scripts\activate.bat"
) else (
    echo Virtualenv nao encontrado. Execute install.bat ou scripts\setup-env.bat primeiro.
    pause
    popd
    exit /b 1
)

echo Iniciando Exordion 7.4 Pro...
"%SCRIPT_DIR%\.venv\Scripts\python.exe" app.py --gui
set EXITCODE=%ERRORLEVEL%

echo.
echo Processo finalizado com codigo: %EXITCODE%
echo Pressione qualquer tecla para fechar...
pause >nul
popd
exit /b %EXITCODE%