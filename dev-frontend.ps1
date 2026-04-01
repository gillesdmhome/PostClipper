# Refreshes PATH (so Node works in terminals opened before Node was installed), then runs Vite.
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
Set-Location $PSScriptRoot\frontend
npm run dev
