# PreCutter icin masaustune kisayol olusturur.
# Kullanim:  powershell -ExecutionPolicy Bypass -File scripts\create-shortcut.ps1
# veya tek tiklamayla:  ..\create-shortcut.bat
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }

$target = Join-Path $root "start.bat"
if (-not (Test-Path $target)) {
    throw "start.bat bulunamadi: $target"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "PreCutter.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,137"
$shortcut.Description = "PreCutter - yerel sunucuyu baslatir"
$shortcut.Save()

Write-Host "[PreCutter] Kisayol olusturuldu: $link"
