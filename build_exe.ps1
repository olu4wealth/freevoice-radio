# Build Freevoice Radio as an onedir bundle and stage it into .\dist
#
# Usage:  .\build_exe.ps1
#
# The app is built onedir (not one-file) on purpose: a one-file exe must
# unpack itself into %TEMP% before it can start, which fails on machines
# with a restricted temp folder ("Could not create temporary directory!").
# An onedir bundle runs in place and needs no writable temp folder.

param(
    [switch]$KeepStage
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$dist = Join-Path $PSScriptRoot "dist"
$stage = Join-Path $PSScriptRoot "dist_new"
$bundle = Join-Path $stage "Freevoice Radio"
$targetExe = Join-Path $dist "Freevoice Radio.exe"
$targetInternal = Join-Path $dist "_internal"

if (Get-Process -Name "Freevoice Radio" -ErrorAction SilentlyContinue) {
    throw "Freevoice Radio is running. Close it (tray > Quit) before rebuilding."
}

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}

python -m PyInstaller --noconfirm --distpath $stage "Freevoice Radio.spec"
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath (Join-Path $bundle "Freevoice Radio.exe"))) {
    throw "Build output is missing: $bundle"
}

New-Item -ItemType Directory -Force -Path $dist | Out-Null

# Replace the previous app files but keep config.json, downloads/, ffmpeg.exe
# and ffprobe.exe in dist untouched.
if (Test-Path -LiteralPath $targetExe) {
    Remove-Item -LiteralPath $targetExe -Force
}
if (Test-Path -LiteralPath $targetInternal) {
    Remove-Item -LiteralPath $targetInternal -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $bundle "Freevoice Radio.exe") -Destination $targetExe
Copy-Item -LiteralPath (Join-Path $bundle "_internal") -Destination $targetInternal -Recurse

if (-not $KeepStage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $dist "ffmpeg.exe"))) {
    Write-Warning "ffmpeg.exe is not in dist. YouTube downloads need it next to the exe (or on PATH)."
}

Write-Host ""
Write-Host "Built: $targetExe"
Write-Host "Keep 'Freevoice Radio.exe' and '_internal' together in dist."
