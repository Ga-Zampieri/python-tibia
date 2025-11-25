@echo off
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale Python 3.8+ e tente novamente.
  pause
  exit /b 1
)

echo Instalando dependencias.
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo Dependencias instaladas. 
echo Execute script build.bat para buildar o projeto.
pause