# 📖 Athena-Benutzerhandbuch

🌍 **Sprachen**: [Français](USER_GUIDE.md) · [English](USER_GUIDE.en.md) · [Español](USER_GUIDE.es.md) · [Italiano](USER_GUIDE.it.md) · Deutsch · [中文](USER_GUIDE.zh.md) · [日本語](USER_GUIDE.ja.md)

Willkommen! Wenn Sie dieses Handbuch lesen, haben Sie soeben **Athena** installiert, Ihren Dirigenten der Multi-Agenten-Künstlichen Intelligenz. Dieses Dokument soll Ihnen helfen, sich mit dem Werkzeug vertraut zu machen.

---

## 1. 🌟 Erster Start und Anmeldung

Sobald Athena auf Ihrem Rechner installiert und gestartet ist, ist die grafische Oberfläche (UI) nur über Ihren Webbrowser zugänglich.

1. Öffnen Sie Ihren Browser und gehen Sie zur Adresse: **`http://localhost:8000`** (oder zur IP-Adresse Ihres Servers, wenn Sie ihn auf einem anderen Rechner installiert haben).
2. Beim allerersten Start werden Sie aufgefordert, ein Konto mit einer E-Mail-Adresse und einem Passwort zu erstellen.
3. Nach der Anmeldung gelangen Sie auf den **virtuellen Desktop**.

---

## 2. 💬 Mit der KI chatten

Es gibt **zwei Möglichkeiten**, mit Athena zu interagieren: die Weboberfläche und das Terminal (CLI).

