# Builds the program: dist\WineInventoryManager\WineInventoryManager.exe
# Run in PowerShell from anywhere:  .\build.ps1
#
# The program keeps its database (data\) and settings.json next to the .exe, inside the build folder.
# PyInstaller deletes that folder at each build, so this script moves both out first and puts them back
# afterwards, also when the build fails. It refuses to build while the program runs, because the running
# program locks its files and would create a new, empty database during the build.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$output = Join-Path $PSScriptRoot "dist\WineInventoryManager"
$exe = Join-Path $output "WineInventoryManager.exe"
$keep = @("data", "settings.json")
$safe = Join-Path $PSScriptRoot ("build-keep-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

$running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($output, [StringComparison]::OrdinalIgnoreCase) }
if ($running) { throw "The program is running ($($running[0].Path)). Close it, then build again." }

# A folder left by an interrupted build holds the user's data: stop and let the user restore it.
$left = Get-ChildItem -Path $PSScriptRoot -Directory -Filter "build-keep-*" -ErrorAction SilentlyContinue
if ($left) { throw "Found $($left[0].FullName) from an earlier build. Move its content back into $output, delete it, then build again." }

if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "Installing the requirements failed" }
$env:Path = "$PSScriptRoot\.venv\Scripts;$env:Path"

$moved = @()
foreach ($name in $keep) {
    $path = Join-Path $output $name
    if (Test-Path $path) {
        if (-not (Test-Path $safe)) { New-Item -ItemType Directory -Path $safe | Out-Null }
        Move-Item -Path $path -Destination $safe
        $moved += $name
        Write-Host "Kept aside during the build: $path"
    }
}

$started = Get-Date
$buildExit = 1
try {
    # winedb/migrations holds the .sql files the program needs at run time
    nicegui-pack --onedir --windowed --noconfirm --clean --name WineInventoryManager `
        --add-data "winedb/migrations;winedb/migrations" run_app.py
    $buildExit = $LASTEXITCODE
}
finally {
    if ($moved.Count -gt 0) {
        if (-not (Test-Path $output)) { New-Item -ItemType Directory -Path $output | Out-Null }
        $blocked = @($moved | Where-Object { Test-Path (Join-Path $output $_) })
        if ($blocked.Count -gt 0) {
            # Something created these during the build. Never overwrite: the kept copy stays safe.
            throw "Not put back, because $($blocked -join ' and ') appeared in $output during the build. " +
                  "Your data is in $safe. Compare, then move it back by hand."
        }
        foreach ($name in $moved) {
            Move-Item -Path (Join-Path $safe $name) -Destination $output
            Write-Host "Put back: $(Join-Path $output $name)"
        }
        Remove-Item -Path $safe
    }
}
if ($buildExit -ne 0) { throw "Build failed (exit code $buildExit)" }
if (-not (Test-Path $exe) -or (Get-Item $exe).LastWriteTime -lt $started) {
    throw "Build failed: $exe was not written by this build"
}

Write-Host "`nDone: $exe"
