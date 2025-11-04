@echo off
REM muda para o diretório do script e depois para a raiz do projeto (pai)
set SCRIPT_DIR=%~dp0
REM remove possível trailing backslash para formar caminhos consistentes
if "%SCRIPT_DIR:~-1%"=="\" set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%

REM supondo que o script esteja em c:\Git\python-tibia ou em c:\Git\python-tibia\botExordion
REM vamos definir PROJECT_ROOT como o pai do diretório atual do script
pushd "%SCRIPT_DIR%\.."

REM tenta ativar venv na raiz do projeto
if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
) else if exist "botExordion\.venv\Scripts\activate.bat" (
  call "botExordion\.venv\Scripts\activate.bat"
) else (
  echo Virtualenv nao encontrado. Execute scripts\setup_env.bat primeiro ou crie um .venv.
  pause
  popd
  exit /b 1
)

REM agora o cwd e' a raiz do projeto, executa o modulo como pacotes
python -m botExordion.app
set EXITCODE=%ERRORLEVEL%

REM mantem a janela aberta para ver possiveis erros
echo.
echo Processo finalizado com codigo: %EXITCODE%
pause

popd
exit /b %EXITCODE%