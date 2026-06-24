# 📖 Guida Utente di Athena

🌍 **Lingue**: [Français](USER_GUIDE.md) · [English](USER_GUIDE.en.md) · [Español](USER_GUIDE.es.md) · Italiano · [Deutsch](USER_GUIDE.de.md) · [中文](USER_GUIDE.zh.md) · [日本語](USER_GUIDE.ja.md)

Benvenuto! Se stai leggendo questa guida, è perché hai appena installato **Athena**, il tuo direttore d'orchestra di Intelligenza Artificiale multi-agente. Questo documento è pensato per aiutarti a prendere confidenza con lo strumento.

---

## ✨ Novità della versione 0.31.0

- **AthenaDesign — modifiche più rapide ed economiche**: modificare un design non riscrive più tutto il codice (si applicano solo le modifiche) → grande risparmio di token. Nuovo pulsante **⏹️ Stop** per interrompere una generazione. Scegli il **modello** direttamente nella scheda Design.
- **Traffico stradale affidabile**: il tempo di percorrenza in **auto** con ingorghi (TomTom) è ora calcolato dallo strumento dedicato, non «a memoria». (chiave TomTom gratuita nelle Impostazioni)
- *Trasporto pubblico: non disponibile — nessuna fonte gratuita affidabile, in particolare per i treni SNCF.*

---

## ✨ Novità della versione 0.30.0

- **Scelta del modello nella console Codice**: un menu **«🤖 Modello»** nella barra del terminale per scegliere al volo il LLM del codice (es. un modello «coder»), come in AthenaDesign. Vuoto = predefinito.

---

## ✨ Novità della versione 0.29.0

- **Trasporto pubblico in tempo reale**: orari, **ritardi** e perturbazioni (treno, tram, bus) + itinerari — «prossimo tram a Homme de Fer?», «il mio treno è in ritardo?». (chiave Navitia gratuita da configurare in Impostazioni)
- **OCR**: estrazione fedele del **testo da un'immagine o un PDF** (anche scansionato) — «leggi questa fattura».
- **Meteo iperlocale**: meteo preciso per coordinate (non solo la città). Indica latitudine/longitudine in Impostazioni per la precisione a livello di via.
- **Raccomandazioni contestuali**: «cosa mi consigli?» → Athena combina meteo, agenda, attività, perturbazioni e le tue preferenze.
- **Traffico stradale**: **tempo di percorrenza in auto con ingorghi** + incidenti — «quanto ci vuole per il lavoro?». (chiave TomTom gratuita)
- **Tutto configurabile nell'interfaccia**: nuova sezione «Integrazioni esterne» in Impostazioni (chiavi Navitia/TomTom, meteo, modello OCR).

---

## ✨ Novità della versione 0.28.0

- **Modello dedicato per Design e Codice**: in **Impostazioni → Il mio modello e chiavi LLM**, scegli un modello specifico per **AthenaDesign** (🎨) e per la **console Codice** (🧩), diverso da quello della chat (es. un modello «coder» per il codice e un altro per la conversazione). Gli elenchi mostrano solo i modelli **realmente accessibili** (il tuo endpoint + i provider la cui chiave è impostata).
- **Contatore di token in tempo reale**: il consumo **in entrata (↓) e in uscita (↑)** è mostrato in diretta durante la generazione (chat, design, codice). Un **totale globale** è nella barra in alto — **persistente** (mantenuto tra i riavvii) con un pulsante **↺** per azzerarlo.
- **Console Codice in diretta**: i passaggi dell'agente e il consumo vengono trasmessi **in tempo reale** (streaming), come la chat, senza attendere la fine.
- **Miglioramenti di AthenaDesign**: una modifica parte ora dalla **versione che stai visualizzando** (non più sempre dall'ultima); design più **moderni**; l'autocorrezione rileva anche le **schermate bianche** dovute al CSS.

---

## 1. 🌟 Primo Avvio e Connessione

Una volta installato e avviato Athena sulla tua macchina, l'interfaccia grafica (UI) è accessibile solo tramite il tuo browser web.

1. Apri il browser e vai all'indirizzo: **`http://localhost:8000`** (o l'indirizzo IP del tuo server se l'hai installato su un'altra macchina).
2. Se è il primissimo avvio, ti verrà chiesto di creare un account con un indirizzo email e una password.
3. Una volta connesso, arrivi sulla **Scrivania virtuale**.

