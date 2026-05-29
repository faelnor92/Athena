# =========================================================================
# NATIVE WINDOWS POWERSHELL INSTALLER - JARVIS v2
# =========================================================================

# Clear console for neat rendering
Clear-Host

# Cyber-Neon Colors & Header
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
Write-Host "        CLI & WINDOWS DESKTOP DEPLOYMENT ENGINE" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "📦 Système détecté : Windows" -ForegroundColor $Magenta
Write-Host ""

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Get-Location }

# -------------------------------------------------------------------------
# ÉTAPE 1 : Dépendances Système (Python)
# -------------------------------------------------------------------------
Write-Host "🔄 Étape 1 : Vérification des dépendances système..." -ForegroundColor $Yellow

$PythonCheck = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCheck) {
    Write-Host "❌ Erreur : python est requis mais introuvable dans votre PATH." -ForegroundColor $Red
    Write-Host "Veuillez installer Python depuis le Microsoft Store ou https://www.python.org et cochez 'Add Python to PATH'." -ForegroundColor $Yellow
    Exit 1
}

$PythonVersion = python --version
Write-Host "✔ Python est disponible : $PythonVersion" -ForegroundColor $Green

# -------------------------------------------------------------------------
# ÉTAPE 2 : Environnement Virtuel Python (.venv)
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 2 : Configuration de l'environnement virtuel Python (.venv)..." -ForegroundColor $Yellow

$VenvDir = Join-Path $ScriptDir ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Création du dossier de l'environnement virtuel (.venv)..."
    python -m venv .venv
    if (-not $?) {
        Write-Host "❌ Erreur lors de la création de .venv." -ForegroundColor $Red
        Exit 1
    }
    Write-Host "✔ Environnement virtuel créé avec succès !" -ForegroundColor $Green
} else {
    Write-Host "✔ Environnement virtuel (.venv) déjà présent." -ForegroundColor $Green
}

# -------------------------------------------------------------------------
# ÉTAPE 3 : Dépendances Python
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 3 : Installation des dépendances Python (requirements.txt)..." -ForegroundColor $Yellow

$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "Mise à niveau de pip..."
& $PythonExe -m pip install --upgrade pip 2>$null

Write-Host "Installation des paquets requis..."
$RequirementsPath = Join-Path $ScriptDir "requirements.txt"
& $PipExe install -r $RequirementsPath
if (-not $?) {
    Write-Host "❌ Erreur lors de l'installation des dépendances." -ForegroundColor $Red
    Exit 1
}
Write-Host "✔ Toutes les dépendances Python ont été installées avec succès !" -ForegroundColor $Green

# -------------------------------------------------------------------------
# ÉTAPE 4 : Fichier de configuration .env
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 4 : Configuration des variables d'environnement (.env)..." -ForegroundColor $Yellow

$EnvFile = Join-Path $ScriptDir ".env"
$EnvExample = Join-Path $ScriptDir ".env.example"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Création du fichier .env à partir de .env.example..."
    Copy-Item $EnvExample $EnvFile
    Write-Host "✔ Fichier .env créé !" -ForegroundColor $Green
} else {
    Write-Host "✔ Le fichier de configuration .env existe déjà (non modifié)." -ForegroundColor $Green
}

# -------------------------------------------------------------------------
# ÉTAPE 5 : Génération des scripts de lancement rapide Windows
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 5 : Génération des scripts de lancement rapide Windows..." -ForegroundColor $Yellow

# Création du fichier run.bat (pour lancer facilement en local)
$RunBatPath = Join-Path $ScriptDir "run.bat"
$BatContent = @"
@echo off
title Jarvis Swarm Server v2
cd /d "%~dp0"
echo 🚀 Demarrage du serveur d'orchestration Jarvis v2...
echo 👉 Connectez-vous sur votre navigateur a : http://localhost:8000/
start http://localhost:8000/
.venv\Scripts\python.exe server.py
pause
"@
Set-Content -Path $RunBatPath -Value $BatContent
Write-Host "✔ Script de lancement rapide run.bat généré !" -ForegroundColor $Green

