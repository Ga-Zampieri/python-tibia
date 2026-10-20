@echo off
setlocal
set VENV_DIR=..\.venv
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.12+ nao encontrado. Instale uma versao compativel e tente novamente.
    pause
    exit /b 1
  )
  set PY_CMD=python
) else (
  set PY_CMD=py
)

pushd "%~dp0\.."
echo Criando virtualenv em %VENV_DIR% ...
%PY_CMD% -m venv %VENV_DIR%
if not exist "%VENV_DIR%\Scripts\activate.bat" (
  echo Falha ao criar virtualenv.
  pause
  exit /b 1
)

call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo.
echo Ambiente criado com sucesso. Execute run.bat para testar a inicializacao.
pause
popd