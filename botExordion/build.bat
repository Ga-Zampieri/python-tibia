@echo off
echo Compilando BotExordion...

REM Remove builds anteriores
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM Compila diretamente
pyinstaller --onefile --windowed --name="BotExordion" --clean --hidden-import=status --hidden-import=action_manager --hidden-import=fishing --hidden-import=macro_rune --hidden-import=overlay --hidden-import=window_handler src/app.py --dist .

if %errorlevel% == 0 (
    echo.
    echo SUCCESSO! Executavel criado em: BotExordion.exe
    echo.
    echo Para abrir, execute: BotExordion.exe
) else (
    echo.
    echo ERRO na compilacao!
)

pause