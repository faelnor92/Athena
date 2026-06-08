# =========================================================================
# NATIVE WINDOWS POWERSHELL INSTALLER - ATHENA v2
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

# Support de l'installation distante via iex (One-Liner)
if (-not (Test-Path "server.py")) {
    Write-Host "🔄 Installation distante détectée. Clonage du dépôt dans 'athena'..." -ForegroundColor $Yellow
    $GitCheck = Get-Command git -ErrorAction SilentlyContinue
    if (-not $GitCheck) {
        Write-Host "❌ Erreur : git est requis pour cloner le dépôt." -ForegroundColor $Red
        Exit 1
    }
    git clone https://github.com/faelnor92/athena.git athena
    if ($LASTEXITCODE -ne 0) { Exit 1 }
    Set-Location athena
    & .\install.ps1
    Exit 0
}

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
# ÉTAPE 1b : Navigateur headless + Docker (AthenaDesign : export PDF + sandbox)
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 1b : Navigateur headless + Docker (AthenaDesign)..." -ForegroundColor $Yellow
$Winget = Get-Command winget -ErrorAction SilentlyContinue
# Navigateur : Edge (Chromium) est presque toujours présent sous Windows.
$Edge = Test-Path "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe"
$Chrome = (Get-Command chrome -ErrorAction SilentlyContinue) -or (Test-Path "$env:ProgramFiles\Google\Chrome\Application\chrome.exe")
if ($Edge -or $Chrome) {
    Write-Host "✔ Navigateur headless détecté (Edge/Chrome)." -ForegroundColor $Green
} elseif ($Winget) {
    Write-Host "Installation de Google Chrome via winget..."
    winget install -e --id Google.Chrome --accept-source-agreements --accept-package-agreements 2>$null
} else {
    Write-Host "⚠ Aucun navigateur headless détecté — installe Chrome/Edge (export PDF AthenaDesign), ou définis CHROMIUM_BIN." -ForegroundColor $Yellow
}
# Docker Desktop.
$Docker = Get-Command docker -ErrorAction SilentlyContinue
if ($Docker) {
    Write-Host "✔ Docker détecté." -ForegroundColor $Green
} elseif ($Winget) {
    Write-Host "Installation de Docker Desktop via winget (redémarrage requis ensuite)..."
    winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements 2>$null
} else {
    Write-Host "⚠ Docker absent → exécution du code AthenaDesign en mode local NON isolé. Installe Docker Desktop : https://www.docker.com/products/docker-desktop/" -ForegroundColor $Yellow
}

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
# ÉTAPE 4b : Assistant interactif (composants optionnels + configuration .env)
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 4b : Choix des composants optionnels & configuration..." -ForegroundColor $Yellow
# Le python du venv installe les paquets optionnels dans le venv.
& $PythonExe (Join-Path $ScriptDir "setup_wizard.py")

# -------------------------------------------------------------------------
# ÉTAPE 5 : Génération des scripts de lancement rapide Windows
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "🔄 Étape 5 : Génération des scripts de lancement rapide Windows..." -ForegroundColor $Yellow

# Création du fichier run.bat (pour lancer facilement en local)
$RunBatPath = Join-Path $ScriptDir "run.bat"
$BatContent = @"
@echo off
title Athena Swarm Server v2
cd /d "%~dp0"
echo 🚀 Demarrage du serveur d'orchestration Athena v2...
echo 👉 Connectez-vous sur votre navigateur a : http://localhost:8000/
start http://localhost:8000/
.venv\Scripts\python.exe server.py
pause
"@
Set-Content -Path $RunBatPath -Value $BatContent
Write-Host "✔ Script de lancement rapide run.bat généré !" -ForegroundColor $Green