### A. Über die Weboberfläche (UI)
Das ist die anschaulichste und einfachste Methode.
- **Die 3D-Ansicht**: Auf der Hauptseite sehen Sie eine visuelle Darstellung von Athena und ihren „Agenten" (der Programmierer, der Rechercheur usw.). Wenn Athena nachdenkt oder eine Aufgabe delegiert, sehen Sie leuchtende Animationen, die Ihnen anzeigen, welcher Agent gerade arbeitet.
- **Der automatische Orchestrator**: Schreiben Sie in der Chatleiste unten einfach Ihre Anfrage. In der Weboberfläche **sprechen Sie immer mit dem Orchestrator**. Er ist intelligent genug, um Ihre Anfrage zu verstehen und sie automatisch dem richtigen Agenten zuzuweisen (er übergibt z. B. an den Programmierer-Agenten, wenn Sie ein Skript anfordern).
- **Der Datei-Explorer (Workspaces)**: Links befindet sich ein Bereich mit Ihren Dateien. Sie können Dokumente (PDF, Markdown, Quellcode) per Drag & Drop ablegen, damit die KI sie analysieren kann.
- **Der integrierte Editor (Mini-IDE)**: Klicken Sie auf eine Datei, um sie direkt im Browser zu **bearbeiten** — mehrere geöffnete Dateien als **Tabs**, Syntaxhervorhebung, Autovervollständigung (Strg+Leertaste) und **Speichern** mit **Strg+S** (💾). Ein *Leser* eines geteilten Projekts bleibt schreibgeschützt. Sie können den **Explorer verkleinern oder einklappen** (mittlerer Griff oder Schaltfläche „◀ Reduzieren"), um den Editor zu vergrößern, und wenn der **Agent eine geöffnete Datei ändert**, aktualisiert sich Ihre Ansicht **live** (zusammen mit der Präsenz der anderen Leser).
- **Die Programmierer-Konsole (interaktives Terminal)**: ein echtes Terminal, in dem Sie zum Entwickeln mit dem **Programmierer**-Agenten sprechen. Besonderheiten:
  - **Unabhängiges Zielprojekt**: Mit einer Auswahl können Sie an einem **anderen** Projekt als dem des Chats/der Sprache programmieren (Ihre Sprachbefehle und die Hausautomation laufen weiter in ihrem Kontext).
  - **Projektbaum** rechts (der Chat ist dort ausgeblendet, weil unnötig): Er **aktualisiert sich automatisch** — Sie sehen die vom Agenten erstellten Dateien erscheinen.
  - **IDE in separatem Fenster**: Die Schaltfläche **„⧉ IDE"** (oder ein Klick auf eine Datei im Baum) öffnet den Editor in einem **echten, verschiebbaren Fenster** (ideal auf einem 2. Bildschirm), mit Tabs, Hervorhebung, Autovervollständigung und **Strg+S**. *(Beim ersten Mal Pop-ups für die Website erlauben.)*
  - Befehle mit dem Präfix `$` oder `!` werden direkt als Shell ausgeführt; andernfalls bearbeitet der Programmierer-Agent Ihre Anfrage und **schreibt die Dateien in das Projekt** (Docker-Sandbox auf dem Projekt eingebunden).

### C. Projekte & Zusammenarbeit (geteilte Workspaces)
Ein **Projekt** ist ein dedizierter Arbeitsordner. Wenn Sie ein Projekt in der Projektleiste (oben im Explorer) auswählen, ist **alles, was die KI tut (Lesen, Code-Bearbeitung, Terminal, Git), auf diesen Ordner beschränkt** — praktisch, um ein Code-Repository oder einen Kundenordner zu isolieren.
- **Projekt erstellen / wechseln**: Schaltfläche `＋ Projekt`, dann Auswahl aus der Liste. Jeder Benutzer hat seine eigenen Projekte, für andere unsichtbar.
- **Ein Projekt teilen** (Schaltfläche `👥 Teilen`): Als **Eigentümer** laden Sie andere Benutzer ein und wählen ihre Rolle:
  - **Leser**: kann das Projekt einsehen und mit der KI darüber chatten, aber **NICHTS ändern** — auch nicht, indem er den Agenten darum bittet (die Sperre wird serverseitig bei jedem Schreibwerkzeug durchgesetzt: Dateibearbeitung, Git, Bash, Python). Nicht umgehbar.
  - **Editor**: kann Dateien ändern, Code ausführen, committen.
- Nur der Eigentümer kann teilen, Rollen ändern oder das Projekt löschen.

### B. Über die interaktive Konsole (CLI)
Wenn Sie das Terminal der grafischen Oberfläche vorziehen, können Sie eine reine Textunterhaltung starten.
Gehen Sie in den Athena-Ordner und geben Sie ein:
`python3 athena_cli.py`

> [!TIP]
> **Einen bestimmten Agenten erzwingen (nur Konsole)**: Anders als in der Weboberfläche, wo der Orchestrator alles verwaltet, können Sie in der Konsole den Dirigenten umgehen und direkt mit einem Spezialisten-Agenten sprechen. Verwenden Sie dazu:
> `python3 athena_cli.py --agent Codeur`

---

## 3. 🛠️ Was kann Athena tun? (Die Superkräfte)

Athena ist kein einfaches „ChatGPT". Es ist ein Framework von **autonomen Agenten der künstlichen Intelligenz**, die Dutzende von Werkzeugen („Skills") integrieren, die auf Ihrem Rechner und im Web agieren können.

### 💻 Agentischer Code (Software Engineering)
Das ist das Herz des Systems. Athena kann einen Systemadministrator oder einen Entwickler ersetzen:
- **Python- & Bash-Ausführung (Sandbox)**: Die KI schreibt Code und führt ihn autonom in einer sicheren Docker-Sandbox aus.
- **Skill-Erstellung im Handumdrehen**: Eine einzigartige Funktion — die KI kann neue „Werkzeuge" programmieren, um sich selbst zu verbessern, und sie dauerhaft in ihrem Basisquellcode speichern!
- **SSH-Administration**: Die KI kann sich per SSH mit Ihren anderen Remote-Servern verbinden, um Wartung durchzuführen.
- **Computer Use (RPA 2.0)**: Die KI kann einen echten, versteckten Webbrowser öffnen, auf Schaltflächen klicken, Formulare ausfüllen und Websites scrapen.
- **Git- & Code-Navigation**: Die KI kann Ihre Git-Repositories lesen, Ihren vorhandenen Quellcode verstehen und ihn live bearbeiten.
- **Autonome Wartung**: Ein nächtlicher Agent kann den Quellcode automatisch prüfen und reparieren.