# Création du lanceur silencieux en VBS (évite de garder une invite CMD ouverte !)
$LaunchVbsPath = Join-Path $ScriptDir "launch.vbs"
$VbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "run.bat", 0, false
"@
Set-Content -Path $LaunchVbsPath -Value $VbsContent
Write-Host "✔ VBS Launcher d'arrière-plan silencieux généré !" -ForegroundColor $Green

# -------------------------------------------------------------------------
# ÉTAPE 6 : Raccourci Desktop Windows (.lnk)
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 6 : Création du raccourci d'application sur le Bureau..." -ForegroundColor $Yellow

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [System.Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $DesktopPath "Jarvis.lnk"
    
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "cmd.exe"
    $Shortcut.Arguments = "/c start /min """" `"$RunBatPath`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "Bureau Virtuel Multi-Agent & Cockpit Jarvis"
    # Utilisation d'une jolie icône système Windows par défaut (globe terrestre ou engrenage)
    $Shortcut.IconLocation = "shell32.dll, 13" # Index 13 = Icône réseau/globe dans shell32.dll
    $Shortcut.Save()
    
    Write-Host "✔ Raccourci d'application 'Jarvis' créé sur votre Bureau !" -ForegroundColor $Green
    
    # Intégration Service d'Arrière-plan permanent sur Windows (via Task Scheduler)
    Write-Host ""
    Write-Host "💡 Option de Lancement automatique au démarrage (Service Windows) :" -ForegroundColor $Cyan
    Write-Host "   Pour que Jarvis s'exécute en arrière-plan silencieux dès le démarrage de votre ordinateur,"
    Write-Host "   exécutez cette commande dans un terminal PowerShell Administrateur :" -ForegroundColor $Yellow
    Write-Host "   👉 Register-ScheduledTask -TaskName 'JarvisSwarmService' -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Action (New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '`\"$LaunchVbsPath`\"') -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)" -ForegroundColor $Magenta
} catch {
    Write-Host "⚠ Impossible de générer le raccourci sur le Bureau automatiquement." -ForegroundColor $Yellow
}

# -------------------------------------------------------------------------
# ÉTAPE 7 : Découverte Ollama
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 7 : Détection de l'intégration locale Ollama..." -ForegroundColor $Yellow

$OllamaCheck = Get-Command ollama -ErrorAction SilentlyContinue
if ($OllamaCheck) {
    Write-Host "✔ Ollama est installé localement sur Windows !" -ForegroundColor $Green
    Write-Host "Modèles installés :"
    $Models = & ollama list
    $Models | Select-Object -Skip 1 | ForEach-Object {
        $Parts = $_ -split "\s+"
        if ($Parts[0]) {
            Write-Host " - $($Parts[0])"
        }
    }
    
    $HasModel = $Models -match "llama|qwen|mistral|phi"
    if (-not $HasModel) {
        Write-Host "⚠ Aucun modèle adapté aux agents n'a été détecté dans Ollama." -ForegroundColor $Yellow
        Write-Host "   Il est fortement recommandé de télécharger un modèle compact (ex: Qwen 2.5 Coder 1.5B)." -ForegroundColor $Yellow
        Write-Host "   Pour le faire automatiquement, tapez : ollama pull qwen2.5-coder:1.5b" -ForegroundColor $Cyan
    }
} else {
    Write-Host "⚠ Note : Ollama n'est pas détecté sur cette machine." -ForegroundColor $Yellow
    Write-Host "   Si vous souhaitez faire tourner vos agents localement et gratuitement :" -ForegroundColor $Yellow
    Write-Host "   Téléchargez Ollama pour Windows sur : https://ollama.com" -ForegroundColor $Cyan
}

# -------------------------------------------------------------------------
# FIN D'INSTALLATION
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host " 🎉 INSTALLATION WINDOWS TERMINÉE AVEC SUCCÈS !" -ForegroundColor $Green -BackgroundColor Black
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "Pour démarrer votre bureau virtuel multi-agent, vous pouvez :"
Write-Host " 1. Double-cliquer sur le magnifique raccourci 'Jarvis' sur votre Bureau."
Write-Host " 2. Ou double-cliquer directement sur 'run.bat' dans ce dossier."
Write-Host ""
Write-Host "Ouvrez ensuite votre navigateur sur : http://localhost:8000/" -ForegroundColor $Cyan
Write-Host ""
