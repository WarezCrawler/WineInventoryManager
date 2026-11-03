# Builds the program: dist\WineInventoryManager\WineInventoryManager.exe
# Run in PowerShell from anywhere:  .\build.ps1
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Installing the requirements failed" }
$env:Path = "$PSScriptRoot\.venv\Scripts;$env:Path"

# winedb/migrations holds the .sql files the program needs at run time
nicegui-pack --onedir --windowed --noconfirm --clean --name WineInventoryManager `
    --add-data "winedb/migrations;winedb/migrations" run_app.py
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

Write-Host "`nDone: dist\WineInventoryManager\WineInventoryManager.exe"