---

## 2. 💬 Conversare con l'IA

Esistono **due modi** per interagire con Athena: l'Interfaccia Web e il Terminale (CLI).

### A. Dall'Interfaccia Web (UI)
È il metodo più visivo e semplice.
- **La vista 3D**: Nella pagina principale vedrai una rappresentazione visiva di Athena e dei suoi "Agenti" (il Programmatore, il Ricercatore, ecc.). Quando Athena riflette o delega un compito, vedrai animazioni luminose che ti indicano quale agente sta lavorando.
- **L'Orchestratore automatico**: Nella barra di conversazione in basso, scrivi semplicemente la tua richiesta. Nell'Interfaccia Web, **parli sempre con l'Orchestratore**. È lui ad essere abbastanza intelligente da comprendere la tua richiesta e assegnarla automaticamente all'agente giusto (es. passerà il testimone all'Agente Programmatore se chiedi uno script).
- **Artifacts nella chat**: quando l'IA produce codice anteprimabile (HTML, **React**, SVG, **Mermaid**, **Markdown**), un pulsante **«👁️ Anteprima»** apre un **pannello di anteprima agganciato** a destra — eseguito in una sandbox isolata. **Navighi tra le versioni** generate durante la conversazione, **copi/scarichi** il codice, o clicchi **«🎨 Apri in AthenaDesign»** per continuare nello studio.
- **L'Esploratore di file (Workspaces)**: A sinistra c'è un pannello con i tuoi file. Puoi trascinare e rilasciare documenti (PDF, Markdown, codice sorgente) affinché l'IA possa analizzarli.
- **L'Editor integrato (mini-IDE)**: clicca su un file per **modificarlo** direttamente nel browser — più file aperti in **schede**, evidenziazione della sintassi, autocompletamento (Ctrl+Spazio) e **salvataggio** con **Ctrl+S** (💾). Un *Lettore* di un progetto condiviso resta in sola lettura. Puoi **restringere o ripiegare l'esploratore** (maniglia centrale o pulsante «◀ Riduci») per ingrandire l'editor, e quando l'**agente modifica un file aperto**, la tua vista si **aggiorna in diretta** (insieme alla presenza degli altri lettori).
- **La Console Programmatore (terminale interattivo)**: un vero terminale dove parli con l'agente **Programmatore** per sviluppare. Specificità:
  - **Progetto target indipendente**: un selettore permette di programmare su un progetto **diverso** da quello della chat/voce (i tuoi comandi vocali e la domotica continuano sul loro contesto).
  - **Albero del progetto** a destra (la chat è nascosta lì perché inutile): si **aggiorna automaticamente** — vedi apparire i file creati dall'agente.
  - **IDE in finestra separata**: il pulsante **«⧉ IDE»** (o un clic su un file dell'albero) apre l'editor in una **vera finestra spostabile** (ideale su un 2° schermo), con schede, evidenziazione, autocompletamento e **Ctrl+S**. *(Al primo utilizzo, autorizza i pop-up per il sito.)*
  - I comandi con prefisso `$` o `!` si eseguono direttamente come shell; altrimenti l'agente Programmatore elabora la tua richiesta e **scrive i file nel progetto** (sandbox Docker montata sul progetto).

### C. Progetti e Collaborazione (Workspaces condivisi)
Un **progetto** è una cartella di lavoro dedicata. Quando selezioni un progetto nella barra dei progetti (in cima all'esploratore), **tutto ciò che fa l'IA (lettura, modifica del codice, terminale, git) è confinato a quella cartella** — pratico per isolare un repository di codice o una cartella cliente.
- **Creare / cambiare progetto**: pulsante `＋ Progetto` poi selezione dalla lista. Ogni utente ha i propri progetti, invisibili agli altri.
- **Condividere un progetto** (pulsante `👥 Condividi`): in quanto **proprietario**, inviti altri utenti e scegli il loro ruolo:
  - **Lettore**: può consultare e conversare con l'IA sul progetto, ma **non può modificare NULLA** — nemmeno chiedendolo all'agente (il blocco è applicato lato server, su ogni strumento di scrittura: modifica di file, git, bash, Python). Impossibile da aggirare.
  - **Editor**: può modificare i file, eseguire codice, fare commit.
- Solo il proprietario può condividere, cambiare i ruoli o eliminare il progetto.

### B. Dalla Console Interattiva (CLI)
Se preferisci il terminale all'interfaccia grafica, puoi avviare una conversazione di puro testo.
Vai nella cartella di Athena e digita:
`python3 athena_cli.py`

> [!TIP]
> **Forzare un agente specifico (solo Console)**: A differenza dell'interfaccia web dove l'Orchestratore gestisce tutto, la console ti permette di scavalcare il direttore e parlare direttamente con un agente specialista. Per farlo, usa:
> `python3 athena_cli.py --agent Codeur`

---

## 3. 🛠️ Cosa può fare Athena? (I Super-Poteri)

Athena non è un semplice "ChatGPT". È un framework di **agenti di intelligenza artificiale autonomi** che integrano decine di strumenti ("Skills") capaci di agire sulla tua macchina e sul web.

### 💻 Codice Agentico (Software Engineering)
È il cuore del sistema. Athena può sostituire un amministratore di sistema o uno sviluppatore:
- **Esecuzione Python e Bash (Sandbox)**: L'IA scrive codice e lo esegue in modo autonomo in una sandbox Docker sicura.
- **Creazione di Skills al volo**: Funzionalità unica, l'IA può programmare nuovi "strumenti" per migliorarsi da sola, e salvarli definitivamente nel suo codice sorgente di base!
- **Amministrazione SSH**: L'IA può connettersi ai tuoi altri server remoti via SSH per fare manutenzione.
- **Computer Use (RPA 2.0)**: L'IA può aprire un vero browser web nascosto, cliccare su pulsanti, compilare moduli e fare scraping di siti.
- **Navigazione Git e Codice**: L'IA può leggere i tuoi repository Git, comprendere il tuo codice sorgente esistente e modificarlo in diretta (ricerca file `glob`/contenuto, struttura del file, riferimenti).
- **Diagnostica dopo ogni modifica (ciclo di feedback)**: a ogni modifica di file, Athena rilegge gli **errori/avvisi** introdotti (server LSP **basedpyright** per Python, ripiego integrato altrimenti) e li **corregge subito**. Questa diagnostica appare anche nella scheda **Codice** (pulsante «🔍 Analizza»).
- **Elenco di attività di sessione**: per un lavoro in più passaggi, l'agente tiene una **checklist** (📋 Attività) visibile in `athena_cli` e nella scheda Codice, aggiornata in tempo reale.
- **Modalità piano (sola lettura)**: il pulsante **«🧭 Modalità piano»** (o `/plan` / `/build` nella CLI) — l'agente **propone un piano senza modificare nulla**; torna alla modalità normale per eseguire.
- **Istruzioni di progetto**: metti un `CLAUDE.md`, `ATHENA.md` o `AGENTS.md` nella radice del progetto (convenzioni, comandi) — Athena li carica automaticamente, a cascata fino alla radice git.
- **Manutenzione autonoma**: Un agente notturno può verificare e riparare il codice sorgente automaticamente.

### 🎨 AthenaDesign Studio (Design IA)
Uno studio di design integrato (scheda **🎨 Design**). Descrivi ciò che vuoi creare, Athena lo genera e lo **mostra in diretta**:
- **Tipi**: pagine web (HTML/CSS/JS), **app React** interattive, **diagrammi Mermaid**, e script **Python** (presentazioni **PowerPoint**, grafici). **Modelli di partenza** (Landing, Pitch deck, Dashboard…) precompilano un prompt.
- **La tua identità (Design System)**: pannello «Design System» per fornire i tuoi colori/font — a mano, incollando un CSS, tramite **«🌐 Da un URL»**, o **generandola automaticamente**: **«🧩 Dal codice»** (dedotta dal progetto: Tailwind/CSS), **«🖼️ Da un'immagine»** (palette/tipografia da una cattura), **«✨ Da una descrizione»** (identità di partenza per un progetto vuoto).
- **Riferimenti**: allega un'immagine/un documento (📎) o una pagina web (🔗) come ispirazione.
- **Affinare**: annota l'anteprima, regola in diretta (slider colore/arrotondamento/font), scorri le versioni. Se uno script Python fallisce, Athena **si corregge da sola**.
- **Condividere / esportare**: pulsante **Condividi** (link in sola lettura), **Esporta PDF**, e download dei `.pptx`.
- *Consiglio*: un progetto Athena riunisce **codice e design** — gestisci entrambi nello stesso posto.

### 🔌 Plugin (incluso Claude Code)
In **Impostazioni > 🔌 Plugin**, attiva le estensioni. Il **plugin Claude Code** ricorre all'agente di codice **Claude Code** (serve il CLI `claude` installato e connesso): una volta attivato, il tuo **Programmatore** può delegargli i compiti di codice complessi, direttamente nel progetto attivo. *(Consuma il tuo abbonamento/chiave Claude.)*

### 🏠 Domotica, Contesto e Quotidiano
- **Domotica Nativa (Home Assistant)**: L'IA si connette direttamente alla tua domotica. Chiedile *"Spegni la luce del soggiorno"* o *"Chiudi le tapparelle"* e lo fa all'istante.
- **Estensioni MCP (Avanzato)**: Athena supporta il protocollo MCP. Questo le permette di collegare plugin complessi (come un accesso profondo al database di Home Assistant per creare automazioni, o qualsiasi altro server MCP esistente).
- **Consapevolezza Spaziale**: L'IA può sapere in quale stanza ti trovi (se hai sensori) per adattare le sue azioni (es. *"Accendi la luce"* accenderà quella della stanza in cui sei).
- **Meteo e Tempo**: Previsioni meteorologiche su più giorni e sincronizzazione temporale.
- **Liste e Spesa**: Chiedile di aggiungere il latte alla tua lista della spesa o di creare una to-do list.

### 📅 Produttività e Comunicazione
- **Agenda e Pianificazione**: Sincronizzazione con i tuoi calendari (iCal, CalDAV) per leggere e creare eventi.
- **Riassunti di Riunioni**: Capacità di trascrivere e riassumere riunioni o file audio.
- **Notifiche**: Athena può inviarti messaggi di propria iniziativa su Telegram, Discord o Slack.
- **Generazione Media**: Creazione di immagini (via API Fal/Replicate) e manipolazioni di file (PDF, documenti).
- **Workflow (n8n)**: Attivazione di scenari complessi tramite webhook n8n.

### ⏰ Routine Proattive
Athena non aspetta che tu le parli. Chiedile: *"Fammi un riassunto della mia giornata ogni mattina alle 7:30"*. Si sveglierà da sola, analizzerà la tua agenda, il meteo, lo stato della tua casa, e potrà persino avviare la macchina del caffè!

---

## 4. ⚙️ Comprendere i Parametri dell'Interfaccia

Cliccando sull'icona dell'ingranaggio (⚙️) nella barra laterale, accedi alle impostazioni del tuo profilo. **Ogni parametro è strettamente isolato per il tuo utente.**

### Scheda "🔑 Chiavi API" (Il Mio Modello e Chiavi LLM)
- **Provider IA (Es: OpenAI, Anthropic, Ollama)** e **Nome del Modello**: Scegli la versione dell'IA che desideri utilizzare.
- **Chiave API Personale**: Se questo campo è compilato, Athena userà la TUA chiave per funzionare, e ti verrà addebitato sul tuo account sviluppatore. Questo permette di sovrascrivere il modello predefinito del server.
- **📊 Il mio utilizzo**: appena sotto le tue chiavi, un riepilogo del tuo consumo personale (richieste, token, costo €) di oggi, degli ultimi 30 giorni e in totale — per seguire le tue spese con un colpo d'occhio. (Un amministratore, da parte sua, vede il consumo di tutti gli account.)

### 🔐 Mettere in sicurezza il mio account (scheda «Utenti»)
- **La mia password**: cambiala quando vuoi (min. 8 caratteri). Per sicurezza, cambiare la tua password **disconnette le tue altre sessioni**.
- **Autenticazione a due fattori (2FA)**: clicca su **Attiva la 2FA**, aggiungi l'account alla tua app di autenticazione (Google Authenticator, Authy, FreeOTP…) scansionando/inserendo il segreto mostrato, poi inserisci un codice per confermare. Ad ogni connessione ti verrà allora richiesto un **codice temporaneo** oltre alla password. Puoi disattivarla in qualsiasi momento (è richiesto un codice per confermare).
  - *Dispositivo perso?* Un amministratore può reimpostare la tua 2FA per restituirti l'accesso.

### Scheda "Agenda e Todo"
- **Agenda Principale (URL)**: Incolla l'indirizzo di un flusso iCal (Google Calendar). L'IA potrà allora leggere la tua pianificazione.
- **Server CalDAV (URL, Utente, Password)**: Se usi un'agenda avanzata (Nextcloud, Synology), l'IA potrà *creare* e *modificare* eventi direttamente.

### Scheda "Comportamento e Sicurezza" (Il Cervello di Athena)
È la sezione più importante per regolare il comportamento globale e le sicurezze della macchina. È divisa in più sottosezioni:

#### 1. Esecuzione e salvaguardie
- `Sandbox di esecuzione di codice/comandi`: Scegli **Docker** (consigliato) affinché l'IA esegua i suoi script in una sandbox sicura, o **Locale** se vuoi che agisca direttamente sul tuo sistema operativo.
- `Auto-miglioramento`: Autorizza l'IA a trarre lezioni dai suoi fallimenti per creare regole di comportamento future.
- `Budget (Tempo e Token)`: Salvaguardie finanziarie. Permette di limitare il numero massimo di secondi (0 = infinito) o il numero massimo di token che l'IA ha il diritto di consumare per compito.
- `Allerta costo del giorno`: Se la spesa giornaliera supera questa soglia in euro, riceverai una notifica.

#### 2. Sicurezza
- `Auto-approvare gli strumenti sensibili`: Per impostazione predefinita (non selezionato), l'IA ti chiederà sempre una conferma prima di usare uno strumento marcato come "sensibile" (es. scrivere in un file di sistema). Se lo selezioni, l'IA diventa totalmente autonoma (a tuo rischio e pericolo).
- `Password admin / Origini CORS`: Messa in sicurezza del server web per impedire connessioni esterne indesiderate.
- `Durata di validità di una sessione`: Tempo (in ore) prima di essere disconnesso dall'interfaccia (predefinito: 168h, ovvero una settimana).
- `Quote e Limiti`: Il sistema protegge le tue finanze. Un amministratore può definire un limite di consumo di token al giorno nel database degli utenti.
- `Cifratura a riposo`: Le conversazioni e le tracce di esecuzione sono cifrate in database (SQLite) tramite Fernet (AES-128-CBC + HMAC). La chiave è memorizzata nel `.env` della tua installazione — **non perderla** (altrimenti la cronologia cifrata diventa illeggibile), e per una vera protezione contro il furto di disco, conservala fuori dalla cartella (variabile d'ambiente iniettata / secret manager).
- `Protezioni integrate (invisibili)`: Athena maschera automaticamente le tue chiavi API e i segreti nei log (Redaction) e integra una protezione anti-SSRF che blocca le richieste web verso la tua rete interna o i tuoi metadati Cloud.

#### 3. Orchestrazione e agenti (avanzato)
- `Instradamento LLM (Delegation Router)`: L'Orchestratore legge il tuo messaggio e sceglie l'agente giusto.
- `Modello rapido`: Puoi forzare un modello molto veloce (es. `gpt-4o-mini` o `haiku`) solo per le decisioni di instradamento, il che rende l'IA più reattiva.
- `Modelli di ripiego (Fallback)`: Se l'API della tua IA principale va in crash, Athena tenterà di usare questi modelli di riserva.
- `Cache del prompt`: Tecnologia che permette di risparmiare denaro e tempo sulle conversazioni lunghe.
- `Auto-critica`: Se attivata, l'IA rilegge e verifica la propria risposta prima di inviartela.

#### 4. Memoria
- `Base di fatti (Core Memory)`: Elenca tutto ciò che Athena ha imparato su di te in modo permanente (i tuoi gusti, il tuo mestiere). Puoi eliminare elementi lì.
- `Knowledge Graph`: Oltre ai fatti semplici, l'IA costruisce una rete di relazioni ("Grafo") tra le entità per comprendere meglio il tuo contesto.
- `Compattazione oltre N messaggi`: Per evitare di far esplodere la fattura, Athena riassume automaticamente le vecchie parti della conversazione dopo N messaggi (40 per impostazione predefinita).
- `Messaggi recenti conservati parola per parola`: Athena conserva sempre gli ultimi N scambi rigorosi in memoria a breve termine (12 per impostazione predefinita).

#### 5. Voce espressiva
- `Emozioni vocali`: Il LLM inserisce tag `[laugh]`, `[sad]` nei suoi testi, e il motore vocale adatta il suo tono!
- `Server TTS espressivo e Voce`: Se usi un motore vocale di terze parti (come XTTS), indica qui il suo indirizzo IP.

#### 6. Consapevolezza Spaziale (Presenza / follow-me)
- `Entità HA della stanza corrente`: Se hai rilevatori di presenza su Home Assistant, indica qui l'entità (es. `sensor.stanza_corrente`). L'IA saprà allora in quale stanza sei per accendervi la luce giusta o adattare il suo comportamento.

#### 7. Automazione (n8n)
- `Workflow autorizzati`: Puoi connettere Athena a complesse automazioni n8n dandole accesso a indirizzi web (Webhook).

### Le altre Schede del Pannello Impostazioni
Oltre a "Comportamento", la barra laterale delle impostazioni ti dà accesso ad altri menu specializzati:

* **Scheda "Conoscenze (RAG)"**: È qui che puoi chiedere all'IA di analizzare (o eliminare) i documenti che hai messo nell'Esploratore di file.
* **Scheda "Routine"**: Permette di programmare compiti automatici (es. "Fai il riassunto della casa ogni giorno alle 7:00"). Puoi anche recuperare lì gli indirizzi "Webhook" di queste routine, o fare in modo che una routine **attivi un Workflow** deterministico (campo «Workflow» del modulo) invece di un semplice compito.
* **Scheda "Satelliti Vocali"**: Permette di configurare gli altoparlanti ESP32 connessi ad Athena.
* **Scheda "Estensioni MCP"**: Permette di collegare plugin esterni standard (es. connettore GitHub, connettore Home Assistant) all'IA.
* **Scheda "Diagnostica e Sistema"**: Verifica la salute dell'installazione (database, STT, TTS). È qui che si trova il pulsante d'emergenza **Riavvia il motore Vocale (Kokoro)** in caso di bug sonoro, così come le opzioni di **Backup e Ripristino** del tuo ambiente completo.
* **Scheda "Workflow"**: Crea **pipeline deterministiche** (catena di agenti, tipo "linea di montaggio") in alternativa alla modalità autonoma — utile quando si vuole uno svolgimento riproducibile e verificabile. Vedi la sezione dedicata più sotto.
* **Scheda "Utenti" (Admin)**: Se sei amministratore, qui puoi invitare nuove persone, gestire i loro diritti e le loro quote di token. **Convalidi anche le automazioni** (workflow/routine) create dagli account "utente" prima che possano essere eseguite, puoi **reimpostare la 2FA** di un account (dispositivo perso), e consultare il **registro di audit** (connessioni, cambi di password, convalide…) tramite `GET /api/audit`.

---

## 5. 💻 Gestire il Server (Comandi di Amministrazione)

Se sei l'amministratore della macchina che ospita Athena, disponi di potenti comandi di sistema per gestire il ciclo di vita del server.

### 🍎 Linux e macOS
Apri il tuo Terminale. Il comando principale si chiama `athena`.
- `athena start`: Accende l'IA in background (processo SystemD / LaunchAgent).
- `athena stop`: Spegne il server in modo pulito.
- `athena restart`: Riavvia completamente l'applicazione.
- `athena status`: Verifica se il server è effettivamente online.
- `athena logs`: Mostra il registro tecnico del server in tempo reale. (Premi `Ctrl+C` per uscire).

**Aggiornare il software:**
Vai nella cartella del codice sorgente e lancia: `./update.sh`

### 🪟 Windows (PowerShell)
Apri PowerShell. Il comando di amministrazione termina con `.ps1`.
- `athena.ps1 start`: Avvia il server in attività di sfondo.
- `athena.ps1 stop`: Spegne il server.
- `athena.ps1 restart`: Riavvia il processo.
- `athena.ps1 status`: Mostra lo stato.
- `athena.ps1 logs`: Mostra la console tecnica dell'orchestratore.

**Aggiornare il software:**
Vai nella cartella del codice sorgente e lancia: `.\update.ps1`
