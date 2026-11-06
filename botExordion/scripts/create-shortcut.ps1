# Gera app.bat.lnk com os caminhos desta maquina.
# Um .lnk guarda caminho absoluto, por isso ele e gerado aqui e nao vai para o git.

$ErrorActionPreference = 'Stop'

$projectDir = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $projectDir '.venv\Scripts\pythonw.exe'
$shortcutPath = Join-Path $projectDir 'app.bat.lnk'

if (-not (Test-Path -LiteralPath $pythonw)) {
    Write-Host "pythonw nao encontrado em $pythonw. Execute install.bat primeiro."
    exit 1
}

if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
}

$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = 'app.py --gui'
$shortcut.WorkingDirectory = $projectDir
$shortcut.Save()

# "Executar como administrador", exigido pelo BlockInput, nao existe no WScript.Shell.
# E o bit SLDF_RUNAS_USER (0x2000) de LinkFlags, que comeca no offset 0x14 do .lnk.
$bytes = [System.IO.File]::ReadAllBytes($shortcutPath)
$bytes[0x15] = $bytes[0x15] -bor 0x20
[System.IO.File]::WriteAllBytes($shortcutPath, $bytes)

Write-Host "Atalho criado: $shortcutPath"
