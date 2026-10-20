@echo off
setlocal
pushd %~dp0\..
if exist ".venv\Scripts\python.exe" (
    call ".venv\Scripts\activate.bat"
) else (
    echo Virtualenv nao encontrado.
    pause
    exit /b 1
)
python -m pytest -q
if errorlevel 1 pause
popd
exit /b %ERRORLEVEL%