### 🎨 AthenaDesign Studio (KI-Design)
Ein integriertes Design-Studio (Tab **🎨 Design**). Beschreiben Sie, was Sie erstellen möchten, Athena generiert es und **zeigt es live an**:
- **Typen**: Webseiten (HTML/CSS/JS), interaktive **React-Apps**, **Mermaid-Diagramme** und **Python**-Skripte (**PowerPoint**-Präsentationen, Diagramme). **Startvorlagen** (Landing, Pitch Deck, Dashboard…) füllen einen Prompt vor.
- **Ihre Marke (Design System)**: Klappen Sie das Panel „Design System" auf, um Ihre Farben/Schrift anzugeben — von Hand, durch Einfügen von CSS oder über **„🌐 Von einer URL"** (Athena extrahiert die Marke von einer Website).
- **Referenzen**: Hängen Sie ein Bild/Dokument (📎) oder eine Webseite (🔗) als Inspiration an.
- **Verfeinern**: Annotieren Sie die Vorschau, passen Sie live an (Schieberegler für Farbe/Rundung/Schrift), durchblättern Sie die Versionen. Wenn ein Python-Skript fehlschlägt, **korrigiert sich Athena selbst**.
- **Teilen / Exportieren**: Schaltfläche **Teilen** (schreibgeschützter Link), **PDF-Export** und Download der `.pptx`.
- *Tipp*: Ein Athena-Projekt vereint **Code und Design** — Sie verwalten beides am selben Ort.

### 🔌 Plugins (einschließlich Claude Code)
Aktivieren Sie unter **Einstellungen > 🔌 Plugins** Erweiterungen. Das **Claude-Code-Plugin** ruft den Programmieragenten **Claude Code** auf (das `claude`-CLI muss installiert und angemeldet sein): Nach der Aktivierung kann Ihr **Programmierer** ihm komplexe Programmieraufgaben delegieren, direkt im aktiven Projekt. *(Verbraucht Ihr Claude-Abonnement/Ihren Schlüssel.)*