# Commande de contrôle 'athena.bat' (parité avec 'athena start' sous Linux/macOS)
$AthenaBatPath = Join-Path $ScriptDir "athena.bat"
$AthenaBat = @"
@echo off
cd /d "%~dp0"
if "%1"=="start" (
    echo Demarrage de Athena... ^| http://localhost:8000/
    start "" http://localhost:8000/
    start "" /min .venv\Scripts\python.exe server.py
    goto :eof
)
if "%1"=="stop" (
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq *server.py*" 2>nul
    echo Athena arrete.
    goto :eof
)
if "%1"=="cli" ( .venv\Scripts\python.exe main.py & goto :eof )
echo Usage: athena {start^|stop^|cli}
"@
Set-Content -Path $AthenaBatPath -Value $AthenaBat
Write-Host "✔ Commande 'athena.bat' créée (athena start / stop / cli)." -ForegroundColor $Green

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
    $ShortcutPath = Join-Path $DesktopPath "Athena.lnk"
    
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "cmd.exe"
    $Shortcut.Arguments = "/c start /min """" `"$RunBatPath`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description = "Bureau Virtuel Multi-Agent & Cockpit Athena"
    # Utilisation d'une jolie icône système Windows par défaut (globe terrestre ou engrenage)
    $Shortcut.IconLocation = "shell32.dll, 13" # Index 13 = Icône réseau/globe dans shell32.dll
    $Shortcut.Save()
    
    Write-Host "✔ Raccourci d'application 'Athena' créé sur votre Bureau !" -ForegroundColor $Green
    
    # Intégration Service d'Arrière-plan permanent sur Windows (via Task Scheduler)
    Write-Host ""
    Write-Host "💡 Option de Lancement automatique au démarrage (Service Windows) :" -ForegroundColor $Cyan
    Write-Host "   Pour que Athena s'exécute en arrière-plan silencieux dès le démarrage de votre ordinateur,"
    Write-Host "   exécutez cette commande dans un terminal PowerShell Administrateur :" -ForegroundColor $Yellow
    Write-Host "   👉 Register-ScheduledTask -TaskName 'AthenaSwarmService' -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Action (New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '`\"$LaunchVbsPath`\"') -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)" -ForegroundColor $Magenta
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
    
    $HasModel = $Models -match "qwen2.5:0.5b"
    if (-not $HasModel) {
        Write-Host "⚠ Le modèle de maintenance (qwen2.5:0.5b) n'est pas détecté." -ForegroundColor $Yellow
        $InstallModel = Read-Host "Voulez-vous le télécharger pour activer l'Agent de Nuit Gratuit ? (o/n)"
        if ($InstallModel -match "^[OoYy]") {
            Write-Host "Téléchargement de qwen2.5:0.5b..." -ForegroundColor $Cyan
            & ollama pull qwen2.5:0.5b
        }
    }
} else {
    Write-Host "⚠ Note : Ollama n'est pas détecté sur cette machine." -ForegroundColor $Yellow
    Write-Host "   Ollama est recommandé pour faire tourner l'Agent de Maintenance de Nuit gratuitement." -ForegroundColor $Yellow
    
    $WingetCheck = Get-Command winget -ErrorAction SilentlyContinue
    if ($WingetCheck) {
        $InstallOllama = Read-Host "Voulez-vous installer Ollama maintenant via winget ? (o/n)"
        if ($InstallOllama -match "^[OoYy]") {
            Write-Host "Installation d'Ollama..." -ForegroundColor $Cyan
            & winget install Ollama
            Write-Host "⚠ Veuillez redémarrer ce script d'installation après l'installation d'Ollama." -ForegroundColor $Yellow
        }
    } else {
        Write-Host "   Téléchargez Ollama pour Windows sur : https://ollama.com" -ForegroundColor $Cyan
    }
}

# -------------------------------------------------------------------------
# FIN D'INSTALLATION
# -------------------------------------------------------------------------
Write-Host ""
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host " 🎉 INSTALLATION WINDOWS TERMINÉE AVEC SUCCÈS !" -ForegroundColor $Green -BackgroundColor Black
Write-Host "=========================================================================" -ForegroundColor $Cyan -BackgroundColor Black
Write-Host "Pour démarrer votre bureau virtuel multi-agent, vous pouvez :"
Write-Host " 1. Double-cliquer sur le magnifique raccourci 'Athena' sur votre Bureau."
Write-Host " 2. Ou double-cliquer directement sur 'run.bat' dans ce dossier."
Write-Host ""
Write-Host "Ouvrez ensuite votre navigateur sur : http://localhost:8000/" -ForegroundColor $Cyan
Write-Host ""
