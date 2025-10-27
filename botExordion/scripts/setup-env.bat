@echo off
set VENV_DIR=..\.venv
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale Python 3.8+ e tente novamente.
  pause
  exit /b 1
)

echo Criando virtualenv em %VENV_DIR% ...
python -m venv %VENV_DIR%
if not exist "%VENV_DIR%\Scripts\activate.bat" (
  echo Falha ao criar virtualenv.
  pause
  exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel
pip install -r ..\requirements.txt

echo Ambiente criado. Execute scripts\run.bat para iniciar a aplicacao.
pause