### 🏠 Hausautomation, Kontext & Alltag
- **Native Hausautomation (Home Assistant)**: Die KI verbindet sich direkt mit Ihrer Hausautomation. Bitten Sie sie um *„Schalte das Licht im Wohnzimmer aus"* oder *„Schließe die Rollläden"*, und sie tut es sofort.
- **MCP-Erweiterungen (Fortgeschritten)**: Athena unterstützt das MCP-Protokoll. Damit kann sie komplexe Plugins anbinden (wie einen tiefen Zugriff auf die Home-Assistant-Datenbank zum Erstellen von Automationen oder jeden anderen vorhandenen MCP-Server).
- **Räumliches Bewusstsein**: Die KI kann wissen, in welchem Raum Sie sich befinden (wenn Sie Sensoren haben), um ihre Aktionen anzupassen (z. B. schaltet *„Schalte das Licht ein"* das im Raum ein, in dem Sie sich befinden).
- **Wetter & Zeit**: Mehrtägige Wettervorhersagen und Zeitsynchronisation.
- **Listen & Einkäufe**: Bitten Sie sie, Milch auf Ihre Einkaufsliste zu setzen oder eine To-do-Liste zu erstellen.

### 📅 Produktivität & Kommunikation
- **Kalender & Planung**: Synchronisation mit Ihren Kalendern (iCal, CalDAV) zum Lesen und Erstellen von Ereignissen.
- **Besprechungszusammenfassungen**: Fähigkeit, Besprechungen oder Audiodateien zu transkribieren und zusammenzufassen.
- **Benachrichtigungen**: Athena kann Ihnen aus eigener Initiative Nachrichten über Telegram, Discord oder Slack senden.
- **Mediengenerierung**: Bilderstellung (über die Fal/Replicate-API) und Dateimanipulation (PDF, Dokumente).
- **Workflows (n8n)**: Auslösen komplexer Szenarien über n8n-Webhooks.

### ⏰ Proaktive Routinen
Athena wartet nicht darauf, dass Sie mit ihr sprechen. Bitten Sie sie: *„Gib mir jeden Morgen um 7:30 eine Zusammenfassung meines Tages"*. Sie wacht von selbst auf, analysiert Ihren Kalender, das Wetter, den Zustand Ihres Hauses und kann sogar die Kaffeemaschine starten!

---

## 4. ⚙️ Die Einstellungen der Oberfläche verstehen

Durch Klicken auf das Zahnrad-Symbol (⚙️) in der Seitenleiste gelangen Sie zu den Einstellungen Ihres Profils. **Jede Einstellung ist streng auf Ihren Benutzer isoliert.**

### Tab „🔑 API-Schlüssel" (Mein Modell & LLM-Schlüssel)
- **KI-Anbieter (z. B. OpenAI, Anthropic, Ollama)** und **Modellname**: Wählen Sie die Version der KI, die Sie verwenden möchten.
- **Persönlicher API-Schlüssel**: Wenn dieses Feld ausgefüllt ist, verwendet Athena IHREN Schlüssel zum Arbeiten, und Ihnen wird über Ihr eigenes Entwicklerkonto abgerechnet. Damit lässt sich das Standardmodell des Servers überschreiben.
- **📊 Meine Nutzung**: Direkt unter Ihren Schlüsseln eine Zusammenfassung Ihres persönlichen Verbrauchs (Anfragen, Tokens, Kosten €) für heute, die letzten 30 Tage und insgesamt — um Ihre Ausgaben auf einen Blick zu verfolgen. (Ein Administrator sieht hingegen den Verbrauch aller Konten.)

### 🔐 Mein Konto absichern (Tab „Benutzer")
- **Mein Passwort**: Ändern Sie es, wann Sie wollen (mind. 8 Zeichen). Aus Sicherheitsgründen **werden Ihre anderen Sitzungen abgemeldet**, wenn Sie Ihr Passwort ändern.
- **Zwei-Faktor-Authentifizierung (2FA)**: Klicken Sie auf **2FA aktivieren**, fügen Sie das Konto Ihrer Authentifizierungs-App hinzu (Google Authenticator, Authy, FreeOTP…), indem Sie das angezeigte Geheimnis scannen/eingeben, und geben Sie dann einen Code zur Bestätigung ein. Bei jeder Anmeldung wird dann zusätzlich zum Passwort ein **temporärer Code** verlangt. Sie können sie jederzeit deaktivieren (ein Code ist zur Bestätigung erforderlich).
  - *Gerät verloren?* Ein Administrator kann Ihre 2FA zurücksetzen, um Ihnen den Zugang zurückzugeben.

### Tab „Kalender & Todo"
- **Hauptkalender (URL)**: Fügen Sie die Adresse eines iCal-Feeds ein (Google Calendar). Die KI kann dann Ihren Zeitplan lesen.
- **CalDAV-Server (URL, Benutzer, Passwort)**: Wenn Sie einen fortgeschrittenen Kalender (Nextcloud, Synology) verwenden, kann die KI Ereignisse direkt *erstellen* und *ändern*.

### Tab „Verhalten & Sicherheit" (Athenas Gehirn)
Dies ist der wichtigste Bereich, um das Gesamtverhalten und die Sicherungen des Rechners anzupassen. Er ist in mehrere Unterbereiche gegliedert:

#### 1. Ausführung & Schutzvorrichtungen
- `Sandbox für Code-/Befehlsausführung`: Wählen Sie **Docker** (empfohlen), damit die KI ihre Skripte in einer sicheren Sandbox ausführt, oder **Lokal**, wenn sie direkt auf Ihrem Betriebssystem agieren soll.
- `Selbstverbesserung`: Erlaubt der KI, aus ihren Fehlern zu lernen, um künftige Verhaltensregeln zu erstellen.
- `Budgets (Zeit und Tokens)`: Finanzielle Schutzvorrichtungen. Ermöglicht es, die maximale Anzahl an Sekunden (0 = unendlich) oder die maximale Anzahl an Tokens zu begrenzen, die die KI pro Aufgabe verbrauchen darf.
- `Tageskostenwarnung`: Wenn die täglichen Ausgaben diesen Schwellenwert in Euro überschreiten, erhalten Sie eine Benachrichtigung.

#### 2. Sicherheit
- `Sensible Werkzeuge automatisch genehmigen`: Standardmäßig (nicht angekreuzt) fragt die KI Sie immer um Bestätigung, bevor sie ein als „sensibel" markiertes Werkzeug verwendet (z. B. in eine Systemdatei schreiben). Wenn Sie es ankreuzen, wird die KI völlig autonom (auf eigenes Risiko).
- `Admin-Passwort / CORS-Ursprünge`: Absicherung des Webservers, um unerwünschte externe Verbindungen zu verhindern.
- `Gültigkeitsdauer einer Sitzung`: Zeit (in Stunden), bevor Sie von der Oberfläche abgemeldet werden (Standard: 168 h, also eine Woche).
- `Kontingente und Grenzen`: Das System schützt Ihre Finanzen. Ein Administrator kann in der Benutzerdatenbank ein tägliches Token-Verbrauchslimit festlegen.
- `Verschlüsselung im Ruhezustand`: Die Konversationen und Ausführungsspuren werden in der Datenbank (SQLite) über Fernet (AES-128-CBC + HMAC) verschlüsselt. Der Schlüssel wird in der `.env` Ihrer Installation gespeichert — **verlieren Sie ihn nicht** (sonst wird der verschlüsselte Verlauf unlesbar), und für echten Schutz gegen Festplattendiebstahl bewahren Sie ihn außerhalb des Ordners auf (eingeschleuste Umgebungsvariable / Secret-Manager).
- `Integrierte Schutzmaßnahmen (unsichtbar)`: Athena maskiert automatisch Ihre API-Schlüssel und Geheimnisse in den Logs (Redaction) und integriert einen Anti-SSRF-Schutz, der Web-Anfragen an Ihr internes Netzwerk oder Ihre Cloud-Metadaten blockiert.

#### 3. Orchestrierung & Agenten (fortgeschritten)
- `LLM-Routing (Delegation Router)`: Der Orchestrator liest Ihre Nachricht und wählt den richtigen Agenten.
- `Schnelles Modell`: Sie können nur für die Routing-Entscheidungen ein sehr schnelles Modell (z. B. `gpt-4o-mini` oder `haiku`) erzwingen, was die KI flinker macht.
- `Fallback-Modelle`: Wenn die API Ihrer Haupt-KI abstürzt, versucht Athena, diese Ersatzmodelle zu verwenden.
- `Prompt-Cache`: Technologie, die Geld und Zeit bei langen Konversationen spart.
- `Selbstkritik`: Wenn aktiviert, liest und prüft die KI ihre eigene Antwort, bevor sie sie Ihnen sendet.

#### 4. Speicher
- `Faktenbasis (Core Memory)`: Listet alles auf, was Athena dauerhaft über Sie gelernt hat (Ihre Vorlieben, Ihren Beruf). Sie können dort Elemente löschen.
- `Knowledge Graph`: Zusätzlich zu einfachen Fakten baut die KI ein Netzwerk von Beziehungen („Graph") zwischen den Entitäten auf, um Ihren Kontext besser zu verstehen.
- `Kompaktierung über N Nachrichten hinaus`: Um die Rechnung nicht explodieren zu lassen, fasst Athena die alten Teile der Konversation nach N Nachrichten automatisch zusammen (standardmäßig 40).
- `Aktuelle Nachrichten wörtlich behalten`: Athena behält im Kurzzeitgedächtnis immer die letzten N strikten Austausche (standardmäßig 12).

#### 5. Ausdrucksstarke Stimme
- `Sprachemotionen`: Das LLM fügt `[laugh]`-, `[sad]`-Tags in seine Texte ein, und die Sprach-Engine passt ihren Ton an!
- `Ausdrucksstarker TTS-Server & Stimme`: Wenn Sie eine Sprach-Engine eines Drittanbieters (wie XTTS) verwenden, geben Sie hier ihre IP-Adresse an.

#### 6. Räumliches Bewusstsein (Präsenz / Follow-me)
- `HA-Entität des aktuellen Raums`: Wenn Sie Anwesenheitsmelder bei Home Assistant haben, geben Sie hier die Entität an (z. B. `sensor.aktueller_raum`). Die KI weiß dann, in welchem Raum Sie sich befinden, um dort das richtige Licht einzuschalten oder ihr Verhalten anzupassen.

#### 7. Automatisierung (n8n)
- `Erlaubte Workflows`: Sie können Athena mit komplexen n8n-Automatisierungen verbinden, indem Sie ihr Zugriff auf Webadressen (Webhooks) geben.

### Die anderen Tabs des Einstellungsbereichs
Zusätzlich zu „Verhalten" gibt Ihnen die Einstellungs-Seitenleiste Zugriff auf weitere spezialisierte Menüs:

* **Tab „Wissen (RAG)"**: Hier können Sie die KI bitten, die im Datei-Explorer abgelegten Dokumente zu analysieren (oder zu löschen).
* **Tab „Routinen"**: Ermöglicht das Planen automatischer Aufgaben (z. B. „Erstelle jeden Tag um 7:00 die Hauszusammenfassung"). Sie können dort auch die „Webhook"-Adressen dieser Routinen abrufen oder dafür sorgen, dass eine Routine **einen deterministischen Workflow auslöst** (Feld „Workflow" des Formulars) statt einer einfachen Aufgabe.
* **Tab „Sprachsatelliten"**: Ermöglicht die Konfiguration der mit Athena verbundenen ESP32-Lautsprecher.
* **Tab „MCP-Erweiterungen"**: Ermöglicht das Anbinden standardmäßiger externer Plugins (z. B. GitHub-Konnektor, Home-Assistant-Konnektor) an die KI.
* **Tab „Diagnose & System"**: Prüft die Gesundheit der Installation (Datenbank, STT, TTS). Hier befindet sich die Notfall-Schaltfläche **Sprach-Engine neu starten (Kokoro)** bei Tonproblemen sowie die Optionen für **Sicherung & Wiederherstellung** Ihrer gesamten Umgebung.
* **Tab „Workflows"**: Erstellt **deterministische Pipelines** (Agentenkette, Typ „Fließband") als Alternative zum autonomen Modus — nützlich, wenn man einen reproduzierbaren und prüfbaren Ablauf wünscht. Siehe den eigenen Abschnitt weiter unten.
* **Tab „Benutzer" (Admin)**: Wenn Sie Administrator sind, können Sie hier neue Personen einladen, ihre Rechte und ihre Token-Kontingente verwalten. Sie **validieren hier auch die Automatisierungen** (Workflows/Routinen), die von „Benutzer"-Konten erstellt wurden, bevor sie ausgeführt werden können, Sie können die **2FA eines Kontos zurücksetzen** (verlorenes Gerät) und das **Audit-Protokoll** (Anmeldungen, Passwortänderungen, Validierungen…) über `GET /api/audit` einsehen.

