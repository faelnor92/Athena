# =========================================================================
# NATIVE WINDOWS POWERSHELL UPDATER - JARVIS v2
# =========================================================================

Clear-Host
$Cyan = "Cyan"
$Magenta = "Magenta"
$Green = "Green"
$Yellow = "Yellow"
$Red = "Red"

Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "        __                 _                 ___ " -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "     / /  ___ _ ______  __(_)__  __  __     |_  |" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "  _ / /  / _ \`/ __/ _ \/ / (_&-<  | |/ /    / __/ " -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "  \___/   \_,_/_/  /_//_/_/ /___/  |___/    /____/ " -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "                                                 " -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "        CLI & WINDOWS DESKTOP UPDATER ENGINE" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black

Write-Host "🔄 Recherche de mises à jour (git pull)..." -ForegroundColor $Yellow
git pull origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erreur lors du git pull. Vérifiez votre connexion ou vos modifications locales." -ForegroundColor $Red
    Exit 1
}

$Version = Get-Content -Path "VERSION" -ErrorAction SilentlyContinue
if ($Version) {
    Write-Host "✔ Version locale actuelle : v$Version" -ForegroundColor $Green
}

Write-Host "🔄 Installation des éventuelles nouvelles dépendances..." -ForegroundColor $Yellow

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . ".venv\Scripts\Activate.ps1"
} elseif (Test-Path "venv\Scripts\Activate.ps1") {
    . "venv\Scripts\Activate.ps1"
} else {
    Write-Host "⚠️ Environnement virtuel introuvable. Les dépendances seront installées globalement." -ForegroundColor $Yellow
}

python -m pip install -r requirements.txt --quiet

Write-Host "🚀 Redémarrage du serveur Jarvis..." -ForegroundColor $Cyan
$JarvisCli = Get-Command jarvis -ErrorAction SilentlyContinue
if ($JarvisCli) {
    jarvis restart
} else {
    Write-Host "⚠️ Relance manuelle du serveur..." -ForegroundColor $Yellow
    Stop-Process -Name "python" -ErrorAction SilentlyContinue
    Start-Process -NoNewWindow -FilePath "python" -ArgumentList "server.py" -RedirectStandardOutput "server.log" -RedirectStandardError "server.log"
    Write-Host "✔ Serveur relancé en arrière-plan." -ForegroundColor $Green
}

Write-Host "✔ Mise à jour terminée !" -ForegroundColor $Green
