# Prints suggested FFMPEG_PATH / FFPROBE_PATH lines for backend/.env (Windows).
# Run from PowerShell:  pwsh -File scripts\print-ffmpeg-paths.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$candidates = @()
$local = $env:LOCALAPPDATA
if ($local) {
    $link = Join-Path $local "Microsoft\WinGet\Links\ffmpeg.exe"
    if (Test-Path -LiteralPath $link) { $candidates += (Resolve-Path $link) }
    $pkgs = Join-Path $local "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $pkgs) {
        Get-ChildItem -LiteralPath $pkgs -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Name -match "FFmpeg") {
                $ff = Get-ChildItem -LiteralPath $_.FullName -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue |
                    Select-Object -First 1
                if ($ff) { $candidates += $ff.FullName }
            }
        }
    }
}
$pf = ${env:ProgramFiles}
if ($pf) {
    $p = Join-Path $pf "ffmpeg\bin\ffmpeg.exe"
    if (Test-Path -LiteralPath $p) { $candidates += (Resolve-Path $p).Path }
}
if ($env:USERPROFILE) {
    $p = Join-Path $env:USERPROFILE "scoop\apps\ffmpeg\current\bin\ffmpeg.exe"
    if (Test-Path -LiteralPath $p) { $candidates += (Resolve-Path $p).Path }
}
$choco = if ($env:ChocolateyInstall) { $env:ChocolateyInstall } else { "C:\ProgramData\chocolatey" }
$p = Join-Path $choco "bin\ffmpeg.exe"
if (Test-Path -LiteralPath $p) { $candidates += (Resolve-Path $p).Path }

$uniq = $candidates | Select-Object -Unique
if (-not $uniq) {
    Write-Host "No ffmpeg.exe found. Install with: winget install Gyan.FFmpeg"
    exit 1
}

$first = $uniq | Select-Object -First 1
$dir = Split-Path -Parent $first
$probe = Join-Path $dir "ffprobe.exe"
if (-not (Test-Path -LiteralPath $probe)) {
    Write-Host "Found ffmpeg but not ffprobe next to it: $first"
    exit 1
}

Write-Host "# Paste into backend\.env:"
Write-Host "FFMPEG_PATH=$first"
Write-Host "FFPROBE_PATH=$probe"