---

## 5. 💻 Den Server verwalten (Administrationsbefehle)

Wenn Sie der Administrator des Rechners sind, der Athena hostet, verfügen Sie über leistungsstarke Systembefehle zur Verwaltung des Server-Lebenszyklus.

### 🍎 Linux & macOS
Öffnen Sie Ihr Terminal. Der Hauptbefehl heißt `athena`.
- `athena start`: Startet die KI im Hintergrund (SystemD- / LaunchAgent-Prozess).
- `athena stop`: Fährt den Server sauber herunter.
- `athena restart`: Startet die Anwendung vollständig neu.
- `athena status`: Prüft, ob der Server online ist.
- `athena logs`: Zeigt das technische Protokoll des Servers in Echtzeit an. (Drücken Sie `Strg+C` zum Beenden).

**Die Software aktualisieren:**
Gehen Sie in den Quellcode-Ordner und führen Sie aus: `./update.sh`

### 🪟 Windows (PowerShell)
Öffnen Sie PowerShell. Der Administrationsbefehl endet mit `.ps1`.
- `athena.ps1 start`: Startet den Server im Hintergrund.
- `athena.ps1 stop`: Stoppt den Server.
- `athena.ps1 restart`: Startet den Prozess neu.
- `athena.ps1 status`: Zeigt den Status an.
- `athena.ps1 logs`: Zeigt die technische Konsole des Orchestrators an.

**Die Software aktualisieren:**
Gehen Sie in den Quellcode-Ordner und führen Sie aus: `.\update.ps1`
