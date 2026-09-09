# scripts/build.ps1 — full release build. Run from repo root.
$ErrorActionPreference = "Stop"
Push-Location dashboard
npm ci
npm run build
Pop-Location
python -m PyInstaller sparks_exe.spec --noconfirm --clean
if ($env:INNO_SETUP_PATH) {
    & "$env:INNO_SETUP_PATH\ISCC.exe" installer.iss
} else {
    Write-Warning "INNO_SETUP_PATH not set - skipping installer (run ISCC on installer.iss)"
}
