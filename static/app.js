// Authentification et Gestion de Session
let sessionToken = localStorage.getItem("jarvis_session_token") || "";
let chatClientId = localStorage.getItem("jarvis_client_id") || "web";

// SSO OIDC : récupère le jeton renvoyé par le callback (?sso_token=) puis nettoie l'URL.
try {
    const _p = new URLSearchParams(window.location.search);
    const _sso = _p.get("sso_token");
    if (_sso) {
        sessionToken = _sso;
        localStorage.setItem("jarvis_session_token", _sso);
        _p.delete("sso_token");
        const _q = _p.toString();
        window.history.replaceState({}, "", window.location.pathname + (_q ? "?" + _q : ""));
    }
} catch (e) { /* ignore */ }

// Wrapper de fetch sécurisé avec injecteur de jeton d'autorisation Bearer
function setServerReachable(ok) {
    const banner = document.getElementById("server-down-banner");
    if (banner) banner.style.display = ok ? "none" : "block";
    if (document.body) document.body.style.paddingTop = ok ? "" : "38px";
}

async function apiFetch(url, options = {}) {
    if (!options.headers) {
        options.headers = {};
    }
    if (sessionToken) {
        options.headers["Authorization"] = `Bearer ${sessionToken}`;
    }
    let response;
    try {
        response = await fetch(url, options);
    } catch (e) {
        // Échec réseau = serveur backend injoignable (éteint, crashé, port fermé).
        setServerReachable(false);
        throw e;
    }
    setServerReachable(true);
    if (response.status === 401) {
        localStorage.removeItem("jarvis_session_token");
        sessionToken = "";
        showLoginOverlay();
    }
    return response;
}

// Branding : nom d'appli configurable via APP_NAME (.env) — appliqué titre + logo.
async function applyBranding() {
    try {
        const r = await fetch("/api/platform", { cache: "no-store" });
        setServerReachable(true);
        const d = await r.json();
        const name = (d && d.app_name) ? d.app_name : "Jarvis";
        document.title = `${name} — Assistant Multi-Agent`;
        const logo = document.querySelector(".logo-title");
        if (logo) logo.textContent = name.toUpperCase();
        const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
        if (appleTitle) appleTitle.setAttribute("content", name);
    } catch (e) {
        setServerReachable(false);
    }
}

async function loadSystemVersion() {
    try {
        const r = await fetch("/api/system/version", { cache: "no-store" });
        if (r.ok) {
            const data = await r.json();
            const el = document.getElementById("app-version-display");
            if (el && data.version) {
                el.textContent = `v${data.version}`;
            }
        }
    } catch (e) {
        console.error("Failed to load system version:", e);
    }
}

// Sonde de disponibilité : ping léger pour afficher/masquer le bandeau même au repos.
async function _pingServer() {
    try {
        await fetch("/api/platform", { method: "GET", cache: "no-store" });
        setServerReachable(true);
    } catch (e) {
        setServerReachable(false);
    }
}
setInterval(_pingServer, 15000);
window.addEventListener("DOMContentLoaded", () => {
    applyBranding();
    loadSystemVersion();
});

function showLoginOverlay() {
    const overlay = document.getElementById("login-overlay");
    if (overlay) {
        overlay.style.display = "flex";
        document.getElementById("btn-logout").style.display = "none";
        document.getElementById("login-password").focus();
        // Affiche le bouton SSO uniquement si l'OIDC est configuré côté serveur.
        fetch("/api/auth/oidc/status").then(r => r.json()).then(d => {
            const b = document.getElementById("btn-sso-login");
            if (b) b.style.display = d && d.enabled ? "block" : "none";
        }).catch(() => {});
    }
}

function ssoLogin() {
    // Redirection vers l'IdP ; le callback renvoie au SPA avec ?sso_token=.
    window.location.href = "/api/auth/oidc/login";
}

function toggleRegister() {
    const box = document.getElementById("register-box");
    if (box) box.style.display = box.style.display === "none" ? "flex" : "none";
}

async function submitRegister() {
    const code = document.getElementById("reg-code").value.trim();
    const username = document.getElementById("reg-username").value.trim();
    const password = document.getElementById("reg-password").value;
    const err = document.getElementById("register-error");
    err.style.display = "none";
    if (!code || !username || (password || "").length < 4) {
        err.textContent = "Code, nom d'utilisateur et mot de passe (min. 4) requis.";
        err.style.display = "block";
        return;
    }
    try {
        const r = await fetch("/api/register", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code, username, password }),
        });
        const data = await r.json();
        if (!r.ok) {
            err.textContent = "❌ " + (data.detail || "Inscription refusée.");
            err.style.display = "block";
            return;
        }
        // Compte créé + session ouverte : on stocke le jeton et on entre.
        sessionToken = data.token;
        localStorage.setItem("jarvis_session_token", data.token);
        hideLoginOverlay();
        window.location.reload();
    } catch (e) {
        err.textContent = "❌ Erreur réseau.";
        err.style.display = "block";
    }
}

function hideLoginOverlay() {
    const overlay = document.getElementById("login-overlay");
    if (overlay) {
        overlay.style.display = "none";
        if (sessionToken && sessionToken !== "no-auth-required") {
            document.getElementById("btn-logout").style.display = "inline-block";
        }
    }
}

async function submitLogin() {
    const passwordInput = document.getElementById("login-password");
    const usernameInput = document.getElementById("login-username");
    const errorMsg = document.getElementById("login-error");
    const password = passwordInput.value.trim();
    const username = usernameInput ? usernameInput.value.trim() : "";

    errorMsg.style.display = "none";

    try {
        const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password, username: username || undefined })
        });

        if (response.ok) {
            const data = await response.json();
            sessionToken = data.token;
            localStorage.setItem("jarvis_session_token", sessionToken);
            // Conversation par utilisateur (sauf admin/local -> 'web' historique).
            chatClientId = (data.username && !["admin", "local"].includes(data.username)) ? `web:${data.username}` : "web";
            localStorage.setItem("jarvis_client_id", chatClientId);
            passwordInput.value = "";
            hideLoginOverlay();
            
            // Recharger les données du dashboard après connexion réussie
            reloadSwarmConfig();
            loadWorkspaceFiles();
            loadGlobalConfig();
            loadAvailableModels();
        } else {
            errorMsg.style.display = "block";
            passwordInput.value = "";
            passwordInput.focus();
        }
    } catch (err) {
        console.error("Erreur de connexion:", err);
        errorMsg.textContent = "❌ Impossible de contacter le serveur.";
        errorMsg.style.display = "block";
    }
}

function handleLogout() {
    localStorage.removeItem("jarvis_session_token");
    sessionToken = "";
    showLoginOverlay();
}

// Initialisation de la sécurité au chargement
window.addEventListener("DOMContentLoaded", () => {
    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", handleLogout);
    }
    checkAuthRequirements();
});

async function checkAuthRequirements() {
    try {
        const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: "" })
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.token === "no-auth-required") {
                hideLoginOverlay();
                return;
            }
        }
        
        if (sessionToken) {
            hideLoginOverlay();
            reloadSwarmConfig();
        } else {
            showLoginOverlay();
        }
    } catch (err) {
        console.error("Erreur d'initialisation auth:", err);
        showLoginOverlay();
    }
}

// Configuration générale
const AGENT_COLORS = {
    Jarvis: "#00f0ff",
    Codeur: "#00ff66",
    Auteur: "#d600ff",
    Correcteur: "#ffb700",
    Traducteur: "#ff007f"
};

const AGENT_EMOJIS = {
    Jarvis: "🤖",
    Codeur: "💻",
    Auteur: "✍️",
    Correcteur: "🔍",
    Traducteur: "🌐",
    robot_neon: "🤖",
    dev_purple: "💻",
    writer_orange: "✍️",
    manager_gold: "👑",
    artist_pink: "🎨",
    support_green: "🎧",
    scientist_blue: "🔬",
    agent_dark: "🕶️",
    wizard_purple: "🧙‍♂️",
    cyber_neko: "🐱",
    astronaut_white: "🚀",
    cyber_ninja: "🥷"
};

// Obtenir une couleur aléatoire si non définie d'origine
function getAgentColor(name) {
    if (AGENT_COLORS[name]) return AGENT_COLORS[name];
    // Génère une couleur HSL harmonieuse
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    let h = Math.abs(hash % 360);
    return `hsl(${h}, 85%, 50%)`;
}

function getAgentEmoji(name) {
    const key = name ? name.toLowerCase() : "";
    if (AGENT_EMOJIS[name]) return AGENT_EMOJIS[name];
    if (AGENT_EMOJIS[key]) return AGENT_EMOJIS[key];
    return "👤";
}

// Variables d'état
let currentActiveAgent = "Jarvis";
let agentsConfig = [];
let activeAbortController = null;
let activeRunId = null;
let pendingChatAttachment = null;  // pièce jointe à injecter dans le prochain message

// Éléments du DOM
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSendBtn = document.querySelector(".chat-send-btn");
const chatMessages = document.getElementById("chat-messages");
const activeAgentTitle = document.getElementById("active-agent-title");
const pulseIndicator = document.querySelector(".pulse-indicator");
const logsTerminal = document.getElementById("logs-terminal");
const memoryGrid = document.getElementById("memory-grid");
const btnReset = document.getElementById("btn-reset");

// Onglets Panneau Gauche / Sidebar Dock
const tabCockpit = document.getElementById("tab-cockpit");
const tabGraph = document.getElementById("tab-graph");
const tabOffice = document.getElementById("tab-office");
const tabFiles = document.getElementById("tab-files");
const tabAgenda = document.getElementById("tab-agenda");
const tabBranches = document.getElementById("tab-branches");
const tabMemory = document.getElementById("tab-memory");
const tabConsole = document.getElementById("tab-console");
const tabMeeting = document.getElementById("tab-meeting");
const tabOrchestrator = document.getElementById("tab-orchestrator");

const viewCockpit = document.getElementById("view-cockpit");
const viewGraph = document.getElementById("view-graph");
const viewOffice = document.getElementById("view-office");
const viewFiles = document.getElementById("view-files");
const viewAgenda = document.getElementById("view-agenda");
const viewBranches = document.getElementById("view-branches");
const viewMemory = document.getElementById("view-memory");
const viewConsole = document.getElementById("view-console");
const viewMeeting = document.getElementById("view-meeting");
const viewOrchestrator = document.getElementById("view-orchestrator");
const logsOrchestrator = document.getElementById("logs-orchestrator");

// Gestion de la Modale Paramètres
const btnSettings = document.getElementById("btn-settings");
const settingsModal = document.getElementById("settings-modal");
const modalClose = document.getElementById("modal-close");
const modalTabAgents = document.getElementById("modal-tab-agents");
const modalTabKeys = document.getElementById("modal-tab-keys");
const modalTabSsh = document.getElementById("modal-tab-ssh");
const modalTabAgenda = document.getElementById("modal-tab-agenda");
const modalTabPricing = document.getElementById("modal-tab-pricing");
const modalTabBehavior = document.getElementById("modal-tab-behavior");
const paneBehavior = document.getElementById("pane-behavior");
const modalTabMcp = document.getElementById("modal-tab-mcp");
const paneMcp = document.getElementById("pane-mcp");
const modalTabRoutines = document.getElementById("modal-tab-routines");
const paneRoutines = document.getElementById("pane-routines");
const modalTabKnowledge = document.getElementById("modal-tab-knowledge");
const paneKnowledge = document.getElementById("pane-knowledge");
const modalTabUsers = document.getElementById("modal-tab-users");
const paneUsers = document.getElementById("pane-users");
const paneAgents = document.getElementById("pane-agents");
const paneKeys = document.getElementById("pane-keys");
const paneSsh = document.getElementById("pane-ssh");
const paneAgenda = document.getElementById("pane-agenda");
const panePricing = document.getElementById("pane-pricing");
const modalTabSatellites = document.getElementById("modal-tab-satellites");
const paneSatellites = document.getElementById("pane-satellites");
const modalTabDoctor = document.getElementById("modal-tab-doctor");
const paneDoctor = document.getElementById("pane-doctor");
const modalTabMessaging = document.getElementById("modal-tab-messaging");
const paneMessaging = document.getElementById("pane-messaging");

// Gestion de la Modale Interne Agent Form
const agentFormModal = document.getElementById("agent-form-modal");
const agentFormClose = document.getElementById("agent-form-close");
const btnAddAgent = document.getElementById("btn-add-agent");
const agentConfigForm = document.getElementById("agent-config-form");
const agentsList = document.getElementById("agents-list");

// =========================================================================
// NAVIGATION DES ONGLETS GAUCHE DOCK (OFFICE vs COCKPIT vs FILES vs AGENDA vs GRAPH vs BRANCHES vs MEMORY vs CONSOLE)
// =========================================================================
function selectActiveTab(tab, view, extraAction = null) {
    const allTabs = [tabCockpit, tabGraph, tabOffice, tabFiles, tabAgenda, tabBranches, tabMemory, tabOrchestrator, tabConsole, tabMeeting];
    const allViews = [viewCockpit, viewGraph, viewOffice, viewFiles, viewAgenda, viewBranches, viewMemory, viewOrchestrator, viewConsole, viewMeeting];
    
    allTabs.forEach(t => { if (t) t.classList.remove("active"); });
    allViews.forEach(v => { if (v) v.style.display = "none"; });
    
    if (tab) tab.classList.add("active");
    if (view) {
        // Le graphe et la mémoire ont besoin de display block, les autres flex
        if (view === viewGraph || view === viewMemory) {
            view.style.display = "block";
        } else {
            view.style.display = "flex";
        }
    }
    
    if (extraAction) extraAction();
}

// Menu "Plus" du dock : ouvre/ferme la liste des vues secondaires.
const dockMoreBtn = document.getElementById("dock-more-btn");
const dockMoreMenu = document.getElementById("dock-more-menu");
if (dockMoreBtn && dockMoreMenu) {
    dockMoreBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        dockMoreMenu.style.display = (dockMoreMenu.style.display === "none" || !dockMoreMenu.style.display) ? "flex" : "none";
    });
    dockMoreMenu.querySelectorAll(".dock-btn").forEach(b =>
        b.addEventListener("click", () => { dockMoreMenu.style.display = "none"; }));
    document.addEventListener("click", (e) => {
        if (!dockMoreMenu.contains(e.target) && !dockMoreBtn.contains(e.target)) {
            dockMoreMenu.style.display = "none";
        }
    });
}

if (tabOffice) {
    tabOffice.addEventListener("click", () => {
        selectActiveTab(tabOffice, viewOffice, () => {
            rebuildOfficeFloor();
        });
    });
}

if (tabCockpit) {
    tabCockpit.addEventListener("click", () => {
        selectActiveTab(tabCockpit, viewCockpit, () => {
            loadCockpitData();
            loadGalleryMedia();
        });
    });
}

if (tabGraph) {
    tabGraph.addEventListener("click", () => {
        selectActiveTab(tabGraph, viewGraph, () => {
            setTimeout(updateNetworkLines, 100);
        });
    });
}

if (tabFiles) {
    tabFiles.addEventListener("click", () => {
        selectActiveTab(tabFiles, viewFiles, () => {
            loadWorkspaceFiles();
        });
    });
}

if (tabAgenda) {
    tabAgenda.addEventListener("click", () => {
        selectActiveTab(tabAgenda, viewAgenda, () => {
            loadListItems();
        });
    });
}

if (tabBranches) {
    tabBranches.addEventListener("click", () => {
        selectActiveTab(tabBranches, viewBranches, () => {
            reloadChatHistory(false);
        });
    });
}

if (tabMemory) {
    tabMemory.addEventListener("click", () => {
        selectActiveTab(tabMemory, viewMemory, () => {
            refreshMemory();
        });
    });
}

if (tabConsole) {
    tabConsole.addEventListener("click", () => {
        selectActiveTab(tabConsole, viewConsole);
    });
}

if (tabOrchestrator) {
    tabOrchestrator.addEventListener("click", () => {
        selectActiveTab(tabOrchestrator, viewOrchestrator);
    });
}

if (tabMeeting) {
    tabMeeting.addEventListener("click", () => {
        selectActiveTab(tabMeeting, viewMeeting);
    });
}

// =========================================================================
// RECONSTRUCTION DYNAMIQUE DU RESEAU & DES BUREAUX
// =========================================================================
// Orchestrateur courant (renommable) : flag orchestrator, sinon "Jarvis", sinon 1er agent.
function orchestratorAgent() {
    if (!Array.isArray(agentsConfig) || !agentsConfig.length) return null;
    return agentsConfig.find(a => a.orchestrator === true)
        || agentsConfig.find(a => a.name === "Jarvis")
        || agentsConfig[0];
}
function orchestratorName() {
    const a = orchestratorAgent();
    return (a && (a.display_name || a.name)) || "l'assistant";
}

async function reloadSwarmConfig() {
    try {
        const response = await apiFetch("/api/config/agents");
        agentsConfig = await response.json();
        
        // Mettre à jour dynamiquement le badge du nombre d'agents
        const badgeOffice = document.getElementById("badge-office");
        if (badgeOffice) {
            badgeOffice.textContent = agentsConfig.length;
            badgeOffice.style.display = agentsConfig.length > 0 ? "flex" : "none";
        }
        
        // Peupler dynamiquement le sélecteur d'agent pour la console
        const agentSelect = document.getElementById("terminal-agent-select");
        if (agentSelect && Array.isArray(agentsConfig)) {
            agentSelect.innerHTML = "";
            agentsConfig.forEach(a => {
                const opt = document.createElement("option");
                opt.value = a.name;
                opt.textContent = a.name;
                agentSelect.appendChild(opt);
            });
            // Sélectionner Codeur par défaut, sinon l'orchestrateur
            const hasCodeur = agentsConfig.some(a => a.name === "Codeur");
            agentSelect.value = hasCodeur ? "Codeur" : (orchestratorAgent()?.name || agentsConfig[0].name);
        }
        
        rebuildGraphView();
        rebuildOfficeFloor();

        // Si la modale de réglages est ouverte, rafraîchir aussi la liste d'agents
        // (sinon elle reste figée sur l'ancien effectif jusqu'à réouverture).
        const settingsModalEl = document.getElementById("settings-modal");
        if (settingsModalEl && settingsModalEl.style.display === "flex" &&
            typeof loadConfigAgentsPane === "function") {
            loadConfigAgentsPane();
        }

        // Charger également l'historique arborescent et la mémoire
        reloadChatHistory();
        refreshMemory();
    } catch (err) {
        logToTerminal("Erreur de chargement de la config essaim: " + err, "error");
    }
}

// 1. Reconstruction de la vue Graphe (Nœuds positionnés en polygone)
function rebuildGraphView() {
    const container = document.getElementById("nodes-container");
    container.innerHTML = "";
    
    const svg = document.querySelector(".network-links");
    svg.innerHTML = ""; // Vider les anciennes liaisons SVG
    
    const count = agentsConfig.length;
    if (count === 0) return;
    
    // Rayon du cercle de positionnement
    const radiusX = 100;
    const radiusY = 110;
    const centerX = 160;
    const centerY = 160;
    
    // Génération des nœuds
    agentsConfig.forEach((agent, i) => {
        // Coordonnées trigonométriques pour le cercle
        const angle = (i * 2 * Math.PI) / count - Math.PI / 2; // Commencer en haut
        const x = centerX + radiusX * Math.cos(angle);
        const y = centerY + radiusY * Math.sin(angle);
        
        const node = document.createElement("div");
        node.className = "agent-node";
        if (agent.name === currentActiveAgent) node.classList.add("active");
        node.id = `node-${agent.name}`;
        node.style.left = `${x}px`;
        node.style.top = `${y}px`;
        node.style.transform = "translate(-50%, -50%)";
        
        node.innerHTML = `
            <div class="node-glow"></div>
            <div class="node-avatar">${getAgentEmoji(agent.name)}</div>
            <span class="node-name">${agent.name}</span>
        `;
        container.appendChild(node);
    });
    
    // Génération des connexions (handoffs) dynamiques
    agentsConfig.forEach(agent => {
        const handoffs = agent.handoffs || [];
        handoffs.forEach(target => {
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            line.id = `link-${agent.name}-${target}`;
            line.setAttribute("class", "link-line");
            svg.appendChild(line);
        });
    });
    
    updateNetworkLines();
}

// 2. Mettre à jour le tracé physique des lignes du graphe sémantique
function updateNetworkLines() {
    if (viewGraph.style.display === "none") return;
    
    agentsConfig.forEach(agent => {
        const handoffs = agent.handoffs || [];
        handoffs.forEach(target => {
            const fromNode = document.getElementById(`node-${agent.name}`);
            const toNode = document.getElementById(`node-${target}`);
            const line = document.getElementById(`link-${agent.name}-${target}`);
            
            if (fromNode && toNode && line) {
                // Centre des avatars
                const fromX = fromNode.offsetLeft;
                const fromY = fromNode.offsetTop;
                const toX = toNode.offsetLeft;
                const toY = toNode.offsetTop;
                
                line.setAttribute("x1", fromX);
                line.setAttribute("y1", fromY);
                line.setAttribute("x2", toX);
                line.setAttribute("y2", toY);
            }
        });
    });
}

// 3. Reconstruction du Bureau Virtuel (Swarm Open Space - Rendu Isométrique)
const agentOfficePositions = {
    "Jarvis": { top: "24%", left: "54%" },            // Bureau principal surélevé
    "Codeur": { top: "70%", left: "68%" },            // Grand bureau de dev (Robert)
    "Auteur": { top: "58%", left: "26%" },            // Bureau créatif avec tablette (Émilie)
    "Correcteur": { top: "72%", left: "28%" },        // Bureau d'édition méticuleux (Marc)
    "Traducteur": { top: "52%", left: "72%" },        // Bureau linguistique (Sofia)
    "CommunityManager": { top: "38%", left: "44%" }   // Bureau de communication (Lucas)
};

function getAgentPosition(agentName, index) {
    if (agentOfficePositions[agentName]) {
        return agentOfficePositions[agentName];
    }
    // Génération d'une position circulaire/procédurale pour les agents supplémentaires
    const angle = (index * 72) % 360;
    const rad = (angle * Math.PI) / 180;
    const top = Math.round(50 + 25 * Math.sin(rad)) + "%";
    const left = Math.round(50 + 25 * Math.cos(rad)) + "%";
    return { top, left };
}

function getAgentSpriteSVG(typeOrName) {
    const key = (typeOrName || "").toLowerCase();

    // Personnages flat-design cohérents (mêmes proportions, ombrage doux).
    const baseStyle = "width: 84px; height: 96px; filter: drop-shadow(0 6px 9px rgba(0,0,0,0.45)); transition: all 0.3s;";

    function character(o) {
        const skin = o.skin || "#eab98f";
        const skinShade = o.skinShade || "#d49e72";
        const jacket = o.jacket || "#1f2937";
        const jacketShade = o.jacketShade || "rgba(0,0,0,0.16)";
        const pants = o.pants || "#334155";
        const shoes = o.shoes || "#0b1220";
        const accent = o.accent || "#00f0ff";
        return `
        <svg class="sprite-svg" viewBox="0 0 64 88" style="${baseStyle}" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="32" cy="83" rx="15" ry="3" fill="rgba(0,0,0,0.28)"/>
          <!-- jambes + chaussures -->
          <rect x="25" y="60" width="6.6" height="18" rx="3.3" fill="${pants}"/>
          <rect x="32.4" y="60" width="6.6" height="18" rx="3.3" fill="${pants}"/>
          <rect x="23.5" y="75.5" width="9.5" height="4.8" rx="2.2" fill="${shoes}"/>
          <rect x="31" y="75.5" width="9.5" height="4.8" rx="2.2" fill="${shoes}"/>
          <!-- bras -->
          <rect x="15.5" y="40" width="7" height="20" rx="3.5" fill="${jacket}"/>
          <rect x="41.5" y="40" width="7" height="20" rx="3.5" fill="${jacket}"/>
          <rect x="41.5" y="40" width="7" height="20" rx="3.5" fill="rgba(0,0,0,0.14)"/>
          <!-- mains -->
          <circle cx="19" cy="60" r="3.1" fill="${skin}"/>
          <circle cx="45" cy="60" r="3.1" fill="${skin}"/>
          <!-- torse / veste -->
          <path d="M19 41 Q19 35.5 24.5 35 L39.5 35 Q45 35.5 45 41 L45 60 Q45 63 42 63 L22 63 Q19 63 19 60 Z" fill="${jacket}"/>
          <path d="M32 35 L45 41 L45 60 Q45 63 42 63 L32 63 Z" fill="${jacketShade}"/>
          ${o.collar || ""}
          <line x1="32" y1="37" x2="32" y2="61.5" stroke="${accent}" stroke-width="1.1" opacity="0.8"/>
          ${o.chest || ""}
          <!-- cou + tête -->
          <rect x="28.5" y="30" width="7" height="7" rx="2.2" fill="${skinShade}"/>
          <rect x="20" y="11" width="24" height="23" rx="11" fill="${skin}"/>
          <path d="M32 11 Q44 12 44 22 Q44 34 32 34 Z" fill="rgba(0,0,0,0.06)"/>
          <circle cx="20" cy="23" r="2.2" fill="${skin}"/>
          <circle cx="44" cy="23" r="2.2" fill="${skin}"/>
          ${o.hair || ""}
          <!-- yeux + sourcils + sourire -->
          <ellipse cx="27.6" cy="22.4" rx="1.5" ry="2" fill="#243044"/>
          <ellipse cx="36.4" cy="22.4" rx="1.5" ry="2" fill="#243044"/>
          <circle cx="28.1" cy="21.7" r="0.5" fill="#fff"/>
          <circle cx="36.9" cy="21.7" r="0.5" fill="#fff"/>
          <path d="M25.4 18.6 Q27.6 17.6 29.6 18.7" stroke="${skinShade}" stroke-width="0.8" fill="none" stroke-linecap="round"/>
          <path d="M34.4 18.7 Q36.4 17.6 38.6 18.6" stroke="${skinShade}" stroke-width="0.8" fill="none" stroke-linecap="round"/>
          <path d="M28.5 27 Q32 30 35.5 27" stroke="#b3603f" stroke-width="1.1" fill="none" stroke-linecap="round"/>
          ${o.face || ""}
          ${o.accessory || ""}
        </svg>`;
    }
    
    if (key === "robot_neon" || key === "jarvis") {
        return character({
            skin: "#e7b489", skinShade: "#cf9669",
            jacket: "#0c2a3a", pants: "#0f3a52", shoes: "#00f0ff", accent: "#00f0ff",
            hair: `<path d="M19.5 17 Q20 9 32 9 Q44 9 44.5 17 Q42 12 36 11 Q32 10 28 11 Q22 12 19.5 17 Z" fill="#13303f"/>`,
            face: `<rect x="24" y="20" width="16" height="4.6" rx="2.3" fill="rgba(0,240,255,0.12)" stroke="#00f0ff" stroke-width="1.1"/>`,
            collar: `<path d="M27 35 L37 35 L32 41 Z" fill="#00f0ff" opacity="0.85"/>`,
            chest: `<rect x="27.5" y="45" width="9" height="6" rx="1" fill="none" stroke="#00f0ff" stroke-width="0.8" opacity="0.7"/>`,
            accessory: `<rect x="50" y="40" width="9" height="13" rx="1.5" fill="rgba(0,240,255,0.18)" stroke="#00f0ff" stroke-width="1"/><line x1="52" y1="44" x2="57" y2="44" stroke="#00f0ff" stroke-width="0.8"/><line x1="52" y1="47" x2="56" y2="47" stroke="#00f0ff" stroke-width="0.8"/>`
        });
    } else if (key === "dev_purple" || key === "codeur" || key === "developer") {
        return character({
            skin: "#d79e6e", skinShade: "#bd8456",
            jacket: "#2e1065", pants: "#3b3650", shoes: "#a855f7", accent: "#10b981",
            hair: `<path d="M18.5 21 Q18 8 32 7.5 Q46 8 45.5 21 Q43 13 36 11 Q32 10 28 11 Q21 13 18.5 21 Z" fill="#3b1d8a"/>`,
            face: `<rect x="24" y="20" width="16" height="4.4" rx="2.2" fill="#022c22" stroke="#10b981" stroke-width="1"/>`,
            collar: `<path d="M26 35 L38 35 L34 40 L30 40 Z" fill="#a855f7" opacity="0.8"/>`,
            accessory: `<rect x="49" y="45" width="11" height="8" rx="1" fill="#0f172a" stroke="#10b981" stroke-width="0.9"/><rect x="48.5" y="52.5" width="12" height="2" rx="0.6" fill="#10b981" opacity="0.45"/><line x1="51" y1="48" x2="58" y2="48" stroke="#10b981" stroke-width="0.6" stroke-dasharray="1.2,1.2"/>`
        });
    } else if (key === "writer_orange" || key === "redacteur" || key === "rédacteur" || key === "auteur") {
        return character({
            skin: "#f1c9a5", skinShade: "#dcab82",
            jacket: "#ece6dc", jacketShade: "rgba(0,0,0,0.10)", pants: "#4c1d95", shoes: "#1e1b4b", accent: "#ec4899",
            hair: `<path d="M19 22 Q19 15 23 14 L41 14 Q45 15 45 22 Q43 17 39 16 L25 16 Q21 17 19 22 Z" fill="#6b3a1f"/><path d="M18.5 14 Q20 8 32 8 Q45 8 45.5 13 Q45.5 16 40 15 Q30 13.5 22 15 Q18.5 15.5 18.5 14 Z" fill="#ec4899"/><circle cx="34" cy="8" r="1.5" fill="#ec4899"/>`,
            collar: `<path d="M25 35 L39 35 L36 40 L28 40 Z" fill="#db2777"/>`,
            accessory: `<line x1="51.5" y1="44" x2="49.5" y2="58" stroke="#78350f" stroke-width="1.2"/><line x1="56.5" y1="44" x2="58.5" y2="58" stroke="#78350f" stroke-width="1.2"/><rect x="48.5" y="45" width="11" height="8.5" rx="0.6" fill="#f8fafc" stroke="#ec4899" stroke-width="0.9"/><path d="M51 51 L54 48 L57 51" stroke="#ec4899" stroke-width="0.8" fill="none"/>`
        });
    } else if (key === "translator" || key === "traducteur" || key === "linguiste" || key === "sofia") {
        return character({
            skin: "#ecc0a0", skinShade: "#d3a37f",
            jacket: "#e8eef6", jacketShade: "rgba(0,0,0,0.10)", pants: "#1e293b", shoes: "#3b82f6", accent: "#3b82f6",
            hair: `<path d="M18.5 24 Q18 8 32 7.5 Q46 8 45.5 24 Q44 14 38 12 Q32 9 26 12 Q20 14 18.5 24 Z" fill="#2563eb"/><path d="M18.5 22 L19.5 30 L22 30 L21.5 21 Z" fill="#1d4ed8"/><path d="M45.5 22 L44.5 30 L42 30 L42.5 21 Z" fill="#1d4ed8"/>`,
            face: `<path d="M18.5 20 Q32 6 45.5 20" stroke="#1d4ed8" stroke-width="2" fill="none"/><rect x="16.8" y="19" width="3.2" height="7" rx="1.6" fill="#1d4ed8"/><rect x="44" y="19" width="3.2" height="7" rx="1.6" fill="#1d4ed8"/><path d="M20 25 Q24 29 28.5 28.5" stroke="#1d4ed8" stroke-width="0.9" fill="none"/><circle cx="29" cy="28.5" r="1.2" fill="#1d4ed8"/>`,
            accessory: `<circle cx="54" cy="48" r="5.5" fill="rgba(59,130,246,0.12)" stroke="#3b82f6" stroke-width="1"/><ellipse cx="54" cy="48" rx="2.3" ry="5.5" fill="none" stroke="#3b82f6" stroke-width="0.6"/><line x1="48.5" y1="48" x2="59.5" y2="48" stroke="#3b82f6" stroke-width="0.6"/>`
        });
    } else if (key === "correcteur" || key === "critique" || key === "critic" || key === "manager_gold") {
        return character({
            skin: "#dcab82", skinShade: "#c4915f",
            jacket: "#2a3344", pants: "#1f2937", shoes: "#eab308", accent: "#eab308",
            hair: `<path d="M19 21 Q19 9 32 9 Q45 9 45 21 Q43 13 37 12 Q32 10 27 12 Q21 13 19 21 Z" fill="#2b2b33"/><path d="M24 9 L27 4 L32 7 L37 4 L40 9 Z" fill="#eab308" stroke="#fbbf24" stroke-width="0.5"/><circle cx="27" cy="4.2" r="0.9" fill="#fde68a"/><circle cx="32" cy="6.6" r="0.9" fill="#fde68a"/><circle cx="37" cy="4.2" r="0.9" fill="#fde68a"/>`,
            face: `<rect x="24" y="20.5" width="6" height="4" rx="1" fill="none" stroke="#eab308" stroke-width="0.9"/><rect x="34" y="20.5" width="6" height="4" rx="1" fill="none" stroke="#eab308" stroke-width="0.9"/><line x1="30" y1="22.2" x2="34" y2="22.2" stroke="#eab308" stroke-width="0.9"/>`,
            collar: `<path d="M27 35 L37 35 L32 40 Z" fill="#ffffff"/><path d="M30.8 36.5 L33.2 36.5 L32 45 Z" fill="#eab308"/>`,
            accessory: `<circle cx="53" cy="46" r="4.5" fill="rgba(234,179,8,0.12)" stroke="#eab308" stroke-width="1.2"/><line x1="56.3" y1="49.3" x2="60" y2="54" stroke="#eab308" stroke-width="1.8" stroke-linecap="round"/>`
        });
    } else if (key === "communitymanager" || key === "influenceur" || key === "artist_pink" || key === "artiste") {
        return character({
            skin: "#e7b48d", skinShade: "#cd9568",
            jacket: "#16161f", pants: "#be185d", shoes: "#ff007f", accent: "#ff007f",
            hair: `<path d="M18.8 22 Q18 8 32 7.5 Q46 8 45.2 22 Q43 13 37 11.5 Q32 9 27 11.5 Q21 13 18.8 22 Z" fill="#1f1822"/>`,
            face: `<path d="M18.5 20 Q32 6 45.5 20" stroke="#ff007f" stroke-width="2" fill="none"/><rect x="16.8" y="19" width="3.2" height="7" rx="1.6" fill="#ff007f"/><rect x="44" y="19" width="3.2" height="7" rx="1.6" fill="#ff007f"/>`,
            collar: `<path d="M26 35 L38 35 L34 40 L30 40 Z" fill="#ff007f" opacity="0.85"/>`,
            chest: `<path d="M32 49 C30 46.8 28.4 45.8 28.4 44.1 C28.4 43 29.2 42.2 30.2 42.2 C30.9 42.2 31.6 42.6 32 43.3 C32.4 42.6 33.1 42.2 33.8 42.2 C34.8 42.2 35.6 43 35.6 44.1 C35.6 45.8 34 46.8 32 49 Z" fill="#ff007f"/>`,
            accessory: `<path d="M54 44.5 C53 43.4 52.2 42.9 52.2 42 C52.2 41.4 52.6 41 53.1 41 C53.5 41 53.8 41.2 54 41.6 C54.2 41.2 54.5 41 54.9 41 C55.4 41 55.8 41.4 55.8 42 C55.8 42.9 55 43.4 54 44.5 Z" fill="#ff007f"/><circle cx="57" cy="50" r="2.3" fill="none" stroke="#ff007f" stroke-width="0.9"/><path d="M55.7 50 L56.7 51.2 L58.4 49" stroke="#ff007f" stroke-width="0.9" fill="none" stroke-linecap="round"/>`
        });
    } else if (key === "support_green" || key === "support" || key === "helpdesk") {
        return character({
            skin: "#e7b489", skinShade: "#cd9568",
            jacket: "#064e3b", jacketShade: "rgba(0,0,0,0.18)", pants: "#1f2937", shoes: "#22c55e", accent: "#22c55e",
            hair: `<path d="M19 21 Q19 9 32 9 Q45 9 45 21 Q43 13 37 11.5 Q32 9.5 27 11.5 Q21 13 19 21 Z" fill="#4b3a26"/>`,
            collar: `<path d="M27 35 L37 35 L32 40 Z" fill="#22c55e" opacity="0.85"/>`,
            accessory: `<path d="M18 22 Q18 8 32 8 Q46 8 46 22" stroke="#22c55e" stroke-width="1.7" fill="none"/><rect x="15.6" y="20" width="4.4" height="6.4" rx="2.2" fill="#16a34a"/><rect x="44" y="20" width="4.4" height="6.4" rx="2.2" fill="#16a34a"/><path d="M17.8 26 Q16 31 24 31" stroke="#22c55e" stroke-width="1.2" fill="none"/><circle cx="24.5" cy="31" r="1.4" fill="#22c55e"/>`
        });
    } else if (key === "scientist_blue" || key === "scientifique" || key === "data" || key === "chercheur") {
        return character({
            skin: "#ecc0a0", skinShade: "#d3a37f",
            jacket: "#eef3f8", jacketShade: "rgba(0,0,0,0.09)", pants: "#1e293b", shoes: "#0ea5e9", accent: "#0ea5e9",
            hair: `<path d="M18.8 22 Q18 8 32 7.5 Q46 8 45.2 22 Q43 13 37 11 Q32 9 27 11 Q21 13 18.8 22 Z" fill="#3b2f2a"/>`,
            face: `<circle cx="27.6" cy="22.2" r="3" fill="rgba(14,165,233,0.10)" stroke="#0ea5e9" stroke-width="0.9"/><circle cx="36.4" cy="22.2" r="3" fill="rgba(14,165,233,0.10)" stroke="#0ea5e9" stroke-width="0.9"/><line x1="30.6" y1="22.2" x2="33.4" y2="22.2" stroke="#0ea5e9" stroke-width="0.9"/>`,
            collar: `<path d="M26 35 L38 35 L34 41 L30 41 Z" fill="#cbd5e1"/><path d="M30.8 36 L33.2 36 L32 44 Z" fill="#0ea5e9"/>`,
            accessory: `<path d="M52 44 L52 47 L49 54 Q49 56 51 56 L57 56 Q59 56 59 54 L56 47 L56 44 Z" fill="rgba(14,165,233,0.22)" stroke="#0ea5e9" stroke-width="1"/><path d="M50.2 51.5 L57.8 51.5 L56 47 L52 47 Z" fill="#0ea5e9" opacity="0.55"/><circle cx="53" cy="49.5" r="0.7" fill="#bae6fd"/><circle cx="55.4" cy="50.6" r="0.5" fill="#bae6fd"/><rect x="51.6" y="42.6" width="4.8" height="1.8" rx="0.7" fill="#94a3b8"/>`
        });
    } else if (key === "agent_dark" || key === "agent_secret" || key === "securite" || key === "sécurité" || key === "security") {
        return character({
            skin: "#d79e6e", skinShade: "#bd8456",
            jacket: "#0b0f17", jacketShade: "rgba(0,0,0,0.22)", pants: "#0b0f17", shoes: "#1f2937", accent: "#94a3b8",
            hair: `<path d="M19 20 Q19 9 32 9 Q45 9 45 20 Q43 13 37 11.5 Q32 9.5 27 11.5 Q21 13 19 20 Z" fill="#15161c"/>`,
            face: `<path d="M22 20.5 L31 20.5 Q32 20.5 32 21.5 L32 22 Q32 24.8 30 24.8 L25 24.8 Q22.6 24.8 22 22.6 Z" fill="#0b1220" stroke="#334155" stroke-width="0.5"/><path d="M42 20.5 L33 20.5 Q32 20.5 32 21.5 L32 22 Q32 24.8 34 24.8 L39 24.8 Q41.4 24.8 42 22.6 Z" fill="#0b1220" stroke="#334155" stroke-width="0.5"/><line x1="24" y1="21.6" x2="27" y2="21.6" stroke="#475569" stroke-width="0.6" opacity="0.7"/>`,
            collar: `<path d="M27 35 L37 35 L32 41 Z" fill="#ffffff"/><path d="M30.7 36 L33.3 36 L32.6 45 L31.4 45 Z" fill="#b91c1c"/>`,
            accessory: `<path d="M44 23 Q48.5 24 47.2 30.5" stroke="#cbd5e1" stroke-width="1" fill="none"/><circle cx="44.4" cy="22.6" r="1.5" fill="#cbd5e1"/>`
        });
    } else if (key === "wizard_purple" || key === "mage" || key === "mystique" || key === "wizard") {
        return character({
            skin: "#ecc0a0", skinShade: "#d3a37f",
            jacket: "#4c1d95", jacketShade: "rgba(0,0,0,0.20)", pants: "#2e1065", shoes: "#7c3aed", accent: "#c4b5fd",
            hair: `<path d="M32 1 L20.5 16 L43.5 16 Z" fill="#5b21b6" stroke="#7c3aed" stroke-width="0.6"/><path d="M32 1 L43.5 16 L37 16 Z" fill="rgba(0,0,0,0.18)"/><ellipse cx="32" cy="16" rx="14.5" ry="3" fill="#5b21b6"/><path d="M31 3 L33.6 0.5 L31.5 5 Z" fill="#fbbf24"/><circle cx="27.5" cy="9" r="0.8" fill="#fde68a"/><circle cx="36" cy="7" r="0.8" fill="#fde68a"/>`,
            face: `<path d="M24.5 26 Q25.5 37 32 39 Q38.5 37 39.5 26 Q36 30.5 32 30.5 Q28 30.5 24.5 26 Z" fill="#eef2f7"/><path d="M27.5 25.5 Q32 28.5 36.5 25.5" stroke="#dfe5ec" stroke-width="1.4" fill="none" stroke-linecap="round"/>`,
            accessory: `<line x1="55" y1="34" x2="52.6" y2="60" stroke="#78350f" stroke-width="1.7" stroke-linecap="round"/><circle cx="55.6" cy="32.5" r="3.6" fill="rgba(196,181,253,0.32)" stroke="#c4b5fd" stroke-width="1"/><circle cx="55.6" cy="32.5" r="1.2" fill="#ede9fe"/><path d="M50 38 L51 36 L51.6 38 L53.6 38.6 L51.6 39.2 L51 41 L50.4 39.2 L48.4 38.6 Z" fill="#c4b5fd" opacity="0.8"/>`
        });
    } else if (key === "cyber_neko" || key === "neko" || key === "chat" || key === "cat") {
        return character({
            skin: "#ecc0a0", skinShade: "#d3a37f",
            jacket: "#1f1530", jacketShade: "rgba(0,0,0,0.22)", pants: "#3b2f52", shoes: "#22d3ee", accent: "#22d3ee",
            hair: `<path d="M19 22 Q18 9 32 8 Q46 9 45 22 Q43 13 37 11 Q32 9 27 11 Q21 13 19 22 Z" fill="#2a2140"/><path d="M21.5 12 L19 3.5 L27.5 9 Z" fill="#2a2140" stroke="#22d3ee" stroke-width="0.6"/><path d="M22.5 11 L21 6 L25.5 9 Z" fill="#f472b6"/><path d="M42.5 12 L45 3.5 L36.5 9 Z" fill="#2a2140" stroke="#22d3ee" stroke-width="0.6"/><path d="M41.5 11 L43 6 L38.5 9 Z" fill="#f472b6"/>`,
            face: `<path d="M30.4 25.6 L33.6 25.6 L32 27.8 Z" fill="#f472b6"/><line x1="19.5" y1="24.6" x2="27" y2="25.8" stroke="#cbd5e1" stroke-width="0.5"/><line x1="19.5" y1="27" x2="27" y2="27.4" stroke="#cbd5e1" stroke-width="0.5"/><line x1="44.5" y1="24.6" x2="37" y2="25.8" stroke="#cbd5e1" stroke-width="0.5"/><line x1="44.5" y1="27" x2="37" y2="27.4" stroke="#cbd5e1" stroke-width="0.5"/>`,
            accessory: `<path d="M45 59 Q57 57 57 47 Q57 41 52.5 41.5" stroke="#2a2140" stroke-width="3.6" fill="none" stroke-linecap="round"/><path d="M45 59 Q57 57 57 47 Q57 41 52.5 41.5" stroke="#22d3ee" stroke-width="1" fill="none" stroke-linecap="round" opacity="0.55"/>`
        });
    } else if (key === "astronaut_white" || key === "astronaute" || key === "spationaute" || key === "explorateur") {
        return character({
            skin: "#e7b489", skinShade: "#cd9568",
            jacket: "#e8edf3", jacketShade: "rgba(0,0,0,0.08)", pants: "#cbd5e1", shoes: "#94a3b8", accent: "#f97316",
            hair: ``,
            chest: `<rect x="26.5" y="43.5" width="11" height="7.5" rx="1.5" fill="#0b1220" stroke="#f97316" stroke-width="0.8"/><circle cx="29" cy="46" r="0.9" fill="#22c55e"/><circle cx="32" cy="46" r="0.9" fill="#f97316"/><circle cx="35" cy="46" r="0.9" fill="#ef4444"/><rect x="28" y="48.6" width="8" height="1.4" rx="0.7" fill="#38bdf8" opacity="0.6"/>`,
            collar: `<path d="M26 35 L38 35 L38 38 L26 38 Z" fill="#f97316" opacity="0.85"/>`,
            accessory: `<rect x="16.5" y="8.5" width="31" height="28" rx="14" fill="rgba(148,163,184,0.16)" stroke="#cbd5e1" stroke-width="1.5"/><path d="M21 14 Q26 11 31 11.5" stroke="#ffffff" stroke-width="1.4" fill="none" opacity="0.7" stroke-linecap="round"/><rect x="44.5" y="18" width="3.5" height="9" rx="1.6" fill="#94a3b8"/><rect x="16" y="18" width="3.5" height="9" rx="1.6" fill="#94a3b8"/>`
        });
    } else if (key === "cyber_ninja" || key === "ninja" || key === "infiltration") {
        return character({
            skin: "#d79e6e", skinShade: "#bd8456",
            jacket: "#111827", jacketShade: "rgba(0,0,0,0.26)", pants: "#0b0f17", shoes: "#ef4444", accent: "#ef4444",
            hair: `<path d="M17 27 Q15 8 32 7 Q49 8 47 27 Q47 16 40 12 Q32 8 24 12 Q17 16 17 27 Z" fill="#0b0f17"/>`,
            face: `<path d="M19.5 24 L44.5 24 L43.5 31 Q32 37.5 20.5 31 Z" fill="#111827"/><rect x="22.5" y="20" width="19" height="3.4" rx="1.7" fill="rgba(239,68,68,0.14)" stroke="#ef4444" stroke-width="0.7"/><rect x="17" y="16.5" width="30" height="3.4" rx="1" fill="#0b0f17"/>`,
            accessory: `<line x1="48" y1="58" x2="58.5" y2="29" stroke="#cbd5e1" stroke-width="1.6" stroke-linecap="round"/><line x1="45.5" y1="62" x2="50.5" y2="48" stroke="#1f2937" stroke-width="2.4" stroke-linecap="round"/><line x1="47.6" y1="51.5" x2="53.6" y2="53.6" stroke="#ef4444" stroke-width="1"/>`
        });
    } else if (key === "athena" || key === "athéna") {
        // Déesse Athéna revisitée : casque doré à crête, lance et bouclier (palette du logo).
        return character({
            skin: "#f1cba1", skinShade: "#d9ab78",
            jacket: "#173b63", jacketShade: "rgba(0,0,0,0.20)", pants: "#0f2742", shoes: "#d4af37", accent: "#d4af37",
            hair: `<path d="M18.5 23 Q18 12 32 11 Q46 12 45.5 23 Q44 15 40 19 L40 30 Q36 25 32 25 Q28 25 24 30 L24 19 Q20 15 18.5 23 Z" fill="#6b4f2a"/>`
                + `<path d="M19.3 14.5 Q20 9.5 32 9.5 Q44 9.5 44.7 14.5 Q44.7 17 41 16 Q32 13.5 23 16 Q19.3 17 19.3 14.5 Z" fill="#d4af37" stroke="#b8860b" stroke-width="0.6"/>`
                + `<rect x="19.5" y="13.5" width="25" height="2.6" rx="1.3" fill="#b8860b" opacity="0.55"/>`
                + `<path d="M27.5 10 Q32 -1.5 36.5 10 Z" fill="#1f6f8b"/><path d="M29.5 10 Q32 1 34.5 10 Z" fill="#7fd3ff"/>`,
            face: `<path d="M25.4 18.4 Q27.6 17.4 29.6 18.6" stroke="#caa46a" stroke-width="0.8" fill="none" stroke-linecap="round"/>`
                + `<path d="M34.4 18.6 Q36.4 17.4 38.6 18.4" stroke="#caa46a" stroke-width="0.8" fill="none" stroke-linecap="round"/>`,
            collar: `<path d="M26 35 L38 35 L34 41 L30 41 Z" fill="#d4af37" opacity="0.9"/>`,
            chest: `<circle cx="32" cy="46" r="3.2" fill="none" stroke="#7fd3ff" stroke-width="1"/><circle cx="32" cy="46" r="1" fill="#d4af37"/>`,
            accessory: `<line x1="51" y1="33" x2="49" y2="62" stroke="#d4af37" stroke-width="1.9" stroke-linecap="round"/>`
                + `<path d="M47.6 30 L51.4 31.2 L49 35.5 Z" fill="#f0d860"/>`
                + `<path d="M13.5 41 Q8.5 43.5 8.5 49 Q8.5 54.5 13.5 56.5 Q18.5 54.5 18.5 49 Q18.5 43.5 13.5 41 Z" fill="#173b63" stroke="#7fd3ff" stroke-width="1"/>`
                + `<path d="M13.5 44.5 V53 M10.5 49 H16.5" stroke="#7fd3ff" stroke-width="0.9" stroke-linecap="round"/>`
        });
    }

    // Fallback par défaut : robot/IA épuré.
    return character({
        skin: "#cbd5e1", skinShade: "#94a3b8",
        jacket: "#334155", pants: "#1e293b", shoes: "#38bdf8", accent: "#38bdf8",
        hair: `<rect x="22" y="9" width="20" height="4" rx="2" fill="#38bdf8" opacity="0.7"/>`,
        face: `<rect x="24" y="19.5" width="16" height="6" rx="3" fill="#0b1220" stroke="#38bdf8" stroke-width="0.9"/><circle cx="29" cy="22.5" r="1.3" fill="#38bdf8"/><circle cx="35" cy="22.5" r="1.3" fill="#38bdf8"/>`
    });
}

// SIMULATION DE VIE ET DE MOUVEMENT DE L'ESSAIM
let officeWanderingInterval = null;
const agentBreakStates = {}; // Suivi de l'état de break des agents

function getAgentWorkingStatus(agentName) {
    switch(agentName) {
        case "Jarvis": return "Supervise l'essaim... 🤖";
        case "Codeur": return "Optimise le code source... 💻";
        case "Auteur": return "Écrit le prochain best-seller... ✍️";
        case "Correcteur": return "Chasse les fautes de frappe... 🔍";
        case "Traducteur": return "Localise les écrits... 🌐";
        case "CommunityManager": return "Prépare les campagnes... 🚀";
        default: return "En veille active... ⚡";
    }
}

function startOfficeWandering() {
    if (officeWanderingInterval) clearInterval(officeWanderingInterval);
    
    officeWanderingInterval = setInterval(() => {
        // Ne choisir qu'un agent inactif au hasard pour simuler une action
        const idleAgents = agentsConfig.filter(a => a.name !== currentActiveAgent);
        if (idleAgents.length === 0) return;
        
        const agent = idleAgents[Math.floor(Math.random() * idleAgents.length)];
        const deskEl = document.getElementById(`desk-${agent.name}`);
        if (!deskEl) return;
        
        const bubble = document.getElementById(`bubble-${agent.name}`);
        const isOnBreak = agentBreakStates[agent.name] || false;
        
        deskEl.classList.add("walking");
        
        if (isOnBreak) {
            // L'agent termine sa pause et retourne à son bureau
            const index = agentsConfig.findIndex(a => a.name === agent.name);
            const defaultPos = getAgentPosition(agent.name, index);
            
            if (bubble) bubble.textContent = "Retourne à son poste... 🚶";
            deskEl.style.top = defaultPos.top;
            deskEl.style.left = defaultPos.left;
            
            agentBreakStates[agent.name] = false;
            
            setTimeout(() => {
                deskEl.classList.remove("walking");
                if (bubble) {
                    bubble.textContent = getAgentWorkingStatus(agent.name);
                }
            }, 4000);
        } else {
            // L'agent décide de faire une pause dans un lieu de détente
            const destinations = [
                { name: "Prend un café... ☕", top: "42%", left: "16%" },
                { name: "Joue au ping-pong ! 🏓", top: "84%", left: "48%" },
                { name: "Se détend dans le lounge 🛋️", top: "32%", left: "22%" },
                { name: "Réfléchit dans la salle de réunion 🧠", top: "16%", left: "48%" }
            ];
            
            const dest = destinations[Math.floor(Math.random() * destinations.length)];
            if (bubble) bubble.textContent = `S'absente : ${dest.name.toLowerCase()} 🚶`;
            
            deskEl.style.top = dest.top;
            deskEl.style.left = dest.left;
            
            agentBreakStates[agent.name] = true;
            
            setTimeout(() => {
                deskEl.classList.remove("walking");
                if (bubble) bubble.textContent = dest.name;
            }, 4000);
        }
        
    }, 15000); // Exécuté toutes les 15 secondes
}

// Variables globales de caméra RTS pour le Bureau Virtuel
let officeZoomScale = 1.0;
let officeRotationDeg = 0;

function applyOfficeCameraTransform() {
    const floor = document.getElementById("office-floor");
    if (!floor) return;
    floor.style.transform = `scale(${officeZoomScale}) rotate(${officeRotationDeg}deg)`;
    
    // Effet "billboard" : tourner les personnages dans le sens opposé pour qu'ils restent droits
    document.querySelectorAll(".agent-desk-iso").forEach(d => {
        d.style.transform = `translate(-50%, -50%) rotate(${-officeRotationDeg}deg)`;
    });
}

function rebuildOfficeFloor() {
    const floor = document.getElementById("office-floor");
    if (!floor) return;
    floor.innerHTML = "";
    
    // Configurer le style de base du conteneur floor pour afficher l'image isométrique
    floor.style.backgroundImage = "url('office_background.png?v=' + new Date().getTime())";
    floor.style.backgroundSize = "cover";
    floor.style.backgroundPosition = "center";
    
    agentsConfig.forEach((agent, index) => {
        const pos = getAgentPosition(agent.name, index);
        
        const desk = document.createElement("div");
        desk.className = "agent-desk-iso";
        if (agent.name === currentActiveAgent) desk.classList.add("active");
        desk.id = `desk-${agent.name}`;
        desk.style.setProperty("--agent-color", getAgentColor(agent.name));
        desk.style.position = "absolute";
        desk.style.top = pos.top;
        desk.style.left = pos.left;
        
        desk.innerHTML = `
            <div class="iso-avatar-wrapper" style="position: relative; display: flex; flex-direction: column; align-items: center; cursor: pointer;">
                <!-- Bulle de statut -->
                <div class="desk-bubble-iso" id="bubble-${agent.name}" style="position: absolute; bottom: 100%; margin-bottom: 8px; background: rgba(10,15,30,0.9); border: 1px solid var(--agent-color, rgba(255,255,255,0.2)); color: #fff; font-size: 0.65rem; padding: 4px 8px; border-radius: 8px; white-space: nowrap; box-shadow: 0 4px 10px rgba(0,0,0,0.4); pointer-events: none; z-index: 10; transition: all 0.3s;">${agent.name === currentActiveAgent ? 'En plein travail... 💻⚡' : getAgentWorkingStatus(agent.name)}</div>
                
                <!-- Sprite Humain Libre (Debout directement sur le sol !) -->
                <div class="iso-sprite-container" style="position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 105px; width: 100px; transition: all 0.3s;">
                    ${getAgentSpriteSVG(agent.avatar_type || agent.name)}
                    
                    <!-- Ombre ovale floue sous ses pieds -->
                    <div class="sprite-shadow" style="width: 48px; height: 10px; background: rgba(0,0,0,0.45); border-radius: 50%; margin-top: -6px; filter: blur(2px); z-index: -1;"></div>
                    
                    <!-- Anneau de sélection RTS au sol (dashed, ne brille que si actif) -->
                    <div class="rts-selection-ring" style="position: absolute; bottom: -6px; width: 65px; height: 24px; border-radius: 50%; border: 2px dashed var(--agent-color, #00f0ff); box-shadow: 0 0 10px var(--agent-color, #00f0ff); opacity: ${agent.name === currentActiveAgent ? '1' : '0'}; transform: scale(1); transition: all 0.3s; z-index: -2;"></div>
                    
                    <!-- Indicateur de café au-dessus du personnage -->
                    ${agent.name === currentActiveAgent ? '<span class="iso-coffee-indicator" style="position: absolute; top: 0; right: 0; font-size: 0.8rem; background: rgba(0,0,0,0.65); border-radius: 50%; padding: 2px; z-index: 10;">☕</span>' : ''}
                </div>
                
                <!-- Badge de Nom -->
                <div class="iso-name-badge" style="margin-top: 4px; background: rgba(0,0,0,0.85); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 2px 6px; font-size: 0.65rem; font-weight: bold; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.8); display: flex; flex-direction: column; align-items: center; gap: 1px; pointer-events: none;">
                    <span>${agent.display_name || agent.name}</span>
                    <span style="font-size: 0.5rem; color: rgba(255,255,255,0.5);">${(agent.display_name && agent.display_name !== agent.name) ? agent.name + ' • ' : ''}${agent.model}</span>
                </div>
            </div>
        `;
        
        desk.addEventListener("click", () => {
            setActiveAgentVisual(agent.name);
            logToTerminal(`Focus sur l'agent : ${agent.name}`, "system");
        });
        
        floor.appendChild(desk);
    });
    
    // Appliquer la transformation de caméra actuelle (Zoom / Rotation)
    applyOfficeCameraTransform();
    
    // Démarrer la boucle de déplacement
    startOfficeWandering();
}

// =========================================================================
// LOGIQUE DE COMMUNICATON CHAT & ESSAIM
// =========================================================================
function logToTerminal(text, type = "system", isHtml = false) {
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    
    // Si c'est du stdout, stderr ou raw, on n'affiche pas l'horodatage pour faire vrai terminal
    const prefix = (type === "stdout" || type === "stderr" || type === "raw") ? "" : `[${new Date().toLocaleTimeString()}] `;
    
    if (isHtml) {
        line.innerHTML = `${prefix}${text}`;
    } else {
        line.textContent = `${prefix}${text}`;
    }
    
    logsTerminal.appendChild(line);
    logsTerminal.scrollTop = logsTerminal.scrollHeight;
}

function logToOrchestrator(text, type = "system", isHtml = false) {
    if (!logsOrchestrator) return;
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    const prefix = `[${new Date().toLocaleTimeString()}] `;
    if (isHtml) {
        line.innerHTML = `${prefix}${text}`;
    } else {
        line.textContent = `${prefix}${text}`;
    }
    logsOrchestrator.appendChild(line);
    logsOrchestrator.scrollTop = logsOrchestrator.scrollHeight;
}

function setActiveAgentVisual(agentName) {
    currentActiveAgent = agentName;
    
    // Graphe
    document.querySelectorAll(".agent-node").forEach(n => n.classList.remove("active"));
    const node = document.getElementById(`node-${agentName}`);
    if (node) node.classList.add("active");
    
    // Open Space Rendu Isométrique
    document.querySelectorAll(".agent-desk-iso").forEach(d => {
        d.classList.remove("active");
        
        // Masquer l'anneau RTS au sol et l'icône café
        const ring = d.querySelector(".rts-selection-ring");
        if (ring) ring.style.opacity = "0";
        
        const coffee = d.querySelector(".iso-coffee-indicator");
        if (coffee) coffee.remove();
        
        const name = d.id.replace("desk-", "");
        if (name !== agentName) {
            const bubble = document.getElementById(`bubble-${name}`);
            if (bubble) bubble.textContent = "Prend une pause... ☕";
        }
    });
    
    const desk = document.getElementById(`desk-${agentName}`);
    if (desk) {
        desk.classList.add("active");
        
        // Activer le cercle au sol
        const ring = desk.querySelector(".rts-selection-ring");
        if (ring) ring.style.opacity = "1";
        
        // Ajouter l'icône café active
        const spriteContainer = desk.querySelector(".iso-sprite-container");
        if (spriteContainer && !desk.querySelector(".iso-coffee-indicator")) {
            const coffeeSpan = document.createElement("span");
            coffeeSpan.className = "iso-coffee-indicator";
            coffeeSpan.style.cssText = "position: absolute; top: 0; right: 0; font-size: 0.8rem; background: rgba(0,0,0,0.65); border-radius: 50%; padding: 2px; z-index: 10;";
            coffeeSpan.innerText = "☕";
            spriteContainer.appendChild(coffeeSpan);
        }
        
        // Le forcer à revenir immédiatement à son poste de travail attitré si il se baladait !
        const index = agentsConfig.findIndex(a => a.name === agentName);
        const defaultPos = getAgentPosition(agentName, index);
        
        desk.classList.add("walking");
        desk.style.top = defaultPos.top;
        desk.style.left = defaultPos.left;
        
        const bubble = document.getElementById(`bubble-${agentName}`);
        if (bubble) bubble.textContent = "Se concentre... 🧠";
        
        setTimeout(() => {
            desk.classList.remove("walking");
            if (bubble) bubble.textContent = "Au travail ! 💻";
        }, 4000);
    }
    
    // Bannière centrale & Fiche Active Agent
    const agentObj = agentsConfig.find(a => a.name === agentName);
    const dispName = agentObj && agentObj.display_name ? agentObj.display_name : agentName;
    const color = getAgentColor(agentName);
    
    // Mettre à jour l'avatar, le titre et le statut de la conversation active (panneau de droite)
    const activeChatAvatar = document.getElementById("active-chat-avatar");
    if (activeChatAvatar && typeof getAgentSpriteSVG === "function") {
        activeChatAvatar.innerHTML = getAgentSpriteSVG(agentObj ? (agentObj.avatar_type || agentObj.name) : agentName);
        const svg = activeChatAvatar.querySelector("svg");
        if (svg) {
            svg.style.width = "30px";
            svg.style.height = "30px";
        }
    }
    
    const ring = document.querySelector(".avatar-glow-ring");
    if (ring) {
        ring.style.borderColor = color;
        ring.style.boxShadow = `0 0 12px ${color}`;
    }
    
    const statusMap = {
        "Jarvis": "superviser • actif",
        "Codeur": "écrit le code • streaming",
        "Auteur": "compose un post • actif",
        "Chef": "coordonne l'équipe • actif",
        "Correcteur": "analyse le code • actif",
        "Traducteur": "traduit le texte • actif"
    };
    
    const activeChatStatus = document.getElementById("active-chat-status");
    if (activeChatStatus) {
        activeChatStatus.innerText = statusMap[agentName] || "expert • actif";
    }
    
    if (activeAgentTitle) {
        activeAgentTitle.textContent = dispName;
    }
    if (pulseIndicator) {
        pulseIndicator.style.backgroundColor = color;
        pulseIndicator.style.boxShadow = `0 0 12px ${color}`;
    }
    
    // Mettre à jour les statistiques de quotas et d'occupation en temps réel dans le header
    const occupiedCount = 1;
    const pausedCount = Math.max(0, agentsConfig.length - occupiedCount);
    
    const topOccupied = document.getElementById("top-occupied-count");
    const topPaused = document.getElementById("top-paused-count");
    if (topOccupied) topOccupied.innerText = occupiedCount;
    if (topPaused) topPaused.innerText = pausedCount;
    
    const topAgentCount = document.getElementById("top-agent-count");
    if (topAgentCount) topAgentCount.innerText = agentsConfig.length;
    
    const topAgentLimit = document.getElementById("top-agent-limit");
    if (topAgentLimit) topAgentLimit.innerText = `${agentsConfig.length}/8`;
}

// Faire voler une enveloppe de courrier physique d'un bureau à un autre
function animateHandoffMail(fromAgent, toAgent) {
    const fromDesk = document.getElementById(`desk-${fromAgent}`);
    const toDesk = document.getElementById(`desk-${toAgent}`);
    
    if (!fromDesk || !toDesk || viewOffice.style.display === "none") return;
    
    // Obtenir les coordonnées physiques absolues
    const fromRect = fromDesk.getBoundingClientRect();
    const toRect = toDesk.getBoundingClientRect();
    
    const color = (typeof getAgentColor === "function") ? getAgentColor(fromAgent) : "#00f0ff";
    const startX = fromRect.left + fromRect.width / 2;
    const startY = fromRect.top + fromRect.height / 2;
    const dx = (toRect.left + toRect.width / 2) - startX;
    const dy = (toRect.top + toRect.height / 2) - startY;

    const mail = document.createElement("div");
    mail.className = "flying-mail";
    mail.innerHTML = "✉️";
    mail.style.setProperty("--mail-color", color);
    mail.style.left = `${startX}px`;
    mail.style.top = `${startY}px`;

    const label = document.createElement("div");
    label.className = "flying-mail-label";
    label.textContent = "DÉLÉGATION";
    label.style.setProperty("--mail-color", color);
    label.style.left = `${startX}px`;
    label.style.top = `${startY + 20}px`;

    document.body.appendChild(mail);
    document.body.appendChild(label);

    // Lancer la transition CSS au frame suivant
    requestAnimationFrame(() => {
        mail.style.transform = `translate(${dx}px, ${dy}px) scale(1.4)`;
        label.style.transform = `translate(${dx}px, ${dy}px)`;
        setTimeout(() => {
            mail.style.opacity = "0";
            label.style.opacity = "0";
            setTimeout(() => { mail.remove(); label.remove(); }, 500);
        }, 1100);
    });
}

// Jouer pas à pas la séquence d'événements de l'essaim
// --- Plan d'action visible (planification explicite) ---
let currentPlanEl = null;
const _PLAN_ICONS = { pending: "⬜", in_progress: "🔄", done: "✅", failed: "❌" };

const _PLAN_CYCLE = ["pending", "in_progress", "done", "failed"];

// Persiste une opération de plan côté serveur puis recharge l'affichage.
async function _planOp(body) {
    try {
        await apiFetch("/api/plan/step", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_id: chatClientId, ...body }),
        });
        await reloadPlan();
    } catch (e) { console.error("plan op", e); }
}

async function reloadPlan() {
    if (!currentPlanEl) return;
    try {
        const r = await apiFetch(`/api/plan?client_id=${encodeURIComponent(chatClientId)}`);
        const data = await r.json();
        _fillPlan(currentPlanEl, data.items || []);
    } catch (e) { /* silencieux */ }
}

// (Re)construit le contenu d'un bloc plan ÉDITABLE.
function _fillPlan(el, items) {
    el.innerHTML = "";
    const title = document.createElement("div");
    title.style.cssText = "font-weight:700;color:var(--accent-cyan);font-size:0.8rem;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;";
    title.innerHTML = `<span>🗺️ Plan d'action</span><span style="font-weight:400;opacity:0.6;font-size:0.7rem;">modifiable</span>`;
    el.appendChild(title);
    (items || []).forEach((it, i) => {
        const row = document.createElement("div");
        row.className = "plan-item";
        row.dataset.index = i;
        row.style.cssText = "display:flex;gap:8px;align-items:center;font-size:0.8rem;padding:2px 0;";
        const ic = document.createElement("span");
        ic.className = "plan-icon";
        ic.style.cssText = "cursor:pointer;user-select:none;";
        ic.title = "Cliquer pour changer le statut";
        ic.textContent = _PLAN_ICONS[it.status] || "⬜";
        ic.onclick = () => {
            const next = _PLAN_CYCLE[(_PLAN_CYCLE.indexOf(it.status) + 1) % _PLAN_CYCLE.length] || "done";
            _planOp({ op: "set_status", index: i, status: next });
        };
        const tx = document.createElement("span");
        tx.className = "plan-text";
        tx.style.cssText = "flex:1;" + (it.status === "done" ? "opacity:0.6;text-decoration:line-through;" : "");
        tx.textContent = it.text;
        const edit = document.createElement("span");
        edit.textContent = "✎"; edit.style.cssText = "cursor:pointer;opacity:0.5;";
        edit.title = "Éditer";
        edit.onclick = () => {
            const v = prompt("Modifier l'étape :", it.text);
            if (v && v.trim()) _planOp({ op: "edit", index: i, text: v.trim() });
        };
        const del = document.createElement("span");
        del.textContent = "✕"; del.style.cssText = "cursor:pointer;opacity:0.5;";
        del.title = "Supprimer";
        del.onclick = () => { _planOp({ op: "delete", index: i }); };
        row.append(ic, tx, edit, del);
        el.appendChild(row);
    });
    const add = document.createElement("div");
    add.textContent = "＋ Ajouter une étape";
    add.style.cssText = "cursor:pointer;color:var(--accent-cyan);opacity:0.7;font-size:0.75rem;margin-top:6px;";
    add.onclick = () => {
        const v = prompt("Nouvelle étape :");
        if (v && v.trim()) _planOp({ op: "add", text: v.trim() });
    };
    el.appendChild(add);
}

function renderPlan(items) {
    const container = document.getElementById("chat-messages");
    if (!container) return;
    const el = document.createElement("div");
    el.className = "swarm-plan animate-fade-in";
    el.style.cssText = "background:rgba(0,243,255,0.06);border:1px solid rgba(0,243,255,0.3);border-radius:10px;padding:10px 14px;margin:8px 0;";
    _fillPlan(el, items);
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
    currentPlanEl = el;
}

function updatePlanStep(index, status) {
    if (!currentPlanEl) return;
    const row = currentPlanEl.querySelector(`.plan-item[data-index="${index}"]`);
    if (!row) return;
    const ic = row.querySelector(".plan-icon");
    if (ic) ic.textContent = _PLAN_ICONS[status] || "⬜";
    if (status === "done") {
        const tx = row.querySelector(".plan-text");
        if (tx) tx.style.opacity = "0.6";
    }
}

async function playAgentSteps(steps, immediate = false) {
    return new Promise(resolve => {
        let delay = 0;
        
        document.querySelectorAll(".link-line").forEach(l => l.classList.remove("active-flow"));
        
        steps.forEach((step, idx) => {
            setTimeout(() => {
                if (step.type === "activation") {
                    setActiveAgentVisual(step.agent);
                    logToOrchestrator(`${step.agent} prend la main.`, "system");
                }
                
                else if (step.type === "tool_call") {
                    logToOrchestrator(`${step.agent} exécute '${step.tool}'...`, "tool");
                    
                    // Statut dans sa bulle open space
                    const bubble = document.getElementById(`bubble-${step.agent}`);
                    if (bubble) bubble.textContent = `Utilise l'outil : ${step.tool}... ⚙️`;
                    
                    // Support spécialisé pour la consultation d'agent en arrière-plan (query_agent ou delegate_to_)
                    let targetAgent = null;
                    if (step.tool === "query_agent" && step.args && step.args.agent_name) {
                        targetAgent = step.args.agent_name;
                    } else if (step.tool.startsWith("delegate_to_")) {
                        targetAgent = step.tool.replace("delegate_to_", "");
                    }
                    
                    if (targetAgent) {
                        // Activer le spécialiste visuellement pour montrer qu'il travaille
                        setActiveAgentVisual(targetAgent);
                        
                        // Modifier la bulle du spécialiste pour dire qu'il travaille sur sa tâche
                        const targetBubble = document.getElementById(`bubble-${targetAgent}`);
                        if (targetBubble) {
                            targetBubble.textContent = "Reçoit la demande et se met au travail... ⚙️💻";
                        }
                        logToOrchestrator(`[Coopération] ${targetAgent} commence à travailler en arrière-plan... 🛠️`, "system");
                    }
                    
                    // Allumer la ligne du graphe s'il s'agit d'un transfert
                    if (step.tool.startsWith("transfer_to_") || step.tool.startsWith("delegate_to_")) {
                        const target = step.tool.startsWith("transfer_to_") ? step.tool.replace("transfer_to_", "") : step.tool.replace("delegate_to_", "");
                        const link = document.getElementById(`link-${step.agent}-${target}`) || 
                                     document.getElementById(`link-${target}-${step.agent}`);
                        if (link) {
                            link.style.setProperty("--active-color", getAgentColor(step.agent));
                            link.classList.add("active-flow");
                        }
                    }
                }
                
                else if (step.type === "tool_output") {
                    logToOrchestrator(`${step.output.substring(0, 120)}`, "success");
                    
                    // Support spécialisé pour la fin de consultation d'agent en arrière-plan
                    const prevStep = steps.slice(0, idx).reverse().find(s => s.type === "tool_call");
                    if (prevStep) {
                        let targetAgentOut = null;
                        if (prevStep.tool === "query_agent" && prevStep.args && prevStep.args.agent_name) {
                            targetAgentOut = prevStep.args.agent_name;
                        } else if (prevStep.tool.startsWith("delegate_to_")) {
                            targetAgentOut = prevStep.tool.replace("delegate_to_", "");
                        }
                        
                        if (targetAgentOut) {
                            const targetBubble = document.getElementById(`bubble-${targetAgentOut}`);
                            if (targetBubble) {
                                targetBubble.textContent = "A terminé son travail et renvoie ses résultats ! ✅";
                            }
                            logToOrchestrator(`[Coopération] ${targetAgentOut} a renvoyé ses résultats avec succès !`, "success");
                        }
                    }
                    
                    // Jarvis vient de créer/mettre à jour un agent → rafraîchir l'effectif
                    // (openspace, graphe et liste des réglages lisent le cache agentsConfig).
                    if (prevStep && prevStep.tool === "create_agent" &&
                        typeof step.output === "string" && step.output.startsWith("Agent")) {
                        logToOrchestrator("Nouvel agent intégré à l'essaim — rafraîchissement de l'effectif…", "success");
                        if (typeof reloadSwarmConfig === "function") reloadSwarmConfig();
                    }

                    const bubble = document.getElementById(`bubble-${step.agent}`);
                    if (bubble) bubble.textContent = "Interprète le résultat... 📊";
                }

                else if (step.type === "handoff") {
                    logToOrchestrator(`Passage de relais : ${step.from} ➔ ${step.to}`, "transition");
                    if (typeof pushNotification === "function") {
                        pushNotification("Relais", `${step.from} ➔ ${step.to}`, "warning");
                    }
                    
                    // Bulle open space
                    const bubble = document.getElementById(`bubble-${step.from}`);
                    if (bubble) bubble.textContent = `Envoie ses dossiers à ${step.to}... 📨`;
                    
                    // Lancer l'enveloppe volante dans le bureau
                    animateHandoffMail(step.from, step.to);
                    
                    // Ajouter le log de coordination rose fluo au milieu du chat
                    const handoffMsg = document.createElement("div");
                    handoffMsg.className = "swarm-coordination-log animate-fade-in";
                    handoffMsg.innerText = `${step.from.toUpperCase()} ➔ ${step.to.toUpperCase()} • DELEGATION`;
                    chatMessages.appendChild(handoffMsg);
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                    
                    // Éteindre le flux après un moment
                    setTimeout(() => {
                        const link = document.getElementById(`link-${step.from}-${step.to}`) ||
                                     document.getElementById(`link-${step.to}-${step.from}`);
                        if (link) link.classList.remove("active-flow");
                    }, 1000);
                }
                
                else if (step.type === "terminal_output_direct") {
                    const lines = step.output.split("\n");
                    const streamType = step.stream === "stderr" ? "stderr" : "stdout";
                    lines.forEach(l => {
                        logToTerminal(l, streamType);
                    });
                }

                else if (step.type === "plan") {
                    renderPlan(step.items || []);
                }

                else if (step.type === "plan_update") {
                    updatePlanStep(step.index, step.status);
                }

                else if (step.type === "skill_learned") {
                    logToOrchestrator(`🧠 Nouvelle compétence acquise : « ${step.name} » — ${step.description || ""}`, "success");
                    if (typeof pushNotification === "function") {
                        pushNotification("Compétence acquise", `${step.agent} a appris « ${step.name} »`, "success");
                    }
                }

                else if (step.type === "critic") {
                    logToOrchestrator(`🔎 Relecture critique : réponse révisée (${(step.issues || "").split("\n")[0]})`, "system");
                }

                else if (step.type === "skill_improved") {
                    logToOrchestrator(`🔧 Compétence « ${step.name} » réparée automatiquement.`, "success");
                }

                else if (step.type === "profile_updated") {
                    logToOrchestrator(`👤 Profil utilisateur mis à jour.`, "system");
                }

                else if (step.type === "thought") {
                    // Narration interne avant un outil : log discret, pas de bulle de chat.
                    logToOrchestrator(`💭 ${step.agent} : ${(step.content || "").slice(0, 120)}`, "system");
                }

                else if (step.type === "message" || step.type === "terminal_message") {
                    if (step.type === "terminal_message") {
                        // Afficher le message directement dans la console interactive avec rendu Markdown HTML
                        let htmlContent = step.content;
                        if (window.marked && typeof window.marked.parse === "function") {
                            htmlContent = window.marked.parse(step.content);
                        }
                        logToTerminal(htmlContent, "success", true);
                    } else {
                        appendAgentMessage(step.agent, step.content);
                    }
                    const bubble = document.getElementById(`bubble-${step.agent}`);
                    if (bubble) bubble.textContent = "Explique sa réponse à l'utilisateur. 💬";
                    if (isVoiceTtsEnabled) {
                        speakText(step.content, step.agent);
                    }
                }
                
                if (idx === steps.length - 1) {
                    setTimeout(resolve, immediate ? 0 : 300);
                }
            }, delay);

            // Timing dégressif pour l'animation séquentielle cinéma (désactivé en mode
            // immédiat : streaming SSE, où chaque étape arrive déjà au fil de l'eau).
            if (!immediate) {
                if (step.type === "handoff") delay += 800;
                else if (step.type === "activation") delay += 300;
                else if (step.type === "tool_call") delay += 500;
                else if (step.type === "tool_output") delay += 200;
                else if (step.type === "message" || step.type === "terminal_message" || step.type === "terminal_output_direct") delay += 150;
                else if (step.type === "plan") delay += 400;
                else if (step.type === "plan_update") delay += 150;
            }
        });
        
        if (steps.length === 0) resolve();
    });
}

// Rendu Markdown inline léger (gras, italique, code, liens) — sans dépendance externe.
// Échappe le HTML pour neutraliser toute injection (XSS) avant d'appliquer le markdown.
// Le contenu d'un message peut contenir du HTML hostile (saisi par l'utilisateur, ou
// rapporté par un agent depuis une page web/un document) → on l'échappe SYSTÉMATIQUEMENT.
function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

// --- Artifacts : prévisualisation de code en bac à sable ISOLÉ ------------
// Le code généré (HTML/JS/React) tourne dans un <iframe sandbox="allow-scripts">
// SANS allow-same-origin → origine opaque : il ne peut PAS lire le token, le
// localStorage ni le DOM parent. C'est la barrière de sécurité.
const ARTIFACTS = [];

function _artifactKind(lang, code) {
    const l = (lang || "").toLowerCase();
    const c = code || "";
    if (["jsx", "tsx", "react"].includes(l)) return "react";
    if (["html", "htm", "xml", "svg"].includes(l)) return "html";
    if (/<!DOCTYPE html|<html[\s>]|<body[\s>]|<svg[\s>]/i.test(c)) return "html";
    // JS seul : prévisualisable seulement s'il manipule le DOM.
    if (["js", "javascript"].includes(l) && /document\.|window\.|createElement|innerHTML/.test(c)) return "js";
    return null;
}

function _htmlTemplate(code) {
    if (/<html[\s>]/i.test(code)) return code;
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui;margin:12px;}</style></head><body>${code}</body></html>`;
}

function _jsTemplate(code) {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>body{font-family:system-ui;margin:12px;}</style></head><body><div id="app"></div><script>${code}<\/script></body></html>`;
}

function _reactTemplate(code) {
    return `<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://unpkg.com/react@18/umd/react.production.min.js"><\/script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"><\/script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"><\/script>
<style>body{font-family:system-ui;margin:12px;}</style></head>
<body><div id="root"></div>
<script type="text/babel" data-presets="react">
${code}
try { if (typeof App !== "undefined") ReactDOM.createRoot(document.getElementById("root")).render(<App />); } catch(e) { document.getElementById("root").textContent = e.message; }
<\/script></body></html>`;
}

function openArtifact(i) {
    const a = ARTIFACTS[i];
    if (!a) return;
    const overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    const card = document.createElement("div");
    card.style.cssText = "background:#fff;width:90vw;height:85vh;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 10px 40px rgba(0,0,0,0.5);";
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:6px 12px;background:#111;color:#fff;font-size:0.78rem;";
    const label = document.createElement("span");
    label.textContent = `👁️ Aperçu (${a.kind}) — bac à sable isolé`;
    const close = document.createElement("button");
    close.textContent = "✕ Fermer";
    close.style.cssText = "background:none;border:1px solid #555;color:#fff;cursor:pointer;border-radius:6px;padding:2px 8px;";
    close.onclick = () => overlay.remove();
    bar.append(label, close);
    const iframe = document.createElement("iframe");
    iframe.setAttribute("sandbox", "allow-scripts");
    iframe.setAttribute("referrerpolicy", "no-referrer");
    iframe.style.cssText = "flex:1;border:none;width:100%;background:#fff;";
    iframe.srcdoc = a.kind === "react" ? _reactTemplate(a.code)
                  : a.kind === "js" ? _jsTemplate(a.code)
                  : _htmlTemplate(a.code);
    card.append(bar, iframe);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
}

// Retire les balises d'émotion vocale ([emotion: …], (ton: …)) pour qu'elles
// n'apparaissent jamais dans le texte affiché (elles ne servent qu'au TTS).
function _stripEmotionTags(s) {
    return String(s == null ? "" : s)
        .replace(/[\[(]\s*(?:emotion|émotion|ton|tone|style)\s*[:=]\s*[^\])]+?\s*[\])]/gi, "")
        .replace(/[ \t]{2,}/g, " ")
        .trimStart();
}

// URL sûre pour un attribut src/href : http(s) ou chemin interne /api/... uniquement.
function _safeUrl(u) {
    u = String(u || "").trim();
    if (/^https?:\/\//i.test(u) || /^\/[\w./?=&%-]*$/.test(u)) {
        return u.replace(/["'<>]/g, encodeURIComponent);
    }
    return "#";
}

// Carte image cliquable, SANS onclick inline interpolé : l'URL/alt passent par des
// attributs data- (contexte attribut HTML, neutralisé par escapeHtml) et l'ouverture
// se fait par délégation d'événement (cf. listener plus bas).
function _imageCardHtml(url, alt) {
    const su = escapeHtml(_safeUrl(url));
    const sa = escapeHtml(alt || "");
    return `
        <div class="chat-generated-image-card animate-zoom-in" style="display: block; margin-top: 10px;" data-img-url="${su}" data-img-alt="${sa}">
            <img src="${su}" alt="${sa}" class="chat-zoomable-image" />
            <div class="chat-image-overlay">
                <span>🖼️ ${sa}</span>
                <span>🔍 Cliquer pour agrandir</span>
            </div>
        </div>`;
}

// Ouverture des images du chat par DÉLÉGATION (plus d'onclick inline interpolé).
if (!window.__imgCardDelegation) {
    window.__imgCardDelegation = true;
    document.addEventListener("click", (e) => {
        const card = e.target.closest && e.target.closest(".chat-generated-image-card");
        if (card && card.dataset && card.dataset.imgUrl) {
            openLightbox(card.dataset.imgUrl, card.dataset.imgAlt || "");
        }
    });
}

function _mdInline(s) {
    // NB: s est déjà échappé en HTML ; le markdown ne réintroduit que des balises sûres.
    s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[\s(>])\*([^*\n]+?)\*(?=[\s).,!?:;]|<|$)/g, '$1<em>$2</em>');
    // Le libellé du lien est déjà échappé ; l'URL est restreinte à http(s).
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s"']+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return s;
}

function appendAgentMessage(agentName, content, id = null) {
    if (!content) return;
    
    const msg = document.createElement("div");
    msg.className = `message agent-msg agent-${agentName} animate-fade-in`;
    if (id) msg.setAttribute("data-msg-id", id);
    
    // Rendu SÛR : on extrait du contenu BRUT les blocs de code et les images (en
    // construisant un HTML sûr), on échappe TOUT le reste, puis on réinsère.
    let raw = _stripEmotionTags(String(content));
    const codeBlocks = [];
    raw = raw.replace(/```(?:[a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (m, code) => {
        codeBlocks.push(`<pre><code>${escapeHtml(code)}</code></pre>`);
        return ` CODE${codeBlocks.length - 1} `;
    });
    // Détection d'artifacts prévisualisables (HTML/JS/React) — bouton « Aperçu ».
    const artifactIdx = [];
    String(content).replace(/```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g, (mm, lang, code) => {
        const kind = _artifactKind(lang, code);
        if (kind) artifactIdx.push(ARTIFACTS.push({ code, kind }) - 1);
        return mm;
    });
    const blocks = [];
    raw = raw.replace(/!\[(.*?)\]\((.*?)\)/g, (m, alt, url) => {
        blocks.push(_imageCardHtml(url, alt));
        return ` BLK${blocks.length - 1} `;
    });

    let formattedContent = escapeHtml(raw);
    formattedContent = _mdInline(formattedContent);
    formattedContent = formattedContent.replace(/\n/g, "<br>");
    formattedContent = formattedContent
        .replace(/ CODE(\d+) /g, (m, i) => codeBlocks[+i])
        .replace(/ BLK(\d+) /g, (m, i) => blocks[+i]);

    // Détection automatique des fichiers d'images générées bruts (image_generee_xxxx.png)
    const imgRegex = /image_generee_\d+\.png/gi;
    const foundImages = [...new Set(content.match(imgRegex) || [])];

    let imagesHtml = "";
    if (foundImages.length > 0) {
        foundImages.forEach(filename => {
            // Éviter le doublon si déjà rendu par le parser markdown
            if (!formattedContent.includes("chat-generated-image-card") || !formattedContent.includes(filename)) {
                imagesHtml += _imageCardHtml(`/api/workspace/download?path=${encodeURIComponent(filename)}`, filename);
            }
        });
    }

    let actionsHtml = "";
    const artifactBtns = artifactIdx.map(i =>
        `<button class="btn-artifact" onclick="openArtifact(${i})">👁️ Aperçu</button>`).join("");
    if (id || artifactBtns) {
        actionsHtml = `
        <div class="message-actions">
            ${artifactBtns}
            ${id ? `<button class="btn-fork-here" onclick="forkConversation('${escapeHtml(id)}')">🌿 Brancher d'ici</button>` : ""}
        </div>`;
    }

    msg.innerHTML = `
        <div class="message-meta">
            <span class="agent-tag" style="color: ${getAgentColor(agentName)}">${escapeHtml(agentName)}</span>
        </div>
        <div class="message-content">${formattedContent}${imagesHtml}</div>
        ${actionsHtml}
    `;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendUserMessage(content, id = null) {
    const msg = document.createElement("div");
    msg.className = "message user-msg animate-fade-in";
    if (id) msg.setAttribute("data-msg-id", id);
    
    let actionsHtml = "";
    if (id) {
        actionsHtml = `
        <div class="message-actions">
            <button class="btn-fork-here" onclick="forkConversation('${escapeHtml(id)}')">🌿 Brancher d'ici</button>
        </div>`;
    }

    msg.innerHTML = `
        <div class="message-meta" style="color: var(--color-user)">Vous</div>
        <div class="message-content">${escapeHtml(content).replace(/\n/g, "<br>")}</div>
        ${actionsHtml}
    `;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

let currentChatTree = { messages: [], active_node_id: null };

async function reloadChatHistory(redrawChat = true) {
    try {
        const response = await apiFetch("/api/chat/tree");
        if (!response.ok) return;
        currentChatTree = await response.json();
        
        // Mettre à jour l'affichage de l'agent actif
        if (currentChatTree.active_agent) {
            setActiveAgentVisual(currentChatTree.active_agent);
        }
        
        const messages = currentChatTree.messages;
        const activeNodeId = currentChatTree.active_node_id;
        
        const nodeMap = {};
        messages.forEach(m => { nodeMap[m.id] = m; });
        
        const activeChain = [];
        let currId = activeNodeId;
        while (currId) {
            const node = nodeMap[currId];
            if (!node) break;
            activeChain.unshift(node);
            currId = node.parent_id;
        }
        
        if (redrawChat) {
            chatMessages.innerHTML = "";
            
            if (activeChain.length === 0) {
                const orch = orchestratorAgent();
                const intro = (orch && orch.welcome_message)
                    ? orch.welcome_message
                    : `Bonjour, je suis ${orchestratorName()}. Comment puis-je vous aider aujourd'hui ?`;
                chatMessages.innerHTML = `
                    <div class="message system-msg glass animate-fade-in">
                        <div class="message-content">
                            <strong>Système :</strong> ${intro}
                        </div>
                    </div>
                `;
            } else {
                activeChain.forEach(msg => {
                    if (msg.role === "user") {
                        if (msg.content && msg.content.startsWith("[Relais système")) {
                            // Extraire le nom de l'agent si possible
                            // Format: [Relais système : La demande a été transférée à l'agent Jarvis (Jarvis). Veuillez répondre à l'utilisateur.]
                            const match = msg.content.match(/transférée à l'agent (.*?)(?:\s|$|\.|\()/);
                            let label = "PASSAGE DE RELAIS";
                            if (match && match[1]) {
                                label = `RELAIS VERS ${match[1].toUpperCase()}`;
                            }
                            const handoffMsg = document.createElement("div");
                            handoffMsg.className = "swarm-coordination-log animate-fade-in";
                            handoffMsg.innerText = label;
                            if (msg.id) handoffMsg.setAttribute("data-msg-id", msg.id);
                            chatMessages.appendChild(handoffMsg);
                        } else {
                            appendUserMessage(msg.content, msg.id);
                        }
                    } else if (msg.role === "assistant") {
                        const agentName = msg.name || orchestratorName();
                        appendAgentMessage(agentName, msg.content, msg.id);
                    }
                });
            }
        }
        
        rebuildBranchesTreeView();
        
    } catch (err) {
        console.error("Erreur de chargement de l'historique:", err);
    }
}

async function forkConversation(messageId) {
    if (!confirm("Voulez-vous repositionner la conversation sur ce message et forker à partir d'ici ?")) return;
    
    try {
        const response = await apiFetch("/api/chat/fork", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message_id: messageId })
        });
        
        if (response.ok) {
            logToTerminal("Branchement réussi ! Fil de discussion repositionné.", "system");
            await reloadChatHistory(true);
        } else {
            const data = await response.json();
            alert("Erreur de branchement: " + data.detail);
        }
    } catch (err) {
        logToTerminal("Erreur de connexion lors du forking: " + err, "error");
    }
}

function rebuildBranchesTreeView() {
    const container = document.getElementById("branches-tree-container");
    if (!container) return;
    container.innerHTML = "";
    
    const messages = currentChatTree.messages;
    const activeNodeId = currentChatTree.active_node_id;
    
    if (messages.length === 0) {
        container.innerHTML = `<div style="text-align: center; opacity: 0.5; padding: 20px;">Aucun historique de branche pour le moment. Répondez au moins une fois !</div>`;
        return;
    }
    
    const childrenMap = {};
    const rootNodes = [];
    
    messages.forEach(msg => {
        const pId = msg.parent_id;
        if (!pId) {
            rootNodes.push(msg);
        } else {
            if (!childrenMap[pId]) {
                childrenMap[pId] = [];
            }
            childrenMap[pId].push(msg);
        }
    });
    
    function buildNodeHtml(msg) {
        const nodeDiv = document.createElement("div");
        nodeDiv.className = "tree-node";
        
        const isUser = msg.role === "user";
        const roleLabel = isUser ? "Vous" : (msg.name || orchestratorName());
        const roleClass = isUser ? "tree-role-user" : "tree-role-agent";
        const isActive = msg.id === activeNodeId;
        const activeClass = isActive ? "active" : "";
        
        const textPreview = msg.content ? msg.content.substring(0, 30) + (msg.content.length > 30 ? "..." : "") : "(vide)";
        
        nodeDiv.innerHTML = `
            <div class="tree-node-content ${activeClass}" onclick="selectTreeNode('${msg.id}')">
                <span class="tree-role-tag ${roleClass}">${roleLabel}</span>
                <span class="tree-text-preview" title="${msg.content || ''}">${textPreview}</span>
            </div>
        `;
        
        const children = childrenMap[msg.id] || [];
        if (children.length > 0) {
            children.forEach(child => {
                nodeDiv.appendChild(buildNodeHtml(child));
            });
        }
        
        return nodeDiv;
    }
    
    rootNodes.forEach(root => {
        container.appendChild(buildNodeHtml(root));
    });
}

async function selectTreeNode(messageId) {
    try {
        const response = await apiFetch("/api/chat/fork", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message_id: messageId })
        });
        
        if (response.ok) {
            logToTerminal(`Passage au nœud de conversation ${messageId}`, "system");
            await reloadChatHistory(true);
        } else {
            const data = await response.json();
            alert("Erreur lors de la sélection du nœud: " + data.detail);
        }
    } catch (err) {
        logToTerminal("Erreur de connexion: " + err, "error");
    }
}

window.forkConversation = forkConversation;
window.selectTreeNode = selectTreeNode;


// Charger la mémoire clé-valeur JSON
async function refreshMemory() {
    try {
        const response = await apiFetch("/api/memory");
        const data = await response.json();
        memoryGrid.innerHTML = "";
        const keys = Object.keys(data);
        if (keys.length === 0) {
            memoryGrid.innerHTML = '<div class="empty-memory">Aucun fait mémorisé.</div>';
            return;
        }
        keys.forEach(key => {
            const item = document.createElement("div");
            item.className = "memory-item";
            item.innerHTML = `
                <span class="memory-key">${key.replace(/_/g, ' ')}</span>
                <span class="memory-val">${data[key]}</span>
                <button class="memory-delete-btn" onclick="deleteMemoryFact('${key}')" title="Supprimer ce fait">×</button>
            `;
            memoryGrid.appendChild(item);
        });
    } catch (err) {
        console.error("Erreur de chargement mémoire:", err);
    }
}

async function deleteMemoryFact(key) {
    if (!confirm(`Voulez-vous vraiment supprimer le fait "${key.replace(/_/g, ' ')}" de la mémoire ?`)) return;
    try {
        const response = await apiFetch(`/api/memory/${key}`, { method: "DELETE" });
        if (response.ok) {
            refreshMemory();
            logToTerminal(`Fait mémorisé "${key}" supprimé avec succès.`, "success");
        } else {
            const data = await response.json();
            alert("Erreur lors de la suppression : " + data.detail);
        }
    } catch (err) {
        console.error("Erreur de suppression mémoire:", err);
    }
}
window.deleteMemoryFact = deleteMemoryFact;

// =========================================================================
// PIÈCES JOINTES DU CHAT (extraction de contenu injectée dans le message)
// =========================================================================
async function attachFileToMessage(file) {
    if (!file) return;
    try {
        logToTerminal(`Téléversement de « ${file.name} »…`, "system");
        const fd = new FormData();
        fd.append("file", file);
        const r = await apiFetch("/api/chat/attach", { method: "POST", body: fd });
        if (!r.ok) {
            const d = await r.json().catch(() => ({}));
            logToTerminal("Pièce jointe refusée : " + (d.detail || r.status), "error");
            return;
        }
        pendingChatAttachment = await r.json();
        renderAttachmentChip();
        logToTerminal(`📎 « ${pendingChatAttachment.filename} » jointe (${pendingChatAttachment.kind}${pendingChatAttachment.truncated ? ", tronquée" : ""}).`, "success");
    } catch (e) {
        logToTerminal("Erreur pièce jointe : " + e, "error");
    }
}

function renderAttachmentChip() {
    const pill = document.querySelector(".chat-input-pill");
    let chip = document.getElementById("chat-attachment-chip");
    if (!pendingChatAttachment) { if (chip) chip.remove(); return; }
    if (!pill) return;
    if (!chip) {
        chip = document.createElement("div");
        chip.id = "chat-attachment-chip";
        chip.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;font-size:0.75rem;background:rgba(0,243,255,0.1);border:1px solid rgba(0,243,255,0.3);border-radius:8px;padding:4px 10px;color:var(--accent-cyan);";
        pill.parentNode.insertBefore(chip, pill);
    }
    const a = pendingChatAttachment;
    chip.innerHTML = `<span>📎 ${a.filename} <span style="opacity:0.6;">(${a.kind}${a.truncated ? ", tronqué" : ""})</span></span>`;
    const x = document.createElement("button");
    x.type = "button";
    x.textContent = "✕";
    x.style.cssText = "background:none;border:none;color:#ff5b89;cursor:pointer;font-size:0.85rem;";
    x.addEventListener("click", () => { pendingChatAttachment = null; renderAttachmentChip(); });
    chip.appendChild(x);
}

// Soumettre un message dans le chat
// Annuler le dernier échange / Réessayer la dernière question.
const _btnChatUndo = document.getElementById("btn-chat-undo");
if (_btnChatUndo) _btnChatUndo.addEventListener("click", async () => {
    if (activeAbortController) return;
    try {
        const r = await apiFetch("/api/chat/undo", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_id: chatClientId })
        });
        const d = await r.json();
        if (d.removed_user == null) { logToTerminal("Rien à annuler.", "warning"); return; }
        // Redessin propre depuis l'arbre (re)calé côté serveur.
        await reloadChatHistory(true);
        logToTerminal("Dernier échange annulé.", "system");
    } catch (e) { logToTerminal("Annulation : " + e, "error"); }
});

const _btnChatRetry = document.getElementById("btn-chat-retry");
if (_btnChatRetry) _btnChatRetry.addEventListener("click", async () => {
    if (activeAbortController) return;
    try {
        const r = await apiFetch("/api/chat/retry", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ client_id: chatClientId })
        });
        const d = await r.json();
        if (!d.user) { logToTerminal("Rien à réessayer.", "warning"); return; }
        // L'arbre est déjà recalé côté serveur : on rejoue la question. C'est le flux
        // de submit qui redessine le chat à la fin (pas besoin de reload ici).
        chatInput.value = d.user;
        if (typeof chatForm.requestSubmit === "function") chatForm.requestSubmit();
        else chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    } catch (e) { logToTerminal("Réessai : " + e, "error"); }
});

chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    // Si une génération est déjà en cours, cliquer sur le bouton agit comme un bouton "Stop" !
    if (activeAbortController) {
        // Annulation côté serveur (le run s'arrête au prochain tour) + arrêt du flux.
        if (activeRunId) {
            apiFetch(`/api/runs/${activeRunId}/cancel`, { method: "POST" }).catch(() => {});
        }
        activeAbortController.abort();
        logToTerminal("Génération interrompue par l'utilisateur.", "warning");
        return;
    }
    
    let text = chatInput.value.trim();
    if (!text && !pendingChatAttachment) return;

    // Injecter la pièce jointe (contenu extrait) dans le message envoyé à l'essaim.
    if (pendingChatAttachment) {
        const a = pendingChatAttachment;
        const body = (a.text && a.text.trim()) ? a.text : (a.note || "(contenu non extrait)");
        const trunc = a.truncated ? `\n[...contenu tronqué — fichier complet: ${a.path} (utilise ingest_file pour tout indexer)]` : "";
        text = `[Pièce jointe « ${a.filename} » (${a.kind})]\n${body}${trunc}\n[fin de la pièce jointe]\n\n${text}`.trim();
        pendingChatAttachment = null;
        renderAttachmentChip();
    }

    chatInput.disabled = true;
    chatInput.value = "";
    chatInput.placeholder = "Génération en cours... Clique sur ⏹️ pour arrêter";
    
    // Remplacer l'icône du bouton d'envoi par un bouton Stop rouge ⏹️
    chatSendBtn.innerHTML = `
        <svg class="send-icon-svg" viewBox="0 0 24 24" style="color: #ff5555; width: 18px; height: 18px;">
            <rect x="4" y="4" width="16" height="16" fill="currentColor" rx="2"></rect>
        </svg>
    `;
    chatSendBtn.title = "Arrêter la génération";
    
    appendUserMessage(text);
    
    // Activer visuellement Jarvis immédiatement pendant le chargement en arrière-plan
    setActiveAgentVisual(orchestratorName());
    const jarvisBubble = document.getElementById("bubble-"+orchestratorName());
    if (jarvisBubble) {
        jarvisBubble.textContent = "Analyse de la demande et coordination de l'essaim... 🧠⚙️";
    }
    logToOrchestrator(orchestratorName() + " analyse votre demande et orchestre les agents spécialisés en arrière-plan...", "system");
    
    activeAbortController = new AbortController();
    activeRunId = null;

    try {
        // Streaming SSE : les étapes de l'essaim arrivent au fil de l'eau.
        const response = await apiFetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, client_id: chatClientId }),
            signal: activeAbortController.signal
        });

        if (!response.ok || !response.body) {
            const errData = await response.json().catch(() => ({}));
            logToTerminal("Erreur API: " + (errData.detail || response.status), "error");
        } else {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            let finished = false;
            while (!finished) {
                const { value, done } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                let sep;
                while ((sep = buf.indexOf("\n\n")) >= 0) {
                    const block = buf.slice(0, sep);
                    buf = buf.slice(sep + 2);
                    let ev = null, dataStr = null;
                    block.split("\n").forEach(line => {
                        if (line.startsWith("event:")) ev = line.slice(6).trim();
                        else if (line.startsWith("data:")) dataStr = line.slice(5).trim();
                    });
                    if (!dataStr) continue;
                    let payload;
                    try { payload = JSON.parse(dataStr); } catch (e) { continue; }
                    if (ev === "run") {
                        activeRunId = payload.run_id;
                    } else if (ev === "step") {
                        await playAgentSteps([payload], true);   // immédiat : pas de délai cinéma en streaming
                    } else if (ev === "error") {
                        logToTerminal("Erreur essaim: " + (payload.detail || ""), "error");
                    } else if (ev === "done") {
                        finished = true;
                    }
                }
            }
            // Finalisation : recharge l'historique canonique + télémétrie.
            await new Promise(r => setTimeout(r, 250));
            await reloadChatHistory(true);
            await loadConversations();
            await refreshMemory();
            if (typeof loadCockpitData === "function") {
                loadCockpitData();
                loadGalleryMedia();
            }
        }
    } catch (err) {
        if (err.name === 'AbortError') {
            logToTerminal("Génération interrompue avec succès.", "info");
        } else {
            logToTerminal("Erreur de connexion: " + err, "error");
        }
    } finally {
        activeAbortController = null;
        activeRunId = null;
        chatInput.disabled = false;
        chatInput.placeholder = "Parle à l'essaim...";
        
        // Rétablir l'icône d'envoi originale
        chatSendBtn.innerHTML = `
            <svg class="send-icon-svg" viewBox="0 0 24 24">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"></path>
            </svg>
        `;
        chatSendBtn.title = "Envoyer";
        chatInput.focus();
    }
});

// Réinitialiser la conversation
btnReset.addEventListener("click", async () => {
    if (confirm("Réinitialiser l'essaim et vider le fil de discussion ?")) {
        try {
            await apiFetch("/api/reset", { method: "POST" });
            await loadConversations();
            await reloadChatHistory(true);
            setActiveAgentVisual(orchestratorName());
            logToTerminal("Essaim réinitialisé.");
            document.querySelectorAll(".link-line").forEach(l => l.classList.remove("active-flow"));
        } catch (err) {
            logToTerminal("Erreur de réinitialisation: " + err, "error");
        }
    }
});

// =========================================================================
// MODALE PRINCIPALE DE CONFIGURATION NO-CODE (⚙️)
// =========================================================================
btnSettings.addEventListener("click", async () => {
    settingsModal.style.display = "flex";
    loadConfigAgentsPane();
    loadConfigEnvPane();
});

modalClose.addEventListener("click", () => {
    settingsModal.style.display = "none";
});

// Alternance entre les onglets de la modale paramètres
function switchModalTab(activeTab, activePaneFn) {
    [modalTabAgents, modalTabKeys, modalTabSsh, modalTabAgenda, modalTabPricing, modalTabBehavior, modalTabMcp, modalTabRoutines, modalTabKnowledge, modalTabUsers, modalTabSatellites, modalTabDoctor, modalTabMessaging].forEach(t => t && t.classList.remove("active"));
    [paneAgents, paneKeys, paneSsh, paneAgenda, panePricing, paneBehavior, paneMcp, paneRoutines, paneKnowledge, paneUsers, paneSatellites, paneDoctor, paneMessaging].forEach(p => p && (p.style.display = "none"));
    activeTab && activeTab.classList.add("active");
    activePaneFn();
}

modalTabAgents.addEventListener("click", () => switchModalTab(modalTabAgents, () => {
    paneAgents.style.display = "block";
}));

modalTabKeys.addEventListener("click", () => switchModalTab(modalTabKeys, () => {
    paneKeys.style.display = "block";
}));

if (modalTabSsh) {
    modalTabSsh.addEventListener("click", () => switchModalTab(modalTabSsh, () => {
        paneSsh.style.display = "block";
    }));
}

modalTabAgenda.addEventListener("click", () => switchModalTab(modalTabAgenda, () => {
    paneAgenda.style.display = "block";
    loadAgendaConfig();
}));

if (modalTabPricing && panePricing) {
    modalTabPricing.addEventListener("click", () => switchModalTab(modalTabPricing, () => {
        panePricing.style.display = "block";
        loadPricingConfig();
    }));
}

// -------------------------------------------------------------------------
// ONGLET : COMPORTEMENT & SÉCURITÉ (réglages data-driven, écrits dans .env)
// -------------------------------------------------------------------------
const BEHAVIOR_SCHEMA = [
    { section: "Exécution & garde-fous", fields: [
        { key: "SANDBOX_MODE", label: "Sandbox d'exécution de code/commandes", type: "select", options: [["docker", "Docker (isolé)"], ["off", "Local (NON isolé)"]], def: "docker" },
        { key: "SELF_IMPROVE", label: "Auto-amélioration (retours d'expérience)", type: "toggle", def: "true" },
        { key: "LLM_MAX_RETRIES", label: "Retries LLM sur erreur", type: "number", def: "2" },
        { key: "SWARM_MAX_PARALLEL", label: "Agents/outils en parallèle (max)", type: "number", def: "4" },
        { key: "SWARM_MAX_SECONDS", label: "Budget temps par requête (s, 0 = ∞)", type: "number", def: "0" },
        { key: "SWARM_MAX_TOKENS", label: "Budget tokens par requête (0 = ∞)", type: "number", def: "0" },
        { key: "BUDGET_DAILY_LIMIT", label: "Alerte si coût du jour dépasse (€, 0 = off)", type: "number", def: "0" },
    ]},
    { section: "Sécurité", fields: [
        { key: "AUTO_APPROVE_SENSITIVE", label: "Auto-approuver les outils sensibles (global)", type: "toggle", def: "false" },
        { key: "SENSITIVE_TOOLS", label: "Outils sensibles (CSV ; vide = défaut)", type: "text", def: "" },
        { key: "ADMIN_PASSWORD", label: "Mot de passe admin (réseau)", type: "password", def: "" },
        { key: "HOST", label: "Écoute : 127.0.0.1 (local) ou 0.0.0.0 (réseau)", type: "text", def: "0.0.0.0" },
        { key: "PORT", label: "Port", type: "number", def: "8000" },
        { key: "ALLOWED_ORIGINS", label: "Origines CORS autorisées (CSV ; vide = local)", type: "text", def: "" },
        { key: "SESSION_TTL_HOURS", label: "Durée de validité d'une session (heures)", type: "number", def: "168" },
        { key: "TELEGRAM_REQUIRE_PAIRING", label: "Exiger un pairage Telegram (DM)", type: "toggle", def: "true" },
        { key: "ACTIVE_WORKSPACE_DIR", label: "Dossier de travail (vide = workspace/)", type: "text", def: "" },
    ]},
    { section: "Orchestration & agents (avancé)", fields: [
        { key: "DELEGATION_ROUTER", label: "Aiguillage LLM vers le bon spécialiste", type: "toggle", def: "true" },
        { key: "FAST_MODEL", label: "Modèle rapide pour micro-décisions (vide = modèle de l'agent)", type: "text", def: "" },
        { key: "FALLBACK_MODELS", label: "Modèles de repli si échec (CSV)", type: "text", def: "" },
        { key: "AUTO_CRITIC", label: "Auto-critique des réponses", type: "toggle", def: "false" },
        { key: "USER_MODELING", label: "Profil utilisateur évolutif", type: "toggle", def: "true" },
        { key: "SELF_IMPROVE_SKILLS", label: "Induction/réparation auto de compétences", type: "toggle", def: "true" },
        { key: "TOOL_SCRIPTS", label: "Autoriser run_tool_script (enchaînement d'outils)", type: "toggle", def: "true" },
        { key: "PROMPT_CACHE", label: "Cache de prompt", type: "select", options: [["auto", "Auto (Anthropic)"], ["on", "Forcé"], ["off", "Désactivé"]], def: "auto" },
        { key: "EXPERIENCE_MAX", label: "Retours d'expérience conservés (max)", type: "number", def: "50" },
        { key: "DOC_MAX_CHUNKS", label: "Passages max analysés par document", type: "number", def: "60" },
    ]},
    { section: "Mémoire", fields: [
        { key: "MEMORY_MAX_MESSAGES", label: "Compaction au-delà de N messages (0 = off)", type: "number", def: "40" },
        { key: "MEMORY_KEEP_RECENT", label: "Messages récents gardés mot pour mot", type: "number", def: "12" },
    ]},
    { section: "Voix expressive", fields: [
        { key: "VOICE_EMOTION_TAGS", label: "Émotions vocales (le LLM colore sa voix)", type: "toggle", def: "false" },
        { key: "VOICE_TTS_HTTP_URL", label: "Serveur TTS expressif (URL, ex. XTTS/Chatterbox)", type: "text", def: "" },
        { key: "VOICE_TTS_VOICE", label: "Voix / locuteur du TTS expressif", type: "text", def: "" },
    ]},
    { section: "Présence / follow-me (optionnel)", fields: [
        { key: "PRESENCE_ENTITY", label: "Entité HA de pièce courante (vide = désactivé)", type: "text", def: "" },
    ]},
    { section: "Automatisation (n8n)", fields: [
        { key: "N8N_WORKFLOWS", label: "Workflows autorisés — JSON {\"nom\":\"url webhook\"}", type: "text", def: "" },
    ]},
];

async function loadConfigBehaviorPane() {
    const container = document.getElementById("behavior-fields");
    if (!container) return;
    let env = {};
    try { const r = await apiFetch("/api/config/env"); if (r.ok) env = await r.json(); } catch (e) {}
    container.innerHTML = "";
    BEHAVIOR_SCHEMA.forEach(group => {
        const h = document.createElement("h5");
        h.textContent = group.section;
        h.style.cssText = "margin: 10px 0 2px; color: var(--accent-cyan); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em;";
        container.appendChild(h);
        group.fields.forEach(f => {
            const has = env[f.key] !== undefined && env[f.key] !== "";
            const cur = has ? env[f.key] : f.def;
            const row = document.createElement("div");
            row.style.cssText = "display: flex; align-items: center; justify-content: space-between; gap: 12px;";
            let input;
            if (f.type === "toggle") {
                const on = String(cur).toLowerCase() === "true" || cur === "1";
                input = `<input type="checkbox" class="behavior-input" data-key="${f.key}" data-type="toggle" ${on ? "checked" : ""} style="width: 18px; height: 18px; cursor: pointer;">`;
            } else if (f.type === "select") {
                input = `<select class="behavior-input" data-key="${f.key}" data-type="select" style="max-width: 210px;">${f.options.map(([v, l]) => `<option value="${v}" ${String(cur) === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
            } else if (f.type === "password") {
                const ph = (env[f.key] && String(env[f.key]).includes("...")) ? "Défini (masqué) — vide = inchangé" : "Aucun (auth désactivée)";
                input = `<input type="password" class="behavior-input" data-key="${f.key}" data-type="password" placeholder="${ph}" style="max-width: 210px;">`;
            } else {
                input = `<input type="${f.type === "number" ? "number" : "text"}" class="behavior-input" data-key="${f.key}" data-type="${f.type}" value="${String(cur).replace(/"/g, "&quot;")}" style="max-width: 210px;">`;
            }
            row.innerHTML = `<label style="font-size: 0.8rem; flex: 1;">${f.label}</label>${input}`;
            container.appendChild(row);
        });
    });
}

async function saveConfigBehaviorPane() {
    const env = {};
    document.querySelectorAll("#behavior-fields .behavior-input").forEach(el => {
        const key = el.dataset.key, type = el.dataset.type;
        if (type === "toggle") env[key] = el.checked ? "true" : "false";
        else if (type === "password") { if (el.value) env[key] = el.value; }
        else env[key] = el.value;
    });
    const status = document.getElementById("behavior-save-status");
    try {
        const r = await apiFetch("/api/config/env", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ env }) });
        const d = await r.json().catch(() => ({}));
        if (status) status.textContent = r.ok ? ("✅ " + (d.message || "Sauvegardé")) : ("❌ " + (d.detail || "Erreur"));
    } catch (e) {
        if (status) status.textContent = "❌ " + e;
    }
}

if (modalTabBehavior && paneBehavior) {
    modalTabBehavior.addEventListener("click", () => switchModalTab(modalTabBehavior, () => {
        paneBehavior.style.display = "block";
        loadConfigBehaviorPane();
    }));
}
const _btnSaveBehavior = document.getElementById("btn-save-behavior");
if (_btnSaveBehavior) _btnSaveBehavior.addEventListener("click", saveConfigBehaviorPane);

// Sauvegarde / restauration de l'état (.zip)
const _btnBackupExport = document.getElementById("btn-backup-export");
if (_btnBackupExport) _btnBackupExport.addEventListener("click", async () => {
    const st = document.getElementById("backup-status");
    if (st) st.textContent = "⏳ Génération de l'archive…";
    try {
        const r = await apiFetch("/api/backup");
        if (!r.ok) { if (st) st.textContent = "❌ Erreur " + r.status; return; }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `jarvis-backup-${new Date().toISOString().slice(0, 10)}.zip`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
        if (st) st.textContent = "✅ Archive téléchargée.";
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});
const _btnBackupImport = document.getElementById("btn-backup-import");
const _backupFileInput = document.getElementById("backup-file-input");
if (_btnBackupImport && _backupFileInput) {
    _btnBackupImport.addEventListener("click", () => _backupFileInput.click());
    _backupFileInput.addEventListener("change", async () => {
        if (!_backupFileInput.files.length) return;
        if (!confirm("Restaurer cette archive ? L'état actuel (conversations, mémoire…) sera ÉCRASÉ.")) { _backupFileInput.value = ""; return; }
        const st = document.getElementById("backup-status");
        if (st) st.textContent = "⏳ Restauration…";
        const fd = new FormData();
        fd.append("file", _backupFileInput.files[0]);
        _backupFileInput.value = "";
        try {
            const r = await apiFetch("/api/backup/restore", { method: "POST", body: fd });
            const d = await r.json().catch(() => ({}));
            if (st) st.textContent = r.ok ? `✅ ${d.restored} fichiers restaurés. Redémarre le serveur.` : "❌ " + (d.detail || "Erreur");
        } catch (e) { if (st) st.textContent = "❌ " + e; }
    });
}

// -------------------------------------------------------------------------
// ONGLET : SERVEURS MCP
// -------------------------------------------------------------------------
// -------------------------------------------------------------------------
// ONGLET : SERVEURS MCP (Interface Graphique)
// -------------------------------------------------------------------------
let currentMcpPresets = [];
let mcpMarketplaceCatalogs = [];

async function loadConfigMcpPane() {
    const listEl = document.getElementById("mcp-servers-list");
    if (!listEl) return;
    
    try {
        const r = await apiFetch("/api/config/mcp/servers");
        if (r.ok) {
            const d = await r.json();
            currentMcpPresets = d.presets || [];
            renderMcpPresetsDropdown();
            renderMcpServersList(d.servers || [], d.tool_count || 0);
            loadMcpMarketplace();
        }
    } catch (e) {
        listEl.innerHTML = `<div style="color: #ff5555; padding: 10px;">❌ Erreur : ${e}</div>`;
    }
}

function renderMcpPresetsDropdown() {
    const sel = document.getElementById("mcp-presets");
    if (!sel) return;
    sel.innerHTML = `<option value="">-- Personnalisé --</option>`;
    currentMcpPresets.forEach((p, idx) => {
        sel.innerHTML += `<option value="${idx}">${p.label}</option>`;
    });
}

function renderMcpServersList(servers, totalTools) {
    const listEl = document.getElementById("mcp-servers-list");
    if (!listEl) return;
    
    if (servers.length === 0) {
        listEl.innerHTML = `<div style="text-align: center; opacity: 0.5; padding: 20px; font-size: 0.85rem;">Aucun serveur configuré. Ajoutez-en un !</div>`;
        return;
    }
    
    let html = `<div style="font-size: 0.8rem; margin-bottom: 8px; color: var(--accent-cyan);">${servers.length} serveur(s) configuré(s) - ${totalTools} outil(s) disponibles</div>`;
    
    servers.forEach(srv => {
        const statusClass = srv.disabled ? "mcp-status-disabled" : (srv.connected ? "mcp-status-online" : "mcp-status-offline");
        const statusText = srv.disabled ? "Désactivé" : (srv.connected ? "Connecté" : "Hors ligne / Erreur");
        
        html += `
            <div class="mcp-card">
                <div class="mcp-card-info">
                    <div class="mcp-card-title">
                        <span class="mcp-status-dot ${statusClass}" title="${statusText}"></span>
                        ${srv.name}
                    </div>
                    <div class="mcp-card-cmd">${srv.command} ${srv.args.join(" ")}</div>
                    ${srv.tools && srv.tools.length > 0 ? `<div class="mcp-card-tools">${srv.tools.length} outil(s) (ex: ${srv.tools.slice(0, 3).map(t => t.name).join(", ")}${srv.tools.length > 3 ? '...' : ''})</div>` : ''}
                </div>
                <button class="btn btn-secondary btn-mcp-edit" data-name="${srv.name}" style="padding: 4px 10px; font-size: 0.75rem;">⚙️ Modifier</button>
            </div>
        `;
    });
    
    listEl.innerHTML = html;
    
    document.querySelectorAll(".btn-mcp-edit").forEach(btn => {
        btn.onclick = () => {
            const srvName = btn.getAttribute("data-name");
            const srv = servers.find(s => s.name === srvName);
            if (srv) showMcpForm(srv);
        };
    });
}

function showMcpForm(serverData = null) {
    document.getElementById("mcp-form-container").style.display = "block";
    document.getElementById("mcp-save-status").textContent = "";
    
    const envList = document.getElementById("mcp-env-list");
    envList.innerHTML = "";
    
    if (serverData) {
        document.getElementById("mcp-form-title").textContent = "Modifier " + serverData.name;
        document.getElementById("mcp-name").value = serverData.name;
        document.getElementById("mcp-name").disabled = true; // Can't change name once created
        document.getElementById("mcp-command").value = serverData.command;
        document.getElementById("mcp-args").value = serverData.args.join(" ");
        document.getElementById("mcp-disabled").checked = serverData.disabled;
        
        document.getElementById("btn-mcp-delete").style.display = "block";
        document.getElementById("btn-mcp-delete").onclick = () => deleteMcpServer(serverData.name);
        
        Object.entries(serverData.env || {}).forEach(([k, v]) => addMcpEnvRow(k, v));
    } else {
        document.getElementById("mcp-form-title").textContent = "Ajouter un serveur";
        document.getElementById("mcp-name").value = "";
        document.getElementById("mcp-name").disabled = false;
        document.getElementById("mcp-command").value = "";
        document.getElementById("mcp-args").value = "";
        document.getElementById("mcp-disabled").checked = false;
        
        document.getElementById("btn-mcp-delete").style.display = "none";
        addMcpEnvRow("", ""); // Add one empty row
    }
}

function hideMcpForm() {
    document.getElementById("mcp-form-container").style.display = "none";
}

function addMcpEnvRow(key = "", val = "") {
    const list = document.getElementById("mcp-env-list");
    const div = document.createElement("div");
    div.className = "mcp-env-row";
    div.innerHTML = `
        <input type="text" class="env-k" placeholder="Clé (ex: TOKEN)" value="${key}" autocomplete="off">
        <input type="text" class="env-v" placeholder="Valeur" value="${val}" autocomplete="off">
        <button type="button" class="mcp-env-remove">✕</button>
    `;
    div.querySelector(".mcp-env-remove").onclick = () => div.remove();
    list.appendChild(div);
}

document.getElementById("btn-mcp-add-env")?.addEventListener("click", () => addMcpEnvRow("", ""));
document.getElementById("btn-mcp-add-new")?.addEventListener("click", () => {
    document.getElementById("mcp-presets").value = "";
    showMcpForm();
});
document.getElementById("btn-mcp-cancel")?.addEventListener("click", hideMcpForm);

document.getElementById("mcp-presets")?.addEventListener("change", (e) => {
    const preset = currentMcpPresets[e.target.value];
    if (preset) {
        document.getElementById("mcp-name").value = preset.name;
        document.getElementById("mcp-command").value = preset.command;
        document.getElementById("mcp-args").value = preset.args.join(" ");
        
        const envList = document.getElementById("mcp-env-list");
        envList.innerHTML = "";
        if (Object.keys(preset.env).length === 0) {
            addMcpEnvRow("", "");
        } else {
            Object.entries(preset.env).forEach(([k, v]) => addMcpEnvRow(k, v));
        }
    }
});

document.getElementById("btn-mcp-save")?.addEventListener("click", async () => {
    const st = document.getElementById("mcp-save-status");
    const name = document.getElementById("mcp-name").value.trim();
    if (!name) {
        st.innerHTML = `<span style="color:#ff5555">❌ Le nom est requis</span>`;
        return;
    }
    
    st.innerHTML = `⏳ Sauvegarde & reconnexion en cours…`;
    
    const envObj = {};
    document.querySelectorAll("#mcp-env-list .mcp-env-row").forEach(row => {
        const k = row.querySelector(".env-k").value.trim();
        const v = row.querySelector(".env-v").value.trim();
        if (k) envObj[k] = v;
    });
    
    const payload = {
        name: name,
        command: document.getElementById("mcp-command").value.trim(),
        args: document.getElementById("mcp-args").value.trim().split(" ").filter(s => s),
        env: envObj,
        disabled: document.getElementById("mcp-disabled").checked
    };
    
    try {
        const r = await apiFetch("/api/config/mcp/servers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok) {
            st.innerHTML = `✅ Sauvegardé`;
            setTimeout(() => { hideMcpForm(); loadConfigMcpPane(); }, 1000);
        } else {
            st.innerHTML = `<span style="color:#ff5555">❌ ${d.detail || "Erreur"}</span>`;
        }
    } catch (e) {
        st.innerHTML = `<span style="color:#ff5555">❌ ${e}</span>`;
    }
});

async function deleteMcpServer(name) {
    if (!confirm(`Supprimer définitivement le serveur MCP '${name}' ?`)) return;
    const st = document.getElementById("mcp-save-status");
    st.innerHTML = `⏳ Suppression en cours…`;
    
    try {
        const r = await apiFetch(`/api/config/mcp/servers/${name}`, { method: "DELETE" });
        if (r.ok) {
            hideMcpForm();
            loadConfigMcpPane();
        } else {
            st.innerHTML = `<span style="color:#ff5555">❌ Erreur lors de la suppression</span>`;
        }
    } catch (e) {
        st.innerHTML = `<span style="color:#ff5555">❌ ${e}</span>`;
    }
}

if (modalTabMcp && paneMcp) {
    modalTabMcp.addEventListener("click", () => switchModalTab(modalTabMcp, () => {
        paneMcp.style.display = "block";
        loadConfigMcpPane();
    }));
}

// -------------------------------------------------------------------------
// ONGLET : SATELLITES VOCAUX ESP32-S3 (ESPHome direct)
// -------------------------------------------------------------------------
function renderSatellitesStatus(status) {
    const el = document.getElementById("satellites-status");
    if (!el || !status) return;
    if (status.deps_ok === false) {
        const msg = (status.errors && (status.errors._deps || status.errors._init)) || "Dépendances vocales manquantes.";
        el.innerHTML = `<span style="color:#ff5b89;">⚠️ ${msg}</span>`;
        return;
    }
    const connected = status.connected || [];
    const errs = Object.entries(status.errors || {}).filter(([k]) => !k.startsWith("_"));
    let html = "";
    if (connected.length) {
        html += `<span style="color:var(--accent-cyan);">🟢 Connecté(s) : ${connected.join(", ")}</span>`;
    } else if (status.configured > 0) {
        html += `<span style="opacity:0.7;">⚪ Aucun satellite connecté pour l'instant.</span>`;
    } else {
        html += `<span style="opacity:0.5;">Aucun satellite configuré.</span>`;
    }
    if (errs.length) {
        html += errs.map(([n, e]) => `<div style="color:#ff5b89;font-size:0.72rem;">❌ ${n} : ${e}</div>`).join("");
    }
    el.innerHTML = html;
}

async function loadSatellitesPane() {
    const list = document.getElementById("satellites-list");
    if (!list) return;
    try {
        const r = await apiFetch("/api/config/satellites");
        const d = await r.json();
        renderSatellitesStatus(d.status);
        const sats = d.satellites || [];
        if (sats.length === 0) {
            list.innerHTML = `<div style="opacity:0.5;font-size:0.78rem;text-align:center;padding:8px;">Aucun satellite. Ajoutez-en un ci-dessous.</div>`;
            return;
        }
        const connected = (d.status && d.status.connected) || [];
        list.innerHTML = "";
        sats.forEach(s => {
            const isOn = connected.includes(s.name);
            const row = document.createElement("div");
            row.className = "service-item";
            row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 12px;";
            row.innerHTML = `
                <div style="min-width:0;">
                    <strong style="color:${isOn ? 'var(--accent-cyan)' : '#888'};">${isOn ? '🟢' : '⚪'} ${s.name}</strong>
                    <div style="font-size:0.7rem;opacity:0.7;">${s.host}:${s.port} · ${s.key_set ? '🔑 clé enregistrée' : '⚠️ pas de clé'}</div>
                </div>
                <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                    <button data-act="edit" title="Charger dans le formulaire" style="background:none;border:1px solid rgba(255,255,255,0.2);color:#fff;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:0.72rem;">✏️</button>
                    <button data-act="del" title="Supprimer" style="background:rgba(255,0,80,0.12);border:1px solid rgba(255,0,80,0.4);color:#ff5b89;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:0.72rem;">🗑️</button>
                </div>`;
            row.querySelector('[data-act="edit"]').addEventListener("click", () => {
                document.getElementById("sat-name").value = s.name;
                document.getElementById("sat-host").value = s.host;
                document.getElementById("sat-port").value = s.port;
                document.getElementById("sat-key").value = "";
                const am = document.getElementById("sat-activation-mode");
                const ww = document.getElementById("sat-wakeword");
                if (am && s.wake_mode) am.value = s.wake_mode;
                if (ww && s.wake_word) ww.value = s.wake_word;
                _syncSatActivation();
            });
            row.querySelector('[data-act="del"]').addEventListener("click", async () => {
                if (!confirm(`Supprimer le satellite « ${s.name} » ?`)) return;
                await apiFetch(`/api/config/satellites/${encodeURIComponent(s.name)}`, { method: "DELETE" });
                loadSatellitesPane();
            });
            list.appendChild(row);
        });
    } catch (e) {
        list.innerHTML = `<div style="color:#ff5b89;font-size:0.78rem;">Erreur : ${e}</div>`;
    }
}

async function saveSatelliteFromForm() {
    const st = document.getElementById("sat-save-status");
    const name = document.getElementById("sat-name").value.trim();
    const host = document.getElementById("sat-host").value.trim();
    if (!name || !host) { if (st) st.textContent = "❌ Nom et adresse IP requis."; return; }
    if (st) st.textContent = "⏳ Enregistrement & connexion…";
    try {
        const r = await apiFetch("/api/config/satellites", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name, host,
                port: parseInt(document.getElementById("sat-port").value || "6053", 10),
                encryption_key: document.getElementById("sat-key").value.trim(),
                wake_mode: (document.getElementById("sat-activation-mode") || {}).value || "embedded",
                wake_word: (document.getElementById("sat-wakeword") || {}).value || "hey_jarvis"
            })
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok) {
            if (st) st.textContent = "✅ Enregistré.";
            renderSatellitesStatus(d.satellites);
            document.getElementById("sat-key").value = "";
            loadSatellitesPane();
        } else {
            if (st) st.textContent = "❌ " + (d.detail || "Erreur");
        }
    } catch (e) { if (st) st.textContent = "❌ " + e; }
}

async function loadWakeWord() {
    try {
        const r = await apiFetch("/api/config/voice-wake");
        const d = await r.json();
        const eng = document.getElementById("wake-engine");
        const w = document.getElementById("wake-word");
        if (eng) eng.value = d.engine || "stt";
        if (w) w.value = d.word || "Athena";
    } catch (e) { /* ignore */ }
}
const _btnWakeSave = document.getElementById("btn-wake-save");
if (_btnWakeSave) _btnWakeSave.addEventListener("click", async () => {
    const st = document.getElementById("wake-save-status");
    const engine = (document.getElementById("wake-engine") || {}).value || "stt";
    const word = (document.getElementById("wake-word") || {}).value || "Athena";
    if (st) st.textContent = "⏳ Enregistrement & application…";
    try {
        const r = await apiFetch("/api/config/voice-wake", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ engine, word })
        });
        const d = await r.json();
        if (st) st.textContent = `✅ Mot d'activation « ${d.word} » (${d.engine}) appliqué. (L'assistant vocal LOCAL nécessite un relancement de son process.)`;
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});

const _btnTtsRestart = document.getElementById("btn-tts-restart");
if (_btnTtsRestart) _btnTtsRestart.addEventListener("click", async () => {
    const st = document.getElementById("tts-restart-status");
    if (st) st.textContent = "⏳ Redémarrage du conteneur en cours...";
    try {
        const r = await apiFetch("/api/system/tts/restart", { method: "POST" });
        const d = await r.json();
        if (r.ok) {
            if (st) st.textContent = "✅ " + (d.message || "Redémarré avec succès.");
        } else {
            if (st) st.textContent = "❌ " + (d.detail || "Erreur de redémarrage.");
        }
    } catch (e) {
        if (st) st.textContent = "❌ " + e;
    }
});
if (modalTabSatellites && paneSatellites) {
    modalTabSatellites.addEventListener("click", () => switchModalTab(modalTabSatellites, () => {
        paneSatellites.style.display = "block";
        _ensureSatCatalog();
        loadSatellitesPane();
        loadWakeWord();
    }));
}
const _btnSatAdd = document.getElementById("btn-sat-add");
if (_btnSatAdd) _btnSatAdd.addEventListener("click", saveSatelliteFromForm);

const _btnSatGenkey = document.getElementById("btn-sat-genkey");
if (_btnSatGenkey) _btnSatGenkey.addEventListener("click", async () => {
    const st = document.getElementById("sat-save-status");
    try {
        const r = await apiFetch("/api/config/satellites/genkey", { method: "POST" });
        const d = await r.json();
        document.getElementById("sat-key").value = d.key || "";
        if (navigator.clipboard) navigator.clipboard.writeText(d.key || "");
        if (st) st.textContent = "🔑 Clé générée et copiée — colle-la dans le YAML de l'ESP (api.encryption.key).";
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});

// Catalogue de capteurs + types audio ESPHome (chargé depuis le backend, source unique).
let _satCatalog = [];
let _satCatalogById = {};
async function _ensureSatCatalog() {
    if (_satCatalog.length) return;
    try {
        const r = await apiFetch("/api/config/satellites/sensor-catalog");
        const d = await r.json();
        _satCatalog = d.catalog || [];
        _satCatalogById = {};
        _satCatalog.forEach(c => { _satCatalogById[c.id] = c; });
        // Peupler les selects de type audio (micro / sortie) une fois.
        const micSel = document.getElementById("sat-mic-type");
        const spkSel = document.getElementById("sat-spk-type");
        if (micSel && !micSel.options.length) {
            micSel.innerHTML = (d.mic_types || []).map(t => `<option value="${t.id}">${t.label}</option>`).join("");
            micSel.addEventListener("change", _syncSatAudioRows);
        }
        if (spkSel && !spkSel.options.length) {
            spkSel.innerHTML = (d.speaker_types || []).map(t => `<option value="${t.id}">${t.label}</option>`).join("");
            spkSel.addEventListener("change", _syncSatAudioRows);
        }
        // Activation : mode (wakeword/bouton) + wake words.
        const actSel = document.getElementById("sat-activation-mode");
        const wwSel = document.getElementById("sat-wakeword");
        if (actSel && !actSel.options.length) {
            actSel.innerHTML = (d.activation_modes || []).map(t => `<option value="${t.id}">${t.label}</option>`).join("");
            actSel.addEventListener("change", _syncSatActivation);
        }
        if (wwSel && !wwSel.options.length) {
            wwSel.innerHTML = (d.wake_words || []).map(t => `<option value="${t.id}">${t.label}</option>`).join("");
        }
        _syncSatActivation();
        _syncSatAudioRows();
    } catch (e) { /* silencieux : l'UI affichera une liste vide */ }
}
function _syncSatActivation() {
    // Le wake word embarqué (microWakeWord) propose un modèle ; en mode serveur,
    // openWakeWord utilise le modèle configuré côté Jarvis — on garde le choix visible.
    const mode = (document.getElementById("sat-activation-mode") || {}).value || "embedded";
    const ww = document.getElementById("sat-wakeword");
    if (ww) ww.style.display = (mode === "embedded") ? "" : "none";
}
function _collectSatActivation() {
    return {
        mode: (document.getElementById("sat-activation-mode") || {}).value || "embedded",
        wake_word: (document.getElementById("sat-wakeword") || {}).value || "hey_jarvis",
    };
}
function _syncSatAudioRows() {
    // PDM : pas de BCLK micro. Sortie analogique (DAC interne) : pas de broches I2S HP.
    const mic = (document.getElementById("sat-mic-type") || {}).value;
    const spk = (document.getElementById("sat-spk-type") || {}).value;
    const micBclk = document.getElementById("sat-mic-bclk-grp");
    if (micBclk) micBclk.style.display = (mic === "pdm") ? "none" : "";
    const spkPins = document.getElementById("sat-spk-pins");
    if (spkPins) spkPins.style.display = (spk === "analog") ? "none" : "flex";
}
function _collectSatAudio() {
    const g = id => (document.getElementById(id) || {}).value || "";
    return {
        board: g("sat-board"),
        mic_type: g("sat-mic-type"), mic_ws: g("sat-mic-ws"), mic_bclk: g("sat-mic-bclk"), mic_din: g("sat-mic-din"),
        spk_type: g("sat-spk-type"), spk_ws: g("sat-spk-ws"), spk_bclk: g("sat-spk-bclk"), spk_dout: g("sat-spk-dout"),
    };
}
function _satCatalogOptionsHtml() {
    // Regroupe par 'group' en <optgroup>.
    const groups = {};
    _satCatalog.forEach(c => { (groups[c.group] = groups[c.group] || []).push(c); });
    return Object.entries(groups).map(([g, items]) =>
        `<optgroup label="${g}">` + items.map(c => `<option value="${c.id}">${c.label}</option>`).join("") + `</optgroup>`
    ).join("");
}
function _syncSatI2cRow() {
    const row = document.getElementById("sat-i2c-row");
    if (!row) return;
    const anyI2c = Array.from(document.querySelectorAll("#sat-sensors-list .sat-sensor-type"))
        .some(sel => (_satCatalogById[sel.value] || {}).bus === "i2c");
    row.style.display = anyI2c ? "block" : "none";
}
function _addSatSensorRow(preset) {
    const list = document.getElementById("sat-sensors-list");
    if (!list) return;
    const row = document.createElement("div");
    row.className = "sat-sensor-row";
    row.style.cssText = "display:flex;gap:6px;align-items:center;";
    row.innerHTML = `
        <select class="sat-sensor-type" style="flex:1.6;background:rgba(0,0,0,0.4);border:1px solid var(--border-color);border-radius:6px;color:#fff;padding:6px;">${_satCatalogOptionsHtml()}</select>
        <input class="sat-sensor-name" type="text" placeholder="pièce/nom" style="flex:1;" />
        <input class="sat-sensor-pin" type="text" placeholder="GPIO" style="width:72px;" />
        <button type="button" class="btn" title="Retirer" style="flex-shrink:0;padding:2px 8px;">🗑️</button>`;
    const typeSel = row.querySelector(".sat-sensor-type");
    const pinInput = row.querySelector(".sat-sensor-pin");
    const syncRow = () => {
        const c = _satCatalogById[typeSel.value] || {};
        if (c.bus === "i2c") {
            pinInput.style.display = "none";          // I2C = bus partagé, pas de broche par capteur
        } else {
            pinInput.style.display = "";
            if (!pinInput.value) pinInput.value = c.default_pin || "";
        }
        _syncSatI2cRow();
    };
    typeSel.addEventListener("change", () => { pinInput.value = ""; syncRow(); });
    if (preset) typeSel.value = preset;
    syncRow();
    row.querySelector("button").addEventListener("click", () => { row.remove(); _syncSatI2cRow(); });
    list.appendChild(row);
}
function _collectSatModules() {
    return Array.from(document.querySelectorAll("#sat-sensors-list .sat-sensor-row")).map(row => ({
        type: row.querySelector(".sat-sensor-type").value,
        name: row.querySelector(".sat-sensor-name").value.trim(),
        pin: row.querySelector(".sat-sensor-pin").value.trim(),
    }));
}
const _btnSatSensorAdd = document.getElementById("btn-sat-sensor-add");
if (_btnSatSensorAdd) _btnSatSensorAdd.addEventListener("click", async () => { await _ensureSatCatalog(); _addSatSensorRow(); });

let _lastSatYaml = { text: "", filename: "satellite.yaml" };
const _btnSatYaml = document.getElementById("btn-sat-yaml");
if (_btnSatYaml) _btnSatYaml.addEventListener("click", async () => {
    const st = document.getElementById("sat-save-status");
    const name = document.getElementById("sat-name").value.trim() || "salon";
    try {
        const r = await apiFetch("/api/config/satellites/yaml", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name,
                encryption_key: document.getElementById("sat-key").value.trim(),
                modules: _collectSatModules(),
                i2c_sda: (document.getElementById("sat-i2c-sda") || {}).value || "GPIO8",
                i2c_scl: (document.getElementById("sat-i2c-scl") || {}).value || "GPIO9",
                audio: _collectSatAudio(),
                activation: _collectSatActivation(),
                custom_yaml: (document.getElementById("sat-custom-yaml") || {}).value || ""
            })
        });
        const d = await r.json();
        _lastSatYaml = { text: d.yaml || "", filename: d.filename || "satellite.yaml" };
        document.getElementById("sat-yaml-text").value = _lastSatYaml.text;
        document.getElementById("sat-yaml-cmd").textContent = `pip install esphome && esphome run ${_lastSatYaml.filename}`;
        document.getElementById("sat-yaml-result").style.display = "block";
        if (st) st.textContent = "📄 Firmware généré ci-dessous.";
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});

function _copyToClipboard(text, btn) {
    if (navigator.clipboard) navigator.clipboard.writeText(text);
    if (btn) { const o = btn.textContent; btn.textContent = "✓"; setTimeout(() => { btn.textContent = o; }, 1500); }
}
const _btnSatYamlCopy = document.getElementById("btn-sat-yaml-copy");
if (_btnSatYamlCopy) _btnSatYamlCopy.addEventListener("click", () => _copyToClipboard(_lastSatYaml.text, _btnSatYamlCopy));
const _btnSatCmdCopy = document.getElementById("btn-sat-cmd-copy");
if (_btnSatCmdCopy) _btnSatCmdCopy.addEventListener("click", () => _copyToClipboard(document.getElementById("sat-yaml-cmd").textContent, _btnSatCmdCopy));
const _btnSatYamlDl = document.getElementById("btn-sat-yaml-dl");
if (_btnSatYamlDl) _btnSatYamlDl.addEventListener("click", () => {
    const blob = new Blob([_lastSatYaml.text], { type: "text/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = _lastSatYaml.filename;
    a.click();
    URL.revokeObjectURL(a.href);
});

// -------------------------------------------------------------------------
// ONGLET : DIAGNOSTIC (doctor) + RECHERCHE DE SESSIONS
// -------------------------------------------------------------------------
async function runDoctor() {
    const box = document.getElementById("doctor-results");
    if (!box) return;
    box.innerHTML = `<div style="opacity:0.6;">⏳ Diagnostic en cours…</div>`;
    try {
        const r = await apiFetch("/api/doctor");
        const d = await r.json();
        box.innerHTML = `<div style="margin-bottom:6px;font-weight:600;">${d.ok}/${d.total} vérifications OK</div>` +
            d.checks.map(c => `
                <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(0,0,0,0.25);border-radius:6px;font-size:0.8rem;">
                    <span>${c.ok ? "✅" : "❌"}</span>
                    <strong style="min-width:200px;">${c.name}</strong>
                    <span style="opacity:0.65;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${c.detail || ""}</span>
                </div>`).join("");
    } catch (e) {
        box.innerHTML = `<div style="color:#ff5b89;">Erreur : ${e}</div>`;
    }
}

async function runSessionSearch() {
    const q = (document.getElementById("session-search-input") || {}).value || "";
    const box = document.getElementById("session-search-results");
    if (!box) return;
    if (!q.trim()) { box.innerHTML = ""; return; }
    box.innerHTML = `<div style="opacity:0.6;">⏳ Recherche…</div>`;
    try {
        const r = await apiFetch(`/api/sessions/search?q=${encodeURIComponent(q)}&client_id=${encodeURIComponent(chatClientId)}`);
        const d = await r.json();
        if (!d.results.length) { box.innerHTML = `<div style="opacity:0.5;">Aucun résultat pour « ${q} ».</div>`; return; }
        box.innerHTML = `<div style="opacity:0.6;font-size:0.76rem;">${d.count} résultat(s)</div>` +
            d.results.map(res => `
                <div style="padding:6px 10px;background:rgba(0,0,0,0.25);border-radius:6px;font-size:0.78rem;">
                    <div style="opacity:0.6;font-size:0.7rem;">${res.conversation} · ${res.role}</div>
                    <div>${(res.snippet || "").replace(/</g, "&lt;")}</div>
                </div>`).join("");
    } catch (e) {
        box.innerHTML = `<div style="color:#ff5b89;">Erreur : ${e}</div>`;
    }
}

if (modalTabDoctor && paneDoctor) {
    modalTabDoctor.addEventListener("click", () => switchModalTab(modalTabDoctor, () => {
        paneDoctor.style.display = "block";
        runDoctor();
    }));
}

// -------------------------------------------------------------------------
// ONGLET : MESSAGERIES & NOTIFICATIONS
// -------------------------------------------------------------------------
const _MSG_FIELDS = {
    "msg-discord": "DISCORD_WEBHOOK_URL", "msg-slack": "SLACK_WEBHOOK_URL",
    "msg-webhook": "NOTIFY_WEBHOOK_URL", "msg-tg-token": "TELEGRAM_BOT_TOKEN",
    "msg-tg-chat": "TELEGRAM_CHAT_ID", "msg-smtp-host": "SMTP_HOST",
    "msg-smtp-port": "SMTP_PORT", "msg-smtp-user": "SMTP_USER",
    "msg-smtp-pass": "SMTP_PASSWORD", "msg-smtp-from": "SMTP_FROM",
    "msg-email-to": "NOTIFY_EMAIL_TO",
};
async function loadMessagingPane() {
    try {
        const r = await apiFetch("/api/config/env");
        const env = await r.json();
        for (const [id, key] of Object.entries(_MSG_FIELDS)) {
            const el = document.getElementById(id);
            if (!el) continue;
            const v = env[key] || "";
            // Les secrets reviennent masqués (xxxx...yyyy) : on laisse le champ vide + placeholder.
            el.value = (el.type === "password" || v.includes("...")) ? "" : v;
        }
        const ssl = document.getElementById("msg-smtp-ssl");
        if (ssl) ssl.checked = (env["SMTP_SSL"] || "").toLowerCase() === "true";
    } catch (e) { /* ignore */ }
    refreshMessagingStatus();
}
async function loadPairing() {
    const box = document.getElementById("pairing-list");
    if (!box) return;
    try {
        const r = await apiFetch("/api/telegram/pairing");
        const d = await r.json();
        let html = "";
        const pending = Object.entries(d.pending || {});
        if (!d.required) html += `<div style="opacity:0.6;font-size:0.72rem;">Appairage désactivé.</div>`;
        if (pending.length) {
            html += pending.map(([code, cid]) => `
                <div style="display:flex;align-items:center;gap:6px;font-size:0.76rem;background:rgba(255,180,0,0.1);padding:5px 8px;border-radius:6px;">
                    <span>⏳ ${cid} (code <code>${code}</code>)</span>
                    <button data-approve="${code}" class="btn" style="padding:1px 8px;margin-left:auto;">Approuver</button>
                </div>`).join("");
        } else if (d.required) {
            html += `<div style="opacity:0.55;font-size:0.72rem;">Aucune demande en attente.</div>`;
        }
        const approved = d.approved || [];
        if (approved.length) {
            html += `<div style="font-size:0.72rem;opacity:0.75;margin-top:4px;">Approuvés : ` +
                approved.map(c => `<span style="background:rgba(0,243,255,0.12);padding:1px 6px;border-radius:4px;margin:1px;">${c} <span data-revoke="${c}" style="cursor:pointer;color:#ff5b89;">✕</span></span>`).join("") + `</div>`;
        }
        box.innerHTML = html;
        box.querySelectorAll("[data-approve]").forEach(b => b.addEventListener("click", async () => {
            await apiFetch("/api/telegram/pairing/approve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: b.getAttribute("data-approve") }) });
            loadPairing();
        }));
        box.querySelectorAll("[data-revoke]").forEach(b => b.addEventListener("click", async () => {
            await apiFetch("/api/telegram/pairing/revoke", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat_id: b.getAttribute("data-revoke") }) });
            loadPairing();
        }));
    } catch (e) { box.innerHTML = `<div style="color:#ff5b89;font-size:0.72rem;">${e}</div>`; }
}
const _btnPairingRefresh = document.getElementById("btn-pairing-refresh");
if (_btnPairingRefresh) _btnPairingRefresh.addEventListener("click", loadPairing);

async function refreshMessagingStatus() {
    const box = document.getElementById("messaging-status");
    if (!box) return;
    try {
        const r = await apiFetch("/api/notify/channels");
        const d = await r.json();
        box.innerHTML = d.configured && d.configured.length
            ? `<span style="color:var(--accent-cyan);">🟢 Canaux actifs : ${d.configured.join(", ")}</span>`
            : `<span style="opacity:0.6;">⚪ Aucun canal configuré pour l'instant.</span>`;
    } catch (e) { /* ignore */ }
}
async function saveMessagingPane() {
    const st = document.getElementById("msg-save-status");
    const env = {};
    for (const [id, key] of Object.entries(_MSG_FIELDS)) {
        const el = document.getElementById(id);
        if (el && el.value.trim()) env[key] = el.value.trim();
    }
    const ssl = document.getElementById("msg-smtp-ssl");
    if (ssl) env["SMTP_SSL"] = ssl.checked ? "true" : "false";
    if (st) st.textContent = "⏳ Enregistrement…";
    try {
        await apiFetch("/api/config/env", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ env })
        });
        if (st) st.textContent = "✅ Messageries enregistrées (redémarre le serveur si une variable n'est pas prise en compte).";
        refreshMessagingStatus();
    } catch (e) { if (st) st.textContent = "❌ " + e; }
}
if (modalTabMessaging && paneMessaging) {
    modalTabMessaging.addEventListener("click", () => switchModalTab(modalTabMessaging, () => {
        paneMessaging.style.display = "block";
        loadMessagingPane();
        loadPairing();
    }));
}
const _btnMsgSave = document.getElementById("btn-msg-save");
if (_btnMsgSave) _btnMsgSave.addEventListener("click", saveMessagingPane);
const _btnMsgTest = document.getElementById("btn-msg-test");
if (_btnMsgTest) _btnMsgTest.addEventListener("click", async () => {
    const st = document.getElementById("msg-save-status");
    const channel = (document.getElementById("msg-test-channel") || {}).value || "";
    if (st) st.textContent = "📤 Envoi du test…";
    try {
        const r = await apiFetch("/api/notify/test", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel })
        });
        const d = await r.json();
        if (st) st.textContent = d.sent && d.sent.length
            ? `✅ Test envoyé sur : ${d.sent.join(", ")}.`
            : "⚠️ Aucun envoi (canal non configuré ?). Pense à enregistrer puis redémarrer le serveur.";
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});
const _btnDoctorRun = document.getElementById("btn-doctor-run");
if (_btnDoctorRun) _btnDoctorRun.addEventListener("click", runDoctor);
const _btnSessionSearch = document.getElementById("btn-session-search");
if (_btnSessionSearch) _btnSessionSearch.addEventListener("click", runSessionSearch);
const _sessionSearchInput = document.getElementById("session-search-input");
if (_sessionSearchInput) _sessionSearchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runSessionSearch(); });

const _btnSatConnect = document.getElementById("btn-sat-connect");
if (_btnSatConnect) _btnSatConnect.addEventListener("click", async () => {
    const st = document.getElementById("sat-save-status");
    if (st) st.textContent = "⏳ Reconnexion…";
    try {
        const r = await apiFetch("/api/config/satellites/connect", { method: "POST" });
        const d = await r.json().catch(() => ({}));
        renderSatellitesStatus(d.satellites);
        if (st) st.textContent = "✅ Reconnexion lancée.";
        loadSatellitesPane();
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});

// -------------------------------------------------------------------------
// ONGLET : ROUTINES PLANIFIÉES
// -------------------------------------------------------------------------
const _WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

function _routineScheduleLabel(s) {
    if (!s) return "";
    if (s.type === "interval") return `Toutes les ${s.minutes || 60} min`;
    if (s.type === "daily") return `Chaque jour à ${s.time || "08:00"}`;
    if (s.type === "weekly") return `Chaque ${_WEEKDAYS[s.weekday || 0]} à ${s.time || "08:00"}`;
    if (s.type === "webhook") return "Webhook (événement externe)";
    return "";
}

function _syncRoutineScheduleRows() {
    const t = document.getElementById("routine-sched-type").value;
    document.getElementById("routine-time-row").style.display = (t === "daily" || t === "weekly") ? "" : "none";
    document.getElementById("routine-weekday-row").style.display = (t === "weekly") ? "" : "none";
    document.getElementById("routine-interval-row").style.display = (t === "interval") ? "" : "none";
}

async function loadRoutinesPane() {
    // Peupler le select d'agents
    const agentSel = document.getElementById("routine-agent");
    if (agentSel && Array.isArray(agentsConfig)) {
        agentSel.innerHTML = agentsConfig.map(a => `<option value="${a.name}">${a.display_name || a.name}</option>`).join("");
    }
    _syncRoutineScheduleRows();

    const list = document.getElementById("routines-list");
    if (!list) return;
    try {
        const r = await apiFetch("/api/routines");
        const data = await r.json();
        const routines = data.routines || [];
        if (routines.length === 0) {
            list.innerHTML = `<div style="opacity:0.5;font-size:0.78rem;text-align:center;padding:8px;">Aucune routine. Créez-en une ci-dessous.</div>`;
            return;
        }
        list.innerHTML = "";
        routines.forEach(rt => {
            const row = document.createElement("div");
            row.className = "service-item";
            row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 12px;";
            const last = rt.last_run ? new Date(rt.last_run).toLocaleString() : "jamais";
            row.innerHTML = `
                <div style="min-width:0;">
                    <strong style="color:${rt.enabled ? 'var(--accent-cyan)' : '#888'};">${rt.name}</strong>
                    <div style="font-size:0.7rem;opacity:0.7;">${_routineScheduleLabel(rt.schedule)} · ${rt.agent} · dernier: ${last}</div>
                </div>
                <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
                    <button data-act="toggle" title="${rt.enabled ? 'Désactiver' : 'Activer'}" style="background:none;border:1px solid rgba(255,255,255,0.2);color:#fff;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:0.72rem;">${rt.enabled ? '⏸️' : '▶️'}</button>
                    <button data-act="run" title="Exécuter maintenant" style="background:rgba(0,243,255,0.12);border:1px solid rgba(0,243,255,0.4);color:var(--accent-cyan);border-radius:4px;padding:2px 6px;cursor:pointer;font-size:0.72rem;">▶ Run</button>
                    <button data-act="del" title="Supprimer" style="background:rgba(255,0,80,0.12);border:1px solid rgba(255,0,80,0.4);color:#ff5b89;border-radius:4px;padding:2px 6px;cursor:pointer;font-size:0.72rem;">🗑️</button>
                </div>`;
            row.querySelector('[data-act="toggle"]').addEventListener("click", () => saveRoutine({ ...rt, enabled: !rt.enabled }));
            row.querySelector('[data-act="run"]').addEventListener("click", async () => {
                const st = document.getElementById("routine-save-status");
                if (st) st.textContent = `⏳ Exécution de « ${rt.name} »…`;
                try { await apiFetch(`/api/routines/${rt.id}/run`, { method: "POST" }); if (st) st.textContent = `✅ « ${rt.name} » exécutée.`; } catch (e) { if (st) st.textContent = "❌ " + e; }
            });
            row.querySelector('[data-act="del"]').addEventListener("click", async () => {
                if (!confirm(`Supprimer la routine « ${rt.name} » ?`)) return;
                await apiFetch(`/api/routines/${rt.id}`, { method: "DELETE" });
                loadRoutinesPane();
            });
            list.appendChild(row);

            // Webhook : afficher l'URL (avec secret) à copier dans Home Assistant/IFTTT.
            if (rt.schedule && rt.schedule.type === "webhook" && rt.secret) {
                const url = `${location.origin}/api/hooks/${rt.id}?token=${rt.secret}`;
                const urlRow = document.createElement("div");
                urlRow.style.cssText = "display:flex;align-items:center;gap:6px;margin:-2px 0 2px 12px;font-size:0.68rem;";
                const code = document.createElement("code");
                code.textContent = url;
                code.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:0.7;flex:1;";
                const copyBtn = document.createElement("button");
                copyBtn.type = "button";
                copyBtn.textContent = "📋";
                copyBtn.title = "Copier l'URL du webhook (POST)";
                copyBtn.style.cssText = "background:none;border:1px solid rgba(255,255,255,0.2);color:#fff;border-radius:4px;padding:1px 6px;cursor:pointer;flex-shrink:0;";
                copyBtn.addEventListener("click", () => {
                    navigator.clipboard.writeText(url);
                    copyBtn.textContent = "✓";
                    setTimeout(() => { copyBtn.textContent = "📋"; }, 1500);
                });
                urlRow.append(code, copyBtn);
                list.appendChild(urlRow);
            }
        });
    } catch (e) {
        list.innerHTML = `<div style="color:#ff5b89;font-size:0.78rem;">Erreur : ${e}</div>`;
    }
}

async function saveRoutine(routine) {
    const st = document.getElementById("routine-save-status");
    try {
        const r = await apiFetch("/api/routines", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(routine)
        });
        if (r.ok) { loadRoutinesPane(); if (st && !routine.id) st.textContent = "✅ Routine ajoutée."; }
        else { const d = await r.json().catch(() => ({})); if (st) st.textContent = "❌ " + (d.detail || "Erreur"); }
    } catch (e) { if (st) st.textContent = "❌ " + e; }
}

function saveNewRoutineFromForm() {
    const type = document.getElementById("routine-sched-type").value;
    const schedule = { type };
    if (type === "interval") schedule.minutes = parseInt(document.getElementById("routine-minutes").value || "60", 10);
    if (type === "daily" || type === "weekly") schedule.time = document.getElementById("routine-time").value || "08:00";
    if (type === "weekly") schedule.weekday = parseInt(document.getElementById("routine-weekday").value || "0", 10);
    const name = document.getElementById("routine-name").value.trim();
    const prompt = document.getElementById("routine-prompt").value.trim();
    if (!name || !prompt) { const st = document.getElementById("routine-save-status"); if (st) st.textContent = "❌ Nom et tâche requis."; return; }
    saveRoutine({
        name, prompt,
        agent: document.getElementById("routine-agent").value || orchestratorName(),
        schedule,
        notify: document.getElementById("routine-notify").checked
    });
    document.getElementById("routine-name").value = "";
    document.getElementById("routine-prompt").value = "";
}

if (modalTabRoutines && paneRoutines) {
    modalTabRoutines.addEventListener("click", () => switchModalTab(modalTabRoutines, () => {
        paneRoutines.style.display = "block";
        loadRoutinesPane();
    }));
}
const _routineSchedType = document.getElementById("routine-sched-type");
if (_routineSchedType) _routineSchedType.addEventListener("change", _syncRoutineScheduleRows);
const _btnSaveRoutine = document.getElementById("btn-save-routine");
if (_btnSaveRoutine) _btnSaveRoutine.addEventListener("click", saveNewRoutineFromForm);

// -------------------------------------------------------------------------
// ONGLET : BASE DE CONNAISSANCES (RAG)
// -------------------------------------------------------------------------
async function loadKnowledgePane() {
    const list = document.getElementById("kb-list");
    const count = document.getElementById("kb-count");
    if (!list) return;
    list.innerHTML = "<div style='opacity:0.5;font-size:0.78rem;'>Chargement…</div>";
    try {
        const r = await apiFetch("/api/knowledge?limit=200");
        const d = await r.json();
        if (count) count.textContent = `${d.count} document(s)`;
        const docs = d.documents || [];
        if (docs.length === 0) { list.innerHTML = "<div style='opacity:0.5;font-size:0.78rem;text-align:center;padding:8px;'>Base vide.</div>"; return; }
        list.innerHTML = "";
        docs.forEach(doc => {
            const row = document.createElement("div");
            row.className = "service-item";
            row.style.cssText = "display:flex;align-items:flex-start;justify-content:space-between;gap:8px;padding:8px 12px;";
            const info = document.createElement("div");
            info.style.cssText = "min-width:0;flex:1;";
            const src = document.createElement("div");
            src.style.cssText = "color:var(--accent-cyan);font-size:0.74rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
            src.textContent = `${doc.source} · ${doc.length} car.`;
            const prev = document.createElement("div");
            prev.style.cssText = "font-size:0.72rem;opacity:0.7;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;";
            prev.textContent = doc.preview;
            info.append(src, prev);
            const del = document.createElement("button");
            del.type = "button"; del.textContent = "🗑️";
            del.style.cssText = "background:rgba(255,0,80,0.12);border:1px solid rgba(255,0,80,0.4);color:#ff5b89;border-radius:4px;padding:1px 7px;cursor:pointer;font-size:0.72rem;flex-shrink:0;";
            del.addEventListener("click", async () => {
                if (!confirm("Supprimer ce document de la base de connaissances ?")) return;
                await apiFetch(`/api/knowledge/${doc.id}`, { method: "DELETE" });
                loadKnowledgePane();
            });
            row.append(info, del);
            list.appendChild(row);
        });
    } catch (e) {
        list.innerHTML = `<div style="color:#ff5b89;font-size:0.78rem;">Erreur : ${e}</div>`;
    }
}

async function ingestKnowledge(payload, label) {
    const st = document.getElementById("kb-status");
    if (st) st.textContent = `⏳ Indexation ${label}…`;
    try {
        const r = await apiFetch("/api/knowledge/ingest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const d = await r.json().catch(() => ({}));
        if (r.ok) { if (st) st.textContent = `✅ Indexé (${d.chars || 0} car.).`; loadKnowledgePane(); }
        else { if (st) st.textContent = "❌ " + (d.detail || "Erreur"); }
    } catch (e) { if (st) st.textContent = "❌ " + e; }
}

if (modalTabKnowledge && paneKnowledge) {
    modalTabKnowledge.addEventListener("click", () => switchModalTab(modalTabKnowledge, () => {
        paneKnowledge.style.display = "block";
        loadKnowledgePane();
    }));
}
const _btnKbUrl = document.getElementById("btn-kb-url");
if (_btnKbUrl) _btnKbUrl.addEventListener("click", () => {
    const u = document.getElementById("kb-url");
    if (u && u.value.trim()) { ingestKnowledge({ url: u.value.trim() }, "de l'URL"); u.value = ""; }
});
const _btnKbText = document.getElementById("btn-kb-text");
if (_btnKbText) _btnKbText.addEventListener("click", () => {
    const t = document.getElementById("kb-text");
    if (t && t.value.trim()) { ingestKnowledge({ text: t.value.trim(), source: "manuel" }, "du texte"); t.value = ""; }
});

// -------------------------------------------------------------------------
// ONGLET : UTILISATEURS (multi-utilisateur, admin)
// -------------------------------------------------------------------------
async function loadUsersPane() {
    const list = document.getElementById("users-list");
    const st = document.getElementById("users-status");
    if (!list) return;
    try {
        const r = await apiFetch("/api/users");
        if (r.status === 403) { list.innerHTML = "<div style='opacity:0.6;font-size:0.78rem;'>Réservé à l'administrateur.</div>"; return; }
        const d = await r.json();
        const users = d.users || [];
        if (st) st.textContent = d.auth_active ? "" : "Aucune auth active : créez un compte pour activer la connexion.";
        if (users.length === 0) { list.innerHTML = "<div style='opacity:0.5;font-size:0.78rem;text-align:center;padding:8px;'>Aucun compte (accès libre/admin).</div>"; return; }
        list.innerHTML = "";
        users.forEach(u => {
            const row = document.createElement("div");
            row.className = "service-item";
            row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 12px;";
            const info = document.createElement("div");
            info.innerHTML = `<strong>${u.username}</strong> <span style="font-size:0.7rem;opacity:0.7;">· ${u.role === "admin" ? "👑 admin" : "utilisateur"}</span>`;
            const del = document.createElement("button");
            del.type = "button"; del.textContent = "🗑️";
            del.style.cssText = "background:rgba(255,0,80,0.12);border:1px solid rgba(255,0,80,0.4);color:#ff5b89;border-radius:4px;padding:1px 7px;cursor:pointer;font-size:0.72rem;";
            del.addEventListener("click", async () => {
                if (!confirm(`Supprimer l'utilisateur « ${u.username} » ?`)) return;
                const rr = await apiFetch(`/api/users/${encodeURIComponent(u.username)}`, { method: "DELETE" });
                if (!rr.ok) { const dd = await rr.json().catch(() => ({})); if (st) st.textContent = "❌ " + (dd.detail || "Erreur"); }
                loadUsersPane();
            });
            row.append(info, del);
            list.appendChild(row);
        });
    } catch (e) {
        list.innerHTML = `<div style="color:#ff5b89;font-size:0.78rem;">Erreur : ${e}</div>`;
    }
}

if (modalTabUsers && paneUsers) {
    modalTabUsers.addEventListener("click", () => switchModalTab(modalTabUsers, () => {
        paneUsers.style.display = "block";
        loadUsersPane();
    }));
}
const _btnAddUser = document.getElementById("btn-add-user");
if (_btnAddUser) _btnAddUser.addEventListener("click", async () => {
    const name = document.getElementById("user-name").value.trim();
    const pass = document.getElementById("user-pass").value;
    const role = document.getElementById("user-role").value;
    const st = document.getElementById("users-status");
    if (!name || !pass) { if (st) st.textContent = "❌ Nom et mot de passe requis."; return; }
    try {
        const r = await apiFetch("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: name, password: pass, role }) });
        const d = await r.json().catch(() => ({}));
        if (r.ok) { if (st) st.textContent = `✅ Compte « ${name} » créé.`; document.getElementById("user-name").value = ""; document.getElementById("user-pass").value = ""; loadUsersPane(); }
        else { if (st) st.textContent = "❌ " + (d.detail || "Erreur"); }
    } catch (e) { if (st) st.textContent = "❌ " + e; }
});

// -------------------------------------------------------------------------
// ONGLET 1 : GESTION DES AGENTS (LISTER / EDITER / SUPPRIMER)
// -------------------------------------------------------------------------
function loadConfigAgentsPane() {
    agentsList.innerHTML = "";
    // Déterminer l'orchestrateur (protégé) : flag orchestrator, sinon "Jarvis", sinon 1er.
    let orchName = (agentsConfig.find(a => a.orchestrator === true) || {}).name;
    if (!orchName) orchName = agentsConfig.some(a => a.name === "Jarvis") ? "Jarvis" : (agentsConfig[0] || {}).name;
    agentsConfig.forEach(agent => {
        const card = document.createElement("div");
        card.className = "agent-item-card";
        const displayName = agent.display_name || agent.name;
        const subtitle = agent.display_name && agent.display_name !== agent.name ? `${agent.name} • ${agent.model}` : agent.model;
        const isOrch = agent.name === orchName;
        const delBtn = isOrch
            ? `<span title="L'orchestrateur ne peut pas être supprimé" style="padding:6px 10px;font-size:0.7rem;opacity:0.6;">🛡️ orchestrateur</span>`
            : `<button class="btn btn-secondary btn-del-agent" data-name="${agent.name}" style="padding: 6px 12px; margin: 0; border-color: rgba(239, 68, 68, 0.4); color: #f87171;">Supprimer</button>`;
        card.innerHTML = `
            <div class="agent-meta-info">
                <h4>${getAgentEmoji(agent.avatar_type || agent.name)} ${displayName}${isOrch ? ' ⭐' : ''}</h4>
                <span>Modèle : ${subtitle}</span>
            </div>
            <div class="agent-actions">
                <button class="btn btn-secondary btn-edit-agent" data-name="${agent.name}" style="padding: 6px 12px; margin: 0;">Modifier</button>
                ${delBtn}
            </div>
        `;
        agentsList.appendChild(card);
    });
    
    // Attacher les écouteurs de modification
    document.querySelectorAll(".btn-edit-agent").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const name = e.target.getAttribute("data-name");
            openAgentFormModal(name);
        });
    });
    
    // Attacher les écouteurs de suppression
    document.querySelectorAll(".btn-del-agent").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const name = e.target.getAttribute("data-name");
            if (confirm(`Supprimer définitivement l'agent ${name} de l'essaim ?`)) {
                const newAgents = agentsConfig.filter(a => a.name !== name);
                await saveAgentsConfigToServer(newAgents);
            }
        });
    });
}

// -------------------------------------------------------------------------
// ONGLET 2 : CLÉS D'API & ENV
// -------------------------------------------------------------------------
async function loadConfigEnvPane() {
    try {
        const response = await apiFetch("/api/config/env");
        const env = await response.json();
        
        document.getElementById("key-openai").placeholder = env.OPENAI_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-anthropic").placeholder = env.ANTHROPIC_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-gemini").placeholder = env.GEMINI_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-openrouter").placeholder = env.OPENROUTER_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-groq").placeholder = env.GROQ_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-mistral").placeholder = env.MISTRAL_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-dashscope").placeholder = env.DASHSCOPE_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-qwen").placeholder = env.QWEN_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-ollama").value = env.OLLAMA_API_BASE || "";
        document.getElementById("key-custom-base").value = env.CUSTOM_LLM_API_BASE || "";
        document.getElementById("key-custom-key").placeholder = env.CUSTOM_LLM_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-ha-url").value = env.HA_URL || "";
        document.getElementById("key-ha-token").placeholder = env.HA_TOKEN ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-telegram").placeholder = env.TELEGRAM_BOT_TOKEN ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-img-provider").value = env.IMAGE_GENERATOR_PROVIDER || "pollinations";
        document.getElementById("key-stability").placeholder = env.STABILITY_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-custom-img-base").value = env.CUSTOM_IMAGE_API_BASE || "";
        document.getElementById("key-custom-img-key").placeholder = env.CUSTOM_IMAGE_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-video-provider").value = env.VIDEO_GENERATOR_PROVIDER || "local";
        document.getElementById("key-fal").placeholder = env.FAL_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-replicate").placeholder = env.REPLICATE_API_TOKEN ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-custom-video-base").value = env.CUSTOM_VIDEO_API_BASE || "";
        document.getElementById("key-custom-video-key").placeholder = env.CUSTOM_VIDEO_API_KEY ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-ssh-host").value = env.SSH_HOST || "";
        document.getElementById("key-ssh-port").value = env.SSH_PORT || "";
        document.getElementById("key-ssh-username").value = env.SSH_USERNAME || "";
        document.getElementById("key-ssh-password").placeholder = env.SSH_PASSWORD ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Non configurée";
        document.getElementById("key-ssh-key-path").value = env.SSH_KEY_PATH || "";
        document.getElementById("key-admin-password").placeholder = env.ADMIN_PASSWORD ? "Existe (masquée) - Laisser vide pour ne pas changer" : "Aucun (Désactivé)";
    } catch (err) {
        logToTerminal("Impossible de charger les clés d'API: " + err, "error");
    }
}

document.getElementById("env-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const envData = {
        OPENAI_API_KEY: document.getElementById("key-openai").value,
        ANTHROPIC_API_KEY: document.getElementById("key-anthropic").value,
        GEMINI_API_KEY: document.getElementById("key-gemini").value,
        OPENROUTER_API_KEY: document.getElementById("key-openrouter").value,
        GROQ_API_KEY: document.getElementById("key-groq").value,
        MISTRAL_API_KEY: document.getElementById("key-mistral").value,
        DASHSCOPE_API_KEY: document.getElementById("key-dashscope").value,
        QWEN_API_KEY: document.getElementById("key-qwen").value,
        OLLAMA_API_BASE: document.getElementById("key-ollama").value,
        CUSTOM_LLM_API_BASE: document.getElementById("key-custom-base").value,
        CUSTOM_LLM_API_KEY: document.getElementById("key-custom-key").value,
        HA_URL: document.getElementById("key-ha-url").value,
        HA_TOKEN: document.getElementById("key-ha-token").value,
        TELEGRAM_BOT_TOKEN: document.getElementById("key-telegram").value,
        IMAGE_GENERATOR_PROVIDER: document.getElementById("key-img-provider").value,
        STABILITY_API_KEY: document.getElementById("key-stability").value,
        CUSTOM_IMAGE_API_BASE: document.getElementById("key-custom-img-base").value,
        CUSTOM_IMAGE_API_KEY: document.getElementById("key-custom-img-key").value,
        VIDEO_GENERATOR_PROVIDER: document.getElementById("key-video-provider").value,
        FAL_API_KEY: document.getElementById("key-fal").value,
        REPLICATE_API_TOKEN: document.getElementById("key-replicate").value,
        CUSTOM_VIDEO_API_BASE: document.getElementById("key-custom-video-base").value,
        CUSTOM_VIDEO_API_KEY: document.getElementById("key-custom-video-key").value
    };
    
    // Nettoyer les clés vides (qui ne doivent pas être envoyées si inchangées)
    Object.keys(envData).forEach(key => {
        if (envData[key] === "") delete envData[key];
    });
    
    try {
        const response = await apiFetch("/api/config/env", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ env: envData })
        });
        const res = await response.json();
        if (response.ok) {
            alert(res.message);
            loadConfigEnvPane();
        } else {
            alert("Erreur de sauvegarde: " + res.detail);
        }
    } catch (err) {
        alert("Erreur réseau: " + err);
    }
});

// Soumission dédiée pour la configuration Terminal SSH
const sshForm = document.getElementById("ssh-form");
if (sshForm) {
    sshForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const sshData = {
            SSH_HOST: document.getElementById("key-ssh-host").value,
            SSH_PORT: document.getElementById("key-ssh-port").value,
            SSH_USERNAME: document.getElementById("key-ssh-username").value,
            SSH_PASSWORD: document.getElementById("key-ssh-password").value,
            SSH_KEY_PATH: document.getElementById("key-ssh-key-path").value,
            ADMIN_PASSWORD: document.getElementById("key-admin-password").value
        };
        
        // Nettoyer les champs vides pour ne pas écraser s'ils n'ont pas changé
        Object.keys(sshData).forEach(key => {
            if (sshData[key] === "") delete sshData[key];
        });
        
        try {
            const response = await apiFetch("/api/config/env", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ env: sshData })
            });
            const res = await response.json();
            if (response.ok) {
                alert("Configuration SSH sauvegardée avec succès !");
                loadConfigEnvPane();
            } else {
                alert("Erreur de sauvegarde SSH : " + res.detail);
            }
        } catch (err) {
            alert("Erreur réseau : " + err);
        }
    });
}

// =========================================================================
// MODALE INTERNE FORMULAIRE AGENT (AJOUT/EDITION D'UN AGENT)
// =========================================================================
const ALL_AVAILABLE_TOOLS = [
    {
        key: "read_file",
        title: "📖 Code : Lire un fichier",
        desc: "Lit un fichier du workspace avec numéros de ligne (pour éditer ensuite précisément)."
    },
    {
        key: "edit_file",
        title: "✏️ Code : Éditer (str-replace)",
        desc: "Modification ciblée et non destructive par remplacement de texte exact. Le plus sûr."
    },
    {
        key: "write_file",
        title: "📝 Code : Créer / réécrire un fichier",
        desc: "Crée ou remplace intégralement un fichier (écriture atomique)."
    },
    {
        key: "apply_patch",
        title: "🩹 Code : Appliquer un diff",
        desc: "Applique un diff unifié (multi-modifications) avec vérification du contexte."
    },
    {
        key: "run_checks",
        title: "🧪 Code : Lancer tests / lint",
        desc: "Exécute pytest/ruff/npm test… et renvoie un verdict PASS/FAIL centré sur les erreurs (boucle de correction)."
    },
    {
        key: "git_status",
        title: "🔀 Git : Statut",
        desc: "Branche courante et fichiers modifiés du dépôt du workspace."
    },
    {
        key: "git_diff",
        title: "🔍 Git : Diff",
        desc: "Affiche les modifications (optionnellement indexées ou pour un fichier)."
    },
    {
        key: "git_log",
        title: "📜 Git : Historique",
        desc: "Liste les derniers commits (hash + message)."
    },
    {
        key: "git_create_branch",
        title: "🌿 Git : Nouvelle branche",
        desc: "Crée une branche et bascule dessus (checkout -b)."
    },
    {
        key: "git_commit",
        title: "✅ Git : Commit",
        desc: "Indexe et commite les modifications (messages sémantiques). Ne pousse pas."
    },
    {
        key: "git_create_worktree",
        title: "🌳 Git : Créer un worktree",
        desc: "Répertoire de travail isolé sur une branche (sous .worktrees/) pour bosser sans toucher l'arbre principal."
    },
    {
        key: "git_list_worktrees",
        title: "🌳 Git : Lister les worktrees",
        desc: "Liste les worktrees existants (chemin + branche)."
    },
    {
        key: "git_remove_worktree",
        title: "🌳 Git : Supprimer un worktree",
        desc: "Retire un worktree (la branche est conservée)."
    },
    {
        key: "search_code",
        title: "🔎 Code : Rechercher (regex)",
        desc: "Recherche une expression régulière dans tout le code du workspace (façon ripgrep)."
    },
    {
        key: "find_definition",
        title: "🎯 Code : Définition d'un symbole",
        desc: "Localise où une fonction/classe/type est défini (multi-langages)."
    },
    {
        key: "find_references",
        title: "🔗 Code : Références d'un symbole",
        desc: "Trouve toutes les utilisations d'un symbole dans le projet."
    },
    {
        key: "file_outline",
        title: "🗂️ Code : Plan d'un fichier",
        desc: "Liste les fonctions/classes d'un fichier avec leur ligne, sans tout lire."
    },
    {
        key: "get_ha_state",
        title: "🏠 Home Assistant : État des capteurs",
        desc: "Consulter l'état de vos lumières, capteurs ou interrupteurs connectés."
    },
    {
        key: "get_current_room",
        title: "📍 Présence : Pièce actuelle",
        desc: "Lit l'entité HA de présence (optionnel) pour savoir dans quelle pièce vous êtes (follow-me)."
    },
    {
        key: "trigger_workflow",
        title: "🔗 Automatisation : Déclencher n8n",
        desc: "Lance un workflow n8n déclaré (par nom). Sensible : effet de bord externe (approbation)."
    },
    {
        key: "call_ha_service",
        title: "⚡ Home Assistant : Contrôler des appareils",
        desc: "Allumer/éteindre vos lumières, régler le thermostat ou lancer un automatisme."
    },
    {
        key: "memorize_fact",
        title: "🧠 Mémoriser des informations clés",
        desc: "Enregistrer à long terme des détails sur vous, vos goûts ou vos préférences."
    },
    {
        key: "remember_relation",
        title: "🕸️ Mémoire-graphe : Enregistrer une relation",
        desc: "Lier deux entités (sujet —relation→ objet), ex. « Tim écrit Les Larmes de l'Olympe »."
    },
    {
        key: "query_graph",
        title: "🕸️ Mémoire-graphe : Voisinage d'une entité",
        desc: "Retrouver tout ce qui est connecté à une entité (relations directes et à un saut)."
    },
    {
        key: "store_document",
        title: "📁 Archiver des notes / documents",
        desc: "Stocker des fichiers textuels longs ou notes pour qu'ils soient gardés en mémoire."
    },
    {
        key: "search_memory",
        title: "🔍 Consulter la mémoire sémantique",
        desc: "Rechercher parmi tous vos faits mémorisés et vos documents archivés."
    },
    {
        key: "execute_python_code",
        title: "🐍 Exécuter du Code Python",
        desc: "Résoudre des calculs complexes ou lancer du code Python isolé dans un sandbox."
    },
    {
        key: "execute_bash_command",
        title: "🐚 Exécuter des Commandes Linux",
        desc: "Lancer des commandes shell système non-destructrices sur votre machine."
    },
    {
        key: "save_new_skill",
        title: "💾 Enregistrer un nouvel outil (Skill)",
        desc: "Transformer une fonction écrite par l'agent en un outil utilisable pour toujours."
    },
    {
        key: "delete_skill",
        title: "🗑️ Supprimer un outil (Skill)",
        desc: "Supprimer définitivement une compétence personnalisée (Skill) créée par les agents."
    },
    {
        key: "query_agent",
        title: "🤝 Consulter un agent en arrière-plan",
        desc: "Permettre au superviseur d'interroger un agent spécialiste en tâche de fond et de synthétiser ses résultats."
    },
    {
        key: "web_search",
        title: "🌐 Recherche Web en direct",
        desc: "Parcourir le Web sur Google/DuckDuckGo pour obtenir des infos en temps réel."
    },
    {
        key: "web_scrape",
        title: "📄 Extraire le contenu d'un site",
        desc: "Lire et extraire tout le texte d'un article ou d'un lien web pour analyse."
    },
    {
        key: "generate_image",
        title: "🎨 Générer des images standards",
        desc: "Créer des illustrations, logos ou mockups UI avec DALL-E/Flux."
    },
    {
        key: "ingest_file",
        title: "📥 Importer & Analyser un fichier",
        desc: "Analyser le contenu brut d'un fichier texte local dans le chat."
    },
    {
        key: "add_calendar_event",
        title: "📅 Ajouter à l'Agenda",
        desc: "Ajouter des rendez-vous ou événements à votre calendrier."
    },
    {
        key: "list_calendar_events",
        title: "📋 Consulter l'Agenda",
        desc: "Consulter la liste de vos événements et tâches planifiées."
    },
    {
        key: "delete_calendar_event",
        title: "❌ Retirer de l'Agenda",
        desc: "Supprimer définitivement un rendez-vous de votre calendrier."
    },
    {
        key: "add_list_item",
        title: "📝 Ajouter à une Liste (Tâches/Idées)",
        desc: "Ajouter un élément à une liste de courses, TODO ou brainstorming."
    },
    {
        key: "get_list_items",
        title: "👁️ Voir le contenu des Listes",
        desc: "Afficher tous les éléments d'une de vos listes interactives."
    },
    {
        key: "toggle_list_item",
        title: "🔘 Cocher / Valider un élément",
        desc: "Valider ou dévalider un élément ou tâche d'une liste."
    },
    {
        key: "delete_list_item",
        title: "🗑️ Supprimer d'une Liste",
        desc: "Retirer un élément spécifique d'une de vos listes."
    },
    {
        key: "generate_artistic_image",
        title: "🖼️ Générer des œuvres d'art HD",
        desc: "Créer des peintures et illustrations artistiques haute fidélité."
    },
    {
        key: "generate_artistic_video",
        title: "🎬 Générer des vidéos artistiques",
        desc: "Créer de courtes animations ou clips vidéos générés par IA."
    },
    {
        key: "get_daily_briefing",
        title: "☀️ Rapport du Matin (Briefing)",
        desc: "Générer un briefing matinal complet (météo, tâches, agenda)."
    }
];

agentFormClose.addEventListener("click", () => {
    agentFormModal.style.display = "none";
});

btnAddAgent.addEventListener("click", () => {
    openAgentFormModal(null);
});

function openAgentFormModal(agentName = null) {
    agentFormModal.style.display = "flex";
    
    const checkboxesTools = document.getElementById("agent-tools-checkboxes");
    const checkboxesHandoffs = document.getElementById("agent-handoffs-checkboxes");
    const modelHelper = document.getElementById("agent-model-helper");
    
    checkboxesTools.innerHTML = "";
    checkboxesHandoffs.innerHTML = "";
    modelHelper.innerHTML = '<option value="">⚡ Choix rapide...</option>';
    
    const isEdit = agentName !== null;
    document.getElementById("agent-form-title").textContent = isEdit ? `Modifier l'Agent ${agentName}` : "Créer un nouvel Agent";
    document.getElementById("agent-orig-name").value = isEdit ? agentName : "";
    
    const agent = isEdit ? agentsConfig.find(a => a.name === agentName) : null;
    
    document.getElementById("agent-name").value = isEdit ? agent.name : "";
    document.getElementById("agent-display-name").value = (isEdit && agent.display_name) ? agent.display_name : "";
    document.getElementById("agent-avatar-type").value = (isEdit && agent.avatar_type) ? agent.avatar_type : "robot_neon";
    document.getElementById("agent-model").value = isEdit ? agent.model : "gpt-4o";
    document.getElementById("agent-prompt").value = isEdit ? agent.system_prompt : "";
    document.getElementById("agent-welcome").value = (isEdit && agent.welcome_message) ? agent.welcome_message : "";
    
    // Charger dynamiquement les modèles disponibles
    apiFetch("/api/config/models")
        .then(res => res.json())
        .then(data => {
            Object.keys(data).forEach(provider => {
                const group = document.createElement("optgroup");
                group.label = provider;
                
                data[provider].forEach(model => {
                    const opt = document.createElement("option");
                    opt.value = model;
                    opt.textContent = model.includes("/") ? model.split("/").slice(1).join("/") : model;
                    // Sélectionner par défaut si le modèle actuel correspond
                    if (isEdit && agent.model === model) {
                        opt.selected = true;
                    }
                    group.appendChild(opt);
                });
                modelHelper.appendChild(group);
            });
        })
        .catch(err => console.error("Erreur de récupération des modèles:", err));
        
    // Listener pour copier la valeur sélectionnée dans le champ texte principal
    modelHelper.onchange = (e) => {
        if (e.target.value) {
            document.getElementById("agent-model").value = e.target.value;
        }
    };
    
    // Injecter les outils : liste curée (jolis libellés) + TOUS les outils réellement
    // enregistrés côté serveur (standard + compétences + MCP) qui ne sont pas dans la
    // liste curée, pour qu'aucun outil cochable ne soit oublié.
    const renderToolChecklist = (tools) => {
        checkboxesTools.innerHTML = "";
        tools.forEach(tool => {
            const item = document.createElement("div");
            item.className = "tool-checkbox-card";
            const checked = isEdit && agent.tools && agent.tools.includes(tool.key) ? "checked" : "";
            item.innerHTML = `
                <input type="checkbox" name="tools" value="${tool.key}" id="tool-${tool.key}" ${checked}>
                <label for="tool-${tool.key}" class="tool-checkbox-label">
                    <span class="tool-checkbox-title">${tool.title}</span>
                    <span class="tool-checkbox-desc">${tool.desc || ""}</span>
                    <span class="tool-checkbox-key"><code>${tool.key}</code></span>
                </label>
            `;
            checkboxesTools.appendChild(item);
        });
    };
    // Rendu immédiat avec la liste curée (réactif), puis fusion avec le serveur.
    renderToolChecklist(ALL_AVAILABLE_TOOLS);
    apiFetch("/api/config/tools")
        .then(res => res.json())
        .then(data => {
            const curatedKeys = new Set(ALL_AVAILABLE_TOOLS.map(t => t.key));
            const catBadge = { competence: "🧩 Compétence", mcp: "🔌 MCP", standard: "🔧 Outil" };
            const extras = (data.tools || [])
                .filter(rt => !curatedKeys.has(rt.key))
                .map(rt => ({
                    key: rt.key,
                    title: (catBadge[rt.category] || "🔧 Outil") + " · " + rt.key,
                    desc: rt.desc || "",
                }));
            // Réafficher aussi un outil coché qui ne serait plus enregistré (alerte visuelle).
            const realKeys = new Set((data.tools || []).map(rt => rt.key));
            const orphanChecked = (isEdit && agent.tools ? agent.tools : [])
                .filter(k => !curatedKeys.has(k) && !realKeys.has(k))
                .map(k => ({ key: k, title: "⚠️ Inconnu · " + k, desc: "Outil coché mais non enregistré côté serveur." }));
            renderToolChecklist([...ALL_AVAILABLE_TOOLS, ...extras, ...orphanChecked]);
        })
        .catch(err => console.error("Erreur de récupération des outils:", err));
    
    // Injecter les autres agents pour cocher les handoffs
    agentsConfig.forEach(otherAgent => {
        // Un agent ne se transfère pas à lui-même
        if (isEdit && otherAgent.name === agentName) return;
        
        const label = document.createElement("label");
        label.className = "checkbox-label";
        const checked = isEdit && agent.handoffs && agent.handoffs.includes(otherAgent.name) ? "checked" : "";
        label.innerHTML = `<input type="checkbox" name="handoffs" value="${otherAgent.name}" ${checked}> ${otherAgent.name}`;
        checkboxesHandoffs.appendChild(label);
    });
}

// Soumission du formulaire agent (sauvegarde locale + rechargement)
agentConfigForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const origName = document.getElementById("agent-orig-name").value;
    const name = document.getElementById("agent-name").value.trim();
    const displayNameInput = document.getElementById("agent-display-name").value.trim();
    const display_name = displayNameInput || name; // Fallback sur name si vide
    const avatar_type = document.getElementById("agent-avatar-type").value;
    const model = document.getElementById("agent-model").value.trim();
    const system_prompt = document.getElementById("agent-prompt").value.trim();
    const welcome_message = document.getElementById("agent-welcome").value.trim() || "";
    
    // Outils cochés
    const tools = [];
    document.querySelectorAll("input[name='tools']:checked").forEach(cb => {
        tools.push(cb.value);
    });
    
    // Handoffs cochés
    const handoffs = [];
    document.querySelectorAll("input[name='handoffs']:checked").forEach(cb => {
        handoffs.push(cb.value);
    });
    
    const updatedAgent = { name, display_name, welcome_message, avatar_type, model, system_prompt, tools, handoffs };
    // Préserver le flag orchestrateur lors d'une édition : sinon renommer l'orchestrateur
    // (ex: Jarvis → Athena) le ferait passer pour une suppression et serait refusé.
    if (origName) {
        const orig = agentsConfig.find(a => a.name === origName);
        if (orig && orig.orchestrator) updatedAgent.orchestrator = true;
    }

    let newAgents = [];
    if (origName) {
        // Edition : on remplace
        newAgents = agentsConfig.map(a => a.name === origName ? updatedAgent : a);
    } else {
        // Création : on ajoute
        newAgents = [...agentsConfig, updatedAgent];
    }
    
    await saveAgentsConfigToServer(newAgents);
    agentFormModal.style.display = "none";
});

// Envoyer la structure d'agents modifiée au serveur FastAPI
async function saveAgentsConfigToServer(newAgentsList) {
    try {
        const response = await apiFetch("/api/config/agents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ agents: newAgentsList })
        });
        const res = await response.json();
        
        if (response.ok) {
            logToTerminal("Configuration de l'essaim mise à jour à chaud avec succès !");
            await reloadSwarmConfig();
            loadConfigAgentsPane();
        } else {
            alert("Erreur de sauvegarde: " + res.detail);
        }
    } catch (err) {
        alert("Erreur réseau lors de la sauvegarde: " + err);
    }
}

// =========================================================================
// INITIALISATION
// =========================================================================
// =========================================================================
// INITIALISATION & GESTION VOCALE (STT & TTS)
// =========================================================================
let isVoiceTtsEnabled = false;
let currentUtterance = null;
let recognition = null;
let isMicRecording = false;

function speakText(text, agentName) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    
    // Nettoyer les balises HTML et markdown simples pour la lecture vocale
    let cleanText = text.replace(/<[^>]*>/g, "").replace(/[\*_`#]/g, "");
    
    const utterance = new SpeechSynthesisUtterance(cleanText);
    const voices = window.speechSynthesis.getVoices();
    const frVoice = voices.find(v => v.lang.startsWith("fr") || v.lang.includes("FR"));
    if (frVoice) utterance.voice = frVoice;
    
    // Adapter la voix et le ton selon l'agent
    if (agentName === "Jarvis") {
        utterance.pitch = 1.0;
        utterance.rate = 1.05;
    } else if (agentName === "Codeur") {
        utterance.pitch = 0.9;
        utterance.rate = 1.15;
    } else if (agentName === "Auteur") {
        utterance.pitch = 1.15;
        utterance.rate = 0.95;
    } else {
        utterance.pitch = 1.0;
        utterance.rate = 1.0;
    }
    
    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
}

function initSpeech() {
    // Bouton Voix ON/OFF dans le Header
    const btnVoiceToggle = document.getElementById("btn-voice-toggle");
    if (btnVoiceToggle) {
        btnVoiceToggle.style.transition = "all 0.3s";
        btnVoiceToggle.addEventListener("click", () => {
            isVoiceTtsEnabled = !isVoiceTtsEnabled;
            if (isVoiceTtsEnabled) {
                btnVoiceToggle.textContent = "🔊 Voix ON";
                btnVoiceToggle.style.backgroundColor = "rgba(16, 185, 129, 0.2)";
                btnVoiceToggle.style.borderColor = "var(--success-color)";
                speakText("Lecture vocale activée. Bonjour !", orchestratorName());
            } else {
                btnVoiceToggle.textContent = "🔇 Voix OFF";
                btnVoiceToggle.style.backgroundColor = "";
                btnVoiceToggle.style.borderColor = "";
                if (window.speechSynthesis) window.speechSynthesis.cancel();
            }
        });
    }
    
    // Configuration Speech Recognition (Reconnaissance vocale)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.lang = 'fr-FR';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        
        const btnMic = document.getElementById("btn-mic");
        
        recognition.onstart = () => {
            isMicRecording = true;
            btnMic.style.opacity = "1";
            btnMic.style.color = "#ef4444";
            btnMic.style.transform = "scale(1.3)";
            btnMic.title = "En écoute... Cliquez pour arrêter";
            chatInput.placeholder = orchestratorName() + " t'écoute... Parle maintenant 🎙️";
        };
        
        recognition.onend = () => {
            isMicRecording = false;
            btnMic.style.opacity = "0.7";
            btnMic.style.color = "var(--text-color)";
            btnMic.style.transform = "none";
            btnMic.title = "Parler à l'essaim (Speech-to-Text)";
            chatInput.placeholder = "Discutez avec " + orchestratorName() + " ou demandez-lui d'activer une équipe...";
        };
        
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            chatInput.value = transcript;
            
            // Soumission automatique après transcription
            setTimeout(() => {
                chatForm.dispatchEvent(new Event("submit"));
            }, 500);
        };
        
        recognition.onerror = (err) => {
            console.error("Speech Recognition Error:", err);
        };
        
        btnMic.addEventListener("click", () => {
            if (isMicRecording) {
                recognition.stop();
            } else {
                if (window.speechSynthesis) window.speechSynthesis.cancel();
                recognition.start();
            }
        });
    } else {
        // Laisser le bouton visible et expliquer le requis HTTPS/localhost si cliqué !
        const btnMic = document.getElementById("btn-mic");
        if (btnMic) {
            btnMic.style.display = "block";
            btnMic.title = "Dictée vocale non disponible";
            btnMic.addEventListener("click", () => {
                alert("La dictée vocale nécessite un navigateur compatible (comme Google Chrome ou Microsoft Edge) et un contexte sécurisé (connexion HTTPS ou accès via 'localhost'). Si vous utilisez une adresse IP ou un nom de domaine non sécurisé en HTTP, le navigateur bloque l'accès au microphone.");
            });
        }
    }
    
    // Charger les voix du système
    if (window.speechSynthesis) {
        window.speechSynthesis.getVoices();
        if (window.speechSynthesis.onvoiceschanged !== undefined) {
            window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
        }
    }
    
    // Gestion du bouton trombone (attachement de fichiers) dans le chat
    const btnAttach = document.getElementById("btn-chat-attach");
    const chatFileInput = document.getElementById("chat-file-input");
    const chatInputEl = document.getElementById("chat-input");
    
    if (btnAttach && chatFileInput && chatInputEl) {
        btnAttach.addEventListener("click", () => chatFileInput.click());
        
        chatFileInput.addEventListener("change", async () => {
            if (chatFileInput.files.length > 0) {
                await attachFileToMessage(chatFileInput.files[0]);
                chatFileInput.value = ""; // Réinitialiser le sélecteur
            }
        });
    }

    // Gestion du Drag & Drop de fichiers directement sur le conteneur du chat
    const chatMessagesContainer = document.getElementById("chat-messages");
    if (chatMessagesContainer) {
        chatMessagesContainer.addEventListener("dragover", (e) => {
            e.preventDefault();
            chatMessagesContainer.style.background = "rgba(0, 240, 255, 0.03)";
        });
        chatMessagesContainer.addEventListener("dragleave", () => {
            chatMessagesContainer.style.background = "";
        });
        chatMessagesContainer.addEventListener("drop", async (e) => {
            e.preventDefault();
            chatMessagesContainer.style.background = "";
            if (e.dataTransfer.files.length > 0) {
                await attachFileToMessage(e.dataTransfer.files[0]);
            }
        });
    }
}

// =========================================================================
// GESTIONNAIRE DE FICHIERS DU WORKSPACE
// =========================================================================
async function loadWorkspaceFiles() {
    const listContainer = document.getElementById("files-list-container");
    if (!listContainer) return;
    
    listContainer.innerHTML = "<div style='padding: 8px; opacity: 0.7;'>Chargement des fichiers...</div>";
    
    try {
        const response = await apiFetch("/api/workspace/files");
        const files = await response.json();
        
        if (files.length === 0) {
            listContainer.innerHTML = "<div style='padding: 8px; opacity: 0.5;'>Aucun fichier trouvé.</div>";
            return;
        }
        
        listContainer.innerHTML = "";
        files.forEach(f => {
            const sizeKb = (f.size / 1024).toFixed(1);
            const item = document.createElement("div");
            item.style.padding = "6px 8px";
            item.style.margin = "4px 0";
            item.style.borderRadius = "4px";
            item.style.cursor = "pointer";
            item.style.transition = "background-color 0.2s";
            item.style.display = "flex";
            item.style.justifyContent = "space-between";
            item.style.alignItems = "center";
            item.className = "file-item-row";
            item.innerHTML = `
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%;" title="${f.path}">📄 ${f.path}</span>
                <span style="font-size: 0.75rem; opacity: 0.5;">${sizeKb} KB</span>
            `;
            
            item.addEventListener("mouseenter", () => item.style.backgroundColor = "rgba(255,255,255,0.08)");
            item.addEventListener("mouseleave", () => item.style.backgroundColor = "");
            
            item.addEventListener("click", () => {
                document.querySelectorAll(".file-item-row").forEach(el => el.style.borderLeft = "");
                item.style.borderLeft = "3px solid var(--accent-color)";
                viewWorkspaceFile(f.path);
            });
            
            listContainer.appendChild(item);
        });
    } catch (err) {
        listContainer.innerHTML = `<div style='padding: 8px; color: var(--error-color);'>Erreur: ${err}</div>`;
    }
}

let activeSelectedFilePath = null;

async function viewWorkspaceFile(filePath) {
    const titleEl = document.getElementById("file-viewer-title");
    const preEl = document.getElementById("file-viewer-pre");
    const downloadBtn = document.getElementById("btn-download-file");
    
    titleEl.textContent = `Lecture de ${filePath}... ⏳`;
    preEl.textContent = "";
    downloadBtn.style.display = "none";
    activeSelectedFilePath = filePath;
    
    try {
        const response = await apiFetch(`/api/workspace/file?path=${encodeURIComponent(filePath)}`);
        const data = await response.json();
        
        if (response.ok) {
            titleEl.textContent = `📄 ${filePath}`;
            
            // Déterminer la classe de coloration de syntaxe PrismJS selon l'extension
            const ext = (filePath.split('.').pop() || "").toLowerCase();
            let langClass = "language-plaintext";
            
            if (ext === "js" || ext === "mjs") langClass = "language-javascript";
            else if (ext === "py") langClass = "language-python";
            else if (ext === "html") langClass = "language-html";
            else if (ext === "css") langClass = "language-css";
            else if (ext === "json") langClass = "language-json";
            else if (ext === "sh" || ext === "bash") langClass = "language-bash";
            else if (ext === "md" || ext === "markdown") langClass = "language-markdown";
            
            // Injecter la structure <code> et colorer
            preEl.innerHTML = `<code class="${langClass}"></code>`;
            const codeEl = preEl.querySelector("code");
            codeEl.textContent = data.content;
            
            if (typeof Prism !== "undefined") {
                Prism.highlightElement(codeEl);
            }
            
            downloadBtn.style.display = "block";
        } else {
            titleEl.textContent = "⚠️ Erreur de chargement";
            preEl.textContent = data.detail || "Impossible de lire ce fichier.";
        }
    } catch (err) {
        titleEl.textContent = "⚠️ Erreur réseau";
        preEl.textContent = err;
    }
}

// Bouton de téléchargement
const downloadBtn = document.getElementById("btn-download-file");
if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
        if (activeSelectedFilePath) {
            window.open(`/api/workspace/download?path=${encodeURIComponent(activeSelectedFilePath)}`, "_blank");
        }
    });
}

// Zone de téléversement (Drag & Drop + Clic)
const dropzone = document.getElementById("upload-dropzone");
const uploadInput = document.getElementById("file-upload-input");

if (dropzone && uploadInput) {
    dropzone.addEventListener("click", () => uploadInput.click());
    
    uploadInput.addEventListener("change", async () => {
        if (uploadInput.files.length > 0) {
            await uploadFileToServer(uploadInput.files[0]);
        }
    });
    
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "var(--accent-color)";
        dropzone.style.backgroundColor = "rgba(255,255,255,0.05)";
    });
    
    dropzone.addEventListener("dragleave", () => {
        dropzone.style.borderColor = "rgba(255,255,255,0.15)";
        dropzone.style.backgroundColor = "";
    });
    
    dropzone.addEventListener("drop", async (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "rgba(255,255,255,0.15)";
        dropzone.style.backgroundColor = "";
        
        if (e.dataTransfer.files.length > 0) {
            await uploadFileToServer(e.dataTransfer.files[0]);
        }
    });
}

async function uploadFileToServer(file) {
    const listContainer = document.getElementById("files-list-container");
    const origHtml = listContainer.innerHTML;
    listContainer.innerHTML = `<div style='padding: 8px; opacity: 0.7;'>Téléversement de ${file.name}... ⏳</div>`;
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await apiFetch("/api/workspace/upload", {
            method: "POST",
            body: formData
        });
        const res = await response.json();
        
        if (response.ok) {
            logToTerminal(`Fichier '${file.name}' téléversé avec succès.`, "success");
            if (res.ingested && res.report) {
                // Log le rapport d'ingestion RAG (découpage intelligent en morceaux) dans la console de l'essaim
                logToTerminal(res.report, "success");
            }
            await loadWorkspaceFiles();
            viewWorkspaceFile(file.name);
        } else {
            alert("Erreur de téléversement : " + res.detail);
            listContainer.innerHTML = origHtml;
        }
    } catch (err) {
        alert("Erreur réseau de téléversement : " + err);
        listContainer.innerHTML = origHtml;
    }
}

// =========================================================================
// GESTION DE L'AGENDA (NEW INTERACTIVE VIEW !)
// =========================================================================
async function loadAgendaEvents() {
    const listContainer = document.getElementById("agenda-list");
    if (!listContainer) return;
    
    listContainer.innerHTML = "<div style='padding: 8px; opacity: 0.7;'>Chargement des événements...</div>";
    
    try {
        const response = await apiFetch("/api/agenda");
        const events = await response.json();
        
        if (events.length === 0) {
            listContainer.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 24px 0; opacity: 0.5;">
                    <span style="font-size: 2rem;">📅</span>
                    <span>Aucun événement ou rendez-vous enregistré.</span>
                </div>`;
            return;
        }
        
        listContainer.innerHTML = "";
        
        // Obtenir la date/heure actuelle
        const now = new Date();
        
        // Mettre à jour dynamiquement le badge de l'agenda (événements futurs)
        const badgeAgenda = document.getElementById("badge-agenda");
        if (badgeAgenda) {
            const pendingCount = events.filter(e => new Date(e.datetime.replace(" ", "T")) >= now).length;
            badgeAgenda.textContent = pendingCount;
            badgeAgenda.style.display = pendingCount > 0 ? "flex" : "none";
        }
        
        events.forEach(e => {
            const eventCard = document.createElement("div");
            eventCard.className = "agenda-item glass";
            
            // Calculer si l'événement est passé
            const eventDate = new Date(e.datetime.replace(" ", "T"));
            const isPast = eventDate < now;
            
            eventCard.style.border = "1px solid rgba(255, 255, 255, 0.08)";
            eventCard.style.borderRadius = "8px";
            eventCard.style.padding = "10px 12px";
            eventCard.style.display = "flex";
            eventCard.style.justifyContent = "space-between";
            eventCard.style.alignItems = "center";
            eventCard.style.background = isPast ? "rgba(255,255,255,0.01)" : "rgba(255,255,255,0.04)";
            eventCard.style.opacity = isPast ? "0.5" : "1";
            if (!isPast) {
                eventCard.style.boxShadow = "0 2px 10px rgba(0, 240, 255, 0.05)";
                eventCard.style.borderLeft = "3px solid var(--accent-color)";
            } else {
                eventCard.style.borderLeft = "3px solid rgba(255, 255, 255, 0.2)";
            }
            
            eventCard.innerHTML = `
                <div style="display: flex; flex-direction: column; gap: 4px; text-align: left;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <strong style="color: ${isPast ? 'rgba(255,255,255,0.8)' : '#fff'};">${e.title}</strong>
                        <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.7);">${e.duration_minutes} min</span>
                    </div>
                    <span style="font-size: 0.75rem; color: var(--success-color); font-weight: 500;">📅 ${e.datetime}</span>
                    ${e.description ? `<p style="margin: 2px 0 0 0; font-size: 0.75rem; opacity: 0.7; line-height: 1.3;">${e.description}</p>` : ''}
                </div>
                <button class="btn btn-icon" onclick="deleteAgendaEvent('${e.id}')" title="Supprimer ce rendez-vous" style="padding: 4px 8px; font-size: 0.8rem; color: #ff5555; background: transparent; border: none; cursor: pointer; transition: transform 0.2s;">❌</button>
            `;
            
            listContainer.appendChild(eventCard);
        });
    } catch (err) {
        listContainer.innerHTML = `<div style='padding: 8px; color: #ff5555;'>Erreur de chargement : ${err}</div>`;
    }
}

async function submitNewAgendaEvent() {
    const titleInput = document.getElementById("agenda-title");
    const dateInput = document.getElementById("agenda-date");
    const durationInput = document.getElementById("agenda-duration");
    const descInput = document.getElementById("agenda-description");
    
    const payload = {
        title: titleInput.value.trim(),
        datetime_str: dateInput.value.trim(),
        duration_minutes: parseInt(durationInput.value) || 60,
        description: descInput.value.trim()
    };
    
    try {
        const response = await apiFetch("/api/agenda", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const res = await response.json();
        
        if (response.ok) {
            logToTerminal("Nouveau rendez-vous enregistré : " + payload.title, "success");
            titleInput.value = "";
            dateInput.value = "";
            descInput.value = "";
            loadAgendaEvents();
        } else {
            alert("Erreur : " + res.detail);
        }
    } catch (err) {
        alert("Erreur réseau : " + err);
    }
}

async function deleteAgendaEvent(id) {
    if (!confirm("Supprimer ce rendez-vous de votre agenda ?")) return;
    
    try {
        const response = await apiFetch(`/api/agenda/${id}`, {
            method: "DELETE"
        });
        const res = await response.json();
        
        if (response.ok) {
            logToTerminal("Rendez-vous supprimé de l'agenda.", "success");
            loadAgendaEvents();
        } else {
            alert("Erreur : " + res.detail);
        }
    } catch (err) {
        alert("Erreur réseau : " + err);
    }
}

// =========================================================================
// SYNCHRONISATION AGENDA EXTERNE (RÉGLABLE VIA INTERFACE WEB)
// =========================================================================
async function loadAgendaConfig() {
    try {
        const response = await apiFetch("/api/config/agenda");
        const config = await response.json();
        
        document.getElementById("agenda-ical-url").value = config.external_ical_url || "";
        document.getElementById("agenda-google-id").value = config.google_calendar_id || "";
        document.getElementById("agenda-caldav-url").value = config.caldav_url || "";
        document.getElementById("agenda-caldav-user").value = config.caldav_username || "";
        
        // Gérer le mot de passe CalDAV masqué
        const pwdInput = document.getElementById("agenda-caldav-password");
        if (config.caldav_password) {
            pwdInput.value = config.caldav_password;
        } else {
            pwdInput.value = "";
        }
        
        // Mettre à jour l'étiquette Google credentials JSON
        const statusSpan = document.getElementById("agenda-google-status");
        if (config.has_google_credentials) {
            statusSpan.innerHTML = "Clé configurée ✅";
            statusSpan.style.color = "var(--success-color)";
        } else {
            statusSpan.innerHTML = "Clé absente ❌";
            statusSpan.style.color = "#ff5555";
        }
    } catch (err) {
        console.error("Erreur lors de la récupération des paramètres agenda :", err);
    }
}

// Enregistrer les variables agenda (.env)
const agendaSyncForm = document.getElementById("agenda-sync-form");
if (agendaSyncForm) {
    agendaSyncForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const payload = {
            external_ical_url: document.getElementById("agenda-ical-url").value.trim(),
            google_calendar_id: document.getElementById("agenda-google-id").value.trim(),
            caldav_url: document.getElementById("agenda-caldav-url").value.trim(),
            caldav_username: document.getElementById("agenda-caldav-user").value.trim(),
            caldav_password: document.getElementById("agenda-caldav-password").value.trim()
        };
        
        try {
            const response = await apiFetch("/api/config/agenda", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const res = await response.json();
            
            if (response.ok) {
                logToTerminal("Paramètres d'agenda synchronisés et enregistrés avec succès !", "success");
                alert("Paramètres d'agenda enregistrés ! Synchronisation lancée...");
                loadAgendaEvents();
                settingsModal.style.display = "none";
            } else {
                alert("Erreur de sauvegarde agenda : " + res.detail);
            }
        } catch (err) {
            alert("Erreur réseau : " + err);
        }
    });
}

// Gérer le téléversement du fichier Google Credentials JSON
const googleFileInput = document.getElementById("agenda-google-file");
if (googleFileInput) {
    googleFileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append("file", file);
        
        try {
            const response = await apiFetch("/api/config/agenda/google-key", {
                method: "POST",
                body: formData
            });
            const res = await response.json();
            
            if (response.ok) {
                logToTerminal("Fichier google_credentials.json téléversé avec succès !", "success");
                alert("Clé Google Credentials JSON téléversée avec succès !");
                loadAgendaConfig();
            } else {
                alert("Erreur lors du téléversement de la clé Google : " + res.detail);
            }
        } catch (err) {
            alert("Erreur réseau de clé Google : " + err);
        }
    });
}

// Synchronisation manuelle (Bouton Synchro de la vue Agenda)
const btnSyncAgenda = document.getElementById("btn-sync-agenda");
if (btnSyncAgenda) {
    btnSyncAgenda.addEventListener("click", async () => {
        const origText = btnSyncAgenda.innerHTML;
        btnSyncAgenda.innerHTML = "Synchro... ⏳";
        btnSyncAgenda.disabled = true;
        
        try {
            const response = await apiFetch("/api/agenda/sync", { method: "POST" });
            const res = await response.json();
            
            if (response.ok) {
                logToTerminal(res.message, "success");
                loadAgendaEvents();
            } else {
                alert("Erreur de synchro : " + res.detail);
            }
        } catch (err) {
            alert("Erreur réseau de synchro : " + err);
        } finally {
            btnSyncAgenda.innerHTML = origText;
            btnSyncAgenda.disabled = false;
        }
    });
}

// Hooks de l'actualisation
document.getElementById("btn-refresh-files").addEventListener("click", loadWorkspaceFiles);
const btnRefreshAgenda = document.getElementById("btn-refresh-agenda");
if (btnRefreshAgenda) {
    btnRefreshAgenda.addEventListener("click", loadAgendaEvents);
}
const btnRefreshBranches = document.getElementById("btn-refresh-branches");
if (btnRefreshBranches) {
    btnRefreshBranches.addEventListener("click", () => reloadChatHistory(false));
}

// =========================================================================
// GESTION DES LISTES UNIVERSELLES (NEW INTERACTIVE CHECKLISTS !)
// =========================================================================
const subTabEvents = document.getElementById("agenda-sub-tab-events");
const subTabLists = document.getElementById("agenda-sub-tab-lists");
const paneEvents = document.getElementById("agenda-sub-pane-events");
const paneLists = document.getElementById("agenda-sub-pane-lists");

if (subTabEvents && subTabLists && paneEvents && paneLists) {
    subTabEvents.addEventListener("click", () => {
        subTabEvents.className = "btn active";
        subTabEvents.style.background = "rgba(255,255,255,0.08)";
        subTabEvents.style.color = "#fff";
        
        subTabLists.className = "btn";
        subTabLists.style.background = "transparent";
        subTabLists.style.color = "#aaa";
        
        paneEvents.style.display = "flex";
        paneLists.style.display = "none";
        
        loadAgendaEvents();
    });

    subTabLists.addEventListener("click", () => {
        subTabLists.className = "btn active";
        subTabLists.style.background = "rgba(255,255,255,0.08)";
        subTabLists.style.color = "#fff";
        
        subTabEvents.className = "btn";
        subTabEvents.style.background = "transparent";
        subTabEvents.style.color = "#aaa";
        
        paneEvents.style.display = "none";
        paneLists.style.display = "flex";
        
        loadListItems();
    });
}

const listSelector = document.getElementById("active-list-selector");
if (listSelector) {
    listSelector.addEventListener("change", loadListItems);
}

const btnRefreshLists = document.getElementById("btn-refresh-lists");
if (btnRefreshLists) {
    btnRefreshLists.addEventListener("click", loadListItems);
}

async function loadListItems() {
    const listContainer = document.getElementById("list-items-container");
    const activeList = document.getElementById("active-list-selector").value;
    if (!listContainer) return;
    
    listContainer.innerHTML = "<div style='padding: 8px; opacity: 0.7;'>Chargement des éléments...</div>";
    
    try {
        const response = await apiFetch(`/api/lists?list_name=${activeList}`);
        const items = await response.json();
        
        if (items.length === 0) {
            listContainer.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 24px 0; opacity: 0.5;">
                    <span style="font-size: 2rem;">📋</span>
                    <span>Cette liste est vide.</span>
                </div>`;
            return;
        }
        
        listContainer.innerHTML = "";
        
        items.forEach(item => {
            const itemRow = document.createElement("div");
            itemRow.className = "list-item glass";
            
            itemRow.style.border = "1px solid rgba(255, 255, 255, 0.08)";
            itemRow.style.borderRadius = "6px";
            itemRow.style.padding = "8px 10px";
            itemRow.style.display = "flex";
            itemRow.style.justifyContent = "space-between";
            itemRow.style.alignItems = "center";
            itemRow.style.background = item.completed ? "rgba(255,255,255,0.01)" : "rgba(255,255,255,0.04)";
            
            const checkIcon = item.completed ? "☑️" : "⬜";
            const strikeStyle = item.completed ? "text-decoration: line-through; opacity: 0.5;" : "";
            
            itemRow.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer; text-align: left;" onclick="toggleListItem('${item.id}')">
                    <span style="font-size: 1.1rem; user-select: none;">${checkIcon}</span>
                    <span style="${strikeStyle} font-size: 0.85rem; color: #fff;">${item.text}</span>
                </div>
                <button class="btn-icon" style="padding: 2px 6px; font-size: 0.8rem; background: rgba(255,0,0,0.15); border: 1px solid rgba(255,0,0,0.3); color: #ff5555; border-radius: 4px;" onclick="deleteListItem('${item.id}')" title="Supprimer">🗑️</button>
            `;
            
            listContainer.appendChild(itemRow);
        });
    } catch (err) {
        listContainer.innerHTML = `<div style="padding: 8px; color: var(--danger-color);">Erreur de chargement : ${err}</div>`;
    }
}

async function submitNewListItem() {
    const activeList = document.getElementById("active-list-selector").value;
    const inputField = document.getElementById("list-item-input");
    const text = inputField.value.strip ? inputField.value.strip() : inputField.value.trim();
    if (!text) return;
    
    try {
        const response = await apiFetch("/api/lists", {
            method: "POST",
            body: JSON.stringify({ list_name: activeList, text: text })
        });
        
        if (response.ok) {
            inputField.value = "";
            loadListItems();
        } else {
            const err = await response.json();
            alert("Erreur de création : " + err.detail);
        }
    } catch (err) {
        alert("Erreur réseau : " + err);
    }
}

async function toggleListItem(itemId) {
    const activeList = document.getElementById("active-list-selector").value;
    try {
        const response = await apiFetch(`/api/lists/${activeList}/${itemId}/toggle`, {
            method: "PUT"
        });
        if (response.ok) {
            loadListItems();
        }
    } catch (err) {
        console.error("Erreur toggle item :", err);
    }
}

async function deleteListItem(itemId) {
    if (!confirm("Voulez-vous vraiment supprimer cet élément ?")) return;
    
    const activeList = document.getElementById("active-list-selector").value;
    try {
        const response = await apiFetch(`/api/lists/${activeList}/${itemId}`, {
            method: "DELETE"
        });
        if (response.ok) {
            loadListItems();
        }
    } catch (err) {
        console.error("Erreur suppression item :", err);
    }
}

// Exposer les fonctions globales pour le DOM onclick
window.toggleListItem = toggleListItem;
window.deleteListItem = deleteListItem;
window.submitNewListItem = submitNewListItem;

async function init() {
    await reloadSwarmConfig();
    await refreshMemory();
    await loadWorkspaceConfig();
    loadWorkspaceFiles();
    loadAgendaEvents();
    loadListItems();
    logToTerminal("Dashboard No-Code, Bureau Virtuel, Agenda et Listes connectés.");
    setActiveAgentVisual(orchestratorName());
    initSpeech();
}

init();

// GESTION DYNAMIQUE DE L'AGRANDISSEMENT DU PANNEAU GAUCHE
const btnToggleLeftExpand = document.getElementById("btn-toggle-left-expand");
const appContainer = document.querySelector(".app-container");
let isLeftExpanded = false;

if (btnToggleLeftExpand && appContainer) {
    btnToggleLeftExpand.addEventListener("click", () => {
        isLeftExpanded = !isLeftExpanded;
        if (isLeftExpanded) {
            appContainer.style.setProperty("--left-panel-width", "600px");
            btnToggleLeftExpand.innerHTML = "↔️ Collapse";
            btnToggleLeftExpand.style.background = "rgba(0, 240, 255, 0.2)";
        } else {
            appContainer.style.setProperty("--left-panel-width", "350px");
            btnToggleLeftExpand.innerHTML = "↔️ Expand";
            btnToggleLeftExpand.style.background = "";
        }
    });
}

// GESTION DU DOSSIER DE TRAVAIL ACTIF (WORKSPACE TARGET FOLDER)
const workspacePathInput = document.getElementById("workspace-path-input");
const btnSaveWorkspacePath = document.getElementById("btn-save-workspace-path");

async function loadWorkspaceConfig() {
    try {
        const response = await apiFetch("/api/workspace/config");
        if (response.ok) {
            const data = await response.json();
            if (workspacePathInput) {
                workspacePathInput.value = data.active_workspace_dir;
            }
            logToTerminal(`Dossier de travail actif connecté : ${data.active_workspace_dir}`, "system");
        }
    } catch (err) {
        console.error("Erreur lors du chargement de la config workspace:", err);
    }
}

async function saveWorkspaceConfig() {
    if (!workspacePathInput) return;
    const targetPath = workspacePathInput.value.trim();
    if (!targetPath) return;
    
    if (btnSaveWorkspacePath) btnSaveWorkspacePath.disabled = true;
    
    try {
        const response = await apiFetch("/api/workspace/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: targetPath })
        });
        
        const data = await response.json();
        if (response.ok) {
            logToTerminal(`📁 Dossier de travail repositionné avec succès sur : ${data.active_workspace_dir}`, "system");
            workspacePathInput.value = data.active_workspace_dir;
            
            // Recharger la liste des fichiers du projet
            loadWorkspaceFiles();
        } else {
            logToTerminal(`Erreur changement de dossier : ${data.detail}`, "error");
        }
    } catch (err) {
        logToTerminal(`Erreur réseau : ${err}`, "error");
    } finally {
        if (btnSaveWorkspacePath) btnSaveWorkspacePath.disabled = false;
    }
}

if (btnSaveWorkspacePath) {
    btnSaveWorkspacePath.addEventListener("click", saveWorkspaceConfig);
}
if (workspacePathInput) {
    workspacePathInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            saveWorkspaceConfig();
        }
    });
}

// SYSTÈME DE NAVIGATION ET D'AUTOCAMPÉTITION DE DOSSIERS VISUELLE
const workspaceSuggestions = document.getElementById("workspace-path-suggestions");

async function showWorkspacePathSuggestions() {
    if (!workspacePathInput || !workspaceSuggestions) return;
    const currentVal = workspacePathInput.value.trim();
    
    try {
        const response = await apiFetch(`/api/workspace/dirs?path=${encodeURIComponent(currentVal)}`);
        if (response.ok) {
            const data = await response.json();
            workspaceSuggestions.innerHTML = "";
            workspaceSuggestions.style.display = "block";
            
            // 1. Ajouter l'option Dossier Parent ".." si on n'est pas à la racine du système
            if (data.parent_path && data.parent_path !== data.current_path) {
                const parentDiv = document.createElement("div");
                parentDiv.style.cssText = "padding: 6px 8px; font-family: monospace; font-size: 0.75rem; border-radius: 4px; color: #38bdf8; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.2s;";
                parentDiv.innerHTML = "<span>📁</span> <strong>.. (Remonter d'un dossier)</strong>";
                parentDiv.addEventListener("click", () => {
                    workspacePathInput.value = data.parent_path;
                    showWorkspacePathSuggestions(); // Rafraîchir
                });
                parentDiv.addEventListener("mouseenter", () => {
                    parentDiv.style.background = "rgba(255,255,255,0.08)";
                });
                parentDiv.addEventListener("mouseleave", () => {
                    parentDiv.style.background = "";
                });
                workspaceSuggestions.appendChild(parentDiv);
            }
            
            // 2. Ajouter tous les sous-dossiers trouvés
            if (data.subdirs.length === 0) {
                const emptyDiv = document.createElement("div");
                emptyDiv.style.cssText = "padding: 6px 8px; font-size: 0.7rem; color: rgba(255,255,255,0.4); font-style: italic;";
                emptyDiv.innerText = "Aucun sous-dossier trouvé.";
                workspaceSuggestions.appendChild(emptyDiv);
            } else {
                data.subdirs.forEach(sub => {
                    const subDiv = document.createElement("div");
                    subDiv.style.cssText = "padding: 6px 8px; font-family: monospace; font-size: 0.75rem; border-radius: 4px; color: #fff; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background 0.2s;";
                    subDiv.innerHTML = `<span>📁</span> <span>${sub}</span>`;
                    subDiv.addEventListener("click", () => {
                        const separator = data.current_path.endsWith("/") || data.current_path.endsWith("\\") ? "" : "/";
                        workspacePathInput.value = data.current_path + separator + sub;
                        showWorkspacePathSuggestions(); // Descendre dans ce dossier et rafraîchir !
                    });
                    subDiv.addEventListener("mouseenter", () => {
                        subDiv.style.background = "rgba(255,255,255,0.08)";
                    });
                    subDiv.addEventListener("mouseleave", () => {
                        subDiv.style.background = "";
                    });
                    workspaceSuggestions.appendChild(subDiv);
                });
            }
        }
    } catch (err) {
        console.error("Erreur suggestions dossier:", err);
    }
}

if (workspacePathInput) {
    workspacePathInput.addEventListener("focus", showWorkspacePathSuggestions);
    workspacePathInput.addEventListener("input", showWorkspacePathSuggestions);
}

// Fermer les suggestions lors d'un clic en dehors
document.addEventListener("click", (e) => {
    if (workspaceSuggestions && workspacePathInput) {
        if (!workspacePathInput.contains(e.target) && !workspaceSuggestions.contains(e.target)) {
            workspaceSuggestions.style.display = "none";
        }
    }
});

// GESTION DU TERMINAL INTERACTIF CODER (Claude Code / OpenCode style)
const terminalCoderInput = document.getElementById("terminal-coder-input");
const btnSendTerminal = document.getElementById("btn-send-terminal");

async function executeTerminalCommand() {
    if (!terminalCoderInput) return;
    const command = terminalCoderInput.value.trim();
    if (!command) return;
    
    terminalCoderInput.disabled = true;
    if (btnSendTerminal) btnSendTerminal.disabled = true;
    terminalCoderInput.value = "";
    
    // Afficher la commande tapée dans la console avec style
    const agentSelect = document.getElementById("terminal-agent-select");
    const selectedAgent = agentSelect ? agentSelect.value : "Codeur";
    logToTerminal(`$ jarvis-${selectedAgent.toLowerCase()} > ${command}`, "transition");
    
    try {
        const response = await apiFetch("/api/terminal/coder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command: command, agent: selectedAgent })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Jouer les étapes d'exécution de l'Agent Codeur dans le terminal de logs
            await playAgentSteps(data.steps);
            // Recharger l'arbre des conversations
            await reloadChatHistory(true);
            await refreshMemory();
        } else {
            logToTerminal("Erreur terminal: " + data.detail, "error");
        }
    } catch (err) {
        logToTerminal("Erreur de connexion terminal: " + err, "error");
    } finally {
        terminalCoderInput.disabled = false;
        if (btnSendTerminal) btnSendTerminal.disabled = false;
        terminalCoderInput.focus();
    }
}

if (terminalCoderInput) {
    terminalCoderInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            executeTerminalCommand();
        }
    });
}

if (btnSendTerminal) {
    btnSendTerminal.addEventListener("click", () => {
        executeTerminalCommand();
    });
}

// EXPLORATEUR DE DOSSIERS DE TRAVAIL INTERACTIF VISUEL (VISUAL DIRECTORY EXPLORER)
const explorerModal = document.getElementById("explorer-modal");
const explorerDirsList = document.getElementById("explorer-dirs-list");
const explorerCurrentPathSpan = document.getElementById("explorer-current-path");
const btnOpenExplorer = document.getElementById("btn-open-explorer-modal");
const btnCloseExplorer = document.getElementById("btn-close-explorer-modal");
const btnExplorerCancel = document.getElementById("btn-explorer-cancel");
const btnExplorerConfirm = document.getElementById("btn-explorer-confirm");

let explorerActivePath = "";
let explorerSelectedPath = "";

async function loadExplorerPath(path) {
    try {
        const response = await apiFetch(`/api/workspace/dirs?path=${encodeURIComponent(path)}`);
        if (response.ok) {
            const data = await response.json();
            explorerActivePath = data.current_path;
            explorerSelectedPath = data.current_path; // Par défaut, on sélectionne le dossier actif actuel
            
            if (explorerCurrentPathSpan) {
                explorerCurrentPathSpan.innerText = data.current_path;
            }
            
            if (explorerDirsList) {
                explorerDirsList.innerHTML = "";
                
                // 1. Dossier Parent ".." si disponible
                if (data.parent_path && data.parent_path !== data.current_path) {
                    const row = document.createElement("div");
                    row.style.cssText = "padding: 8px 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 8px; color: #38bdf8; font-family: monospace; font-size: 0.8rem; user-select: none; transition: background 0.2s;";
                    row.innerHTML = "<span>📁</span> <strong>.. (Dossier Parent)</strong>";
                    
                    row.addEventListener("mouseenter", () => row.style.background = "rgba(255,255,255,0.05)");
                    row.addEventListener("mouseleave", () => row.style.background = "");
                    row.addEventListener("click", () => {
                        // Un simple clic sélectionne le dossier parent
                        explorerSelectedPath = data.parent_path;
                        clearExplorerSelections();
                        row.style.background = "rgba(56, 189, 248, 0.15)";
                        row.style.border = "1px solid rgba(56, 189, 248, 0.3)";
                    });
                    row.addEventListener("dblclick", () => {
                        loadExplorerPath(data.parent_path);
                    });
                    
                    explorerDirsList.appendChild(row);
                }
                
                // 2. Liste des sous-dossiers
                if (data.subdirs.length === 0) {
                    const empty = document.createElement("div");
                    empty.style.cssText = "padding: 12px; font-size: 0.75rem; color: rgba(255,255,255,0.4); text-align: center; font-style: italic;";
                    empty.innerText = "Aucun sous-dossier dans ce répertoire.";
                    explorerDirsList.appendChild(empty);
                } else {
                    data.subdirs.forEach(subdir => {
                        const row = document.createElement("div");
                        row.className = "explorer-dir-row";
                        row.style.cssText = "padding: 8px 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 8px; color: #fff; font-family: monospace; font-size: 0.8rem; user-select: none; transition: all 0.2s; border: 1px solid transparent;";
                        row.innerHTML = `<span>📁</span> <span>${subdir}</span>`;
                        
                        row.addEventListener("mouseenter", () => {
                            if (!row.classList.contains("selected")) {
                                row.style.background = "rgba(255,255,255,0.05)";
                            }
                        });
                        row.addEventListener("mouseleave", () => {
                            if (!row.classList.contains("selected")) {
                                row.style.background = "";
                            }
                        });
                        row.addEventListener("click", () => {
                            clearExplorerSelections();
                            row.classList.add("selected");
                            row.style.background = "rgba(0, 240, 255, 0.12)";
                            row.style.borderColor = "rgba(0, 240, 255, 0.3)";
                            
                            const separator = explorerActivePath.endsWith("/") || explorerActivePath.endsWith("\\") ? "" : "/";
                            explorerSelectedPath = explorerActivePath + separator + subdir;
                        });
                        row.addEventListener("dblclick", () => {
                            const separator = explorerActivePath.endsWith("/") || explorerActivePath.endsWith("\\") ? "" : "/";
                            loadExplorerPath(explorerActivePath + separator + subdir);
                        });
                        
                        explorerDirsList.appendChild(row);
                    });
                }
            }
        }
    } catch (err) {
        console.error("Erreur lors de la lecture du répertoire dans l'explorateur:", err);
    }
}

function clearExplorerSelections() {
    if (!explorerDirsList) return;
    const rows = explorerDirsList.querySelectorAll(".explorer-dir-row, div");
    rows.forEach(r => {
        r.classList.remove("selected");
        r.style.background = "";
        r.style.borderColor = "transparent";
        r.style.border = "none";
    });
}

if (btnOpenExplorer) {
    btnOpenExplorer.addEventListener("click", () => {
        if (explorerModal) {
            explorerModal.style.display = "flex";
            const currentPath = workspacePathInput ? workspacePathInput.value : ".";
            loadExplorerPath(currentPath);
        }
    });
}

function closeExplorerModal() {
    if (explorerModal) {
        explorerModal.style.display = "none";
    }
}

if (btnCloseExplorer) btnCloseExplorer.addEventListener("click", closeExplorerModal);
if (btnExplorerCancel) btnExplorerCancel.addEventListener("click", closeExplorerModal);

if (btnExplorerConfirm) {
    btnExplorerConfirm.addEventListener("click", () => {
        if (workspacePathInput) {
            workspacePathInput.value = explorerSelectedPath;
            saveWorkspaceConfig();
        }
        closeExplorerModal();
    });
}

// CONTRÔLES DE CAMÉRA RTS À LA SOURIS (MOLETTE POUR LE ZOOM, DRAG POUR LA ROTATION)
let isDraggingOffice = false;
let startX = 0;
let startRotation = 0;

if (viewOffice) {
    // 1. Zoom avec la molette de la souris (Wheel Zoom)
    viewOffice.addEventListener("wheel", (e) => {
        e.preventDefault();
        const zoomSpeed = 0.06;
        if (e.deltaY < 0) {
            officeZoomScale = Math.min(2.5, officeZoomScale + zoomSpeed);
        } else {
            officeZoomScale = Math.max(0.4, officeZoomScale - zoomSpeed);
        }
        applyOfficeCameraTransform();
    }, { passive: false });

    // 2. Rotation continue en glissant la souris (Drag Rotation)
    viewOffice.addEventListener("mousedown", (e) => {
        // Ignorer le drag si on clique sur un agent pour le sélectionner
        if (e.target.closest(".agent-desk-iso")) return;
        
        isDraggingOffice = true;
        startX = e.clientX;
        startRotation = officeRotationDeg;
        viewOffice.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
        if (!isDraggingOffice) return;
        const deltaX = e.clientX - startX;
        // Calculer la nouvelle rotation continue de la pièce
        officeRotationDeg = (startRotation + deltaX * 0.4) % 360;
        applyOfficeCameraTransform();
    });

    window.addEventListener("mouseup", () => {
        if (isDraggingOffice) {
            isDraggingOffice = false;
            if (viewOffice) viewOffice.style.cursor = "default";
        }
    });

    // 3. Support des gestes tactiles pour mobiles et tablettes (Touch Rotation)
    viewOffice.addEventListener("touchstart", (e) => {
        if (e.target.closest(".agent-desk-iso")) return;
        if (e.touches.length === 1) {
            isDraggingOffice = true;
            startX = e.touches[0].clientX;
            startRotation = officeRotationDeg;
        }
    }, { passive: true });

    viewOffice.addEventListener("touchmove", (e) => {
        if (!isDraggingOffice || e.touches.length !== 1) return;
        const deltaX = e.touches[0].clientX - startX;
        officeRotationDeg = (startRotation + deltaX * 0.4) % 360;
        applyOfficeCameraTransform();
    }, { passive: true });

    viewOffice.addEventListener("touchend", () => {
        isDraggingOffice = false;
    });
}

// Conserver les boutons physiques en tant que raccourcis d'appoint rapides
const btnOfficeZoomIn = document.getElementById("btn-office-zoom-in");
const btnOfficeZoomOut = document.getElementById("btn-office-zoom-out");
const btnOfficeRotate = document.getElementById("btn-office-rotate");

if (btnOfficeZoomIn) {
    btnOfficeZoomIn.addEventListener("click", () => {
        officeZoomScale = Math.min(2.5, officeZoomScale + 0.2);
        applyOfficeCameraTransform();
    });
}
if (btnOfficeZoomOut) {
    btnOfficeZoomOut.addEventListener("click", () => {
        officeZoomScale = Math.max(0.4, officeZoomScale - 0.2);
        applyOfficeCameraTransform();
    });
}
if (btnOfficeRotate) {
    btnOfficeRotate.addEventListener("click", () => {
        officeRotationDeg = (officeRotationDeg + 45) % 360;
        applyOfficeCameraTransform();
    });
}

// =========================================================================
// GESTION DU COCKPIT, DE LA GALERIE MÉDIA & DES NOTIFICATIONS
// =========================================================================

// Télémétrie & Rafraîchissement
const _btnResetTelemetry = document.getElementById("btn-reset-telemetry");
if (_btnResetTelemetry) _btnResetTelemetry.addEventListener("click", async () => {
    if (!confirm("Remettre à zéro les compteurs (requêtes, outils, tokens, coût) ?")) return;
    try {
        await apiFetch("/api/telemetry/reset", { method: "POST" });
        if (typeof loadCockpitData === "function") loadCockpitData();
        logToTerminal("Compteurs du cockpit remis à zéro.", "system");
    } catch (e) { logToTerminal("Réinitialisation : " + e, "error"); }
});

async function loadCockpitData() {
    try {
        const response = await apiFetch("/api/telemetry");
        if (!response.ok) return;
        const data = await response.json();
        
        // Mettre à jour les statistiques
        document.getElementById("stat-queries").innerText = data.total_queries || 0;
        document.getElementById("stat-tools").innerText = data.tool_calls || 0;
        document.getElementById("stat-tokens").innerText = data.total_tokens ? data.total_tokens.toLocaleString() : 0;
        
        // Afficher le coût exact calculé par le serveur
        const costVal = data.total_cost !== undefined ? data.total_cost.toFixed(4) : ((data.total_tokens || 0) * 0.000015).toFixed(4);
        document.getElementById("stat-cost").innerText = `${costVal} €`;
        
        // Mettre à jour les indicateurs des services connectés
        const servicesList = document.getElementById("cockpit-services");
        if (servicesList) {
            servicesList.innerHTML = "";
            Object.values(data.services).forEach(srv => {
                const item = document.createElement("div");
                item.className = "service-item";
                
                const srvName = document.createElement("div");
                srvName.style.display = "flex";
                srvName.style.alignItems = "center";
                srvName.style.gap = "8px";
                srvName.innerHTML = `<span>${srv.icon}</span> <strong style="color: #fff;">${srv.name}</strong>`;
                
                const srvStatus = document.createElement("span");
                srvStatus.className = `service-status-badge ${srv.status === 'online' || srv.status === 'configured' ? 'online' : 'offline'}`;
                srvStatus.innerText = srv.status === 'online' ? "🟢 En ligne" : srv.status === 'configured' ? "🟡 Configuré" : "🔴 Hors ligne";
                
                item.appendChild(srvName);
                item.appendChild(srvStatus);
                servicesList.appendChild(item);
            });
        }
        
        // Mettre à jour la liste des compétences dynamiques (Skills)
        const skillsList = document.getElementById("cockpit-skills-list");
        const skillsCount = document.getElementById("cockpit-skills-count");
        if (skillsList) {
            try {
                const skillsRes = await apiFetch("/api/config/skills");
                if (skillsRes.ok) {
                    const skillsData = await skillsRes.json();
                    if (skillsCount) skillsCount.innerText = skillsData.length;
                    skillsList.innerHTML = "";
                    if (skillsData.length === 0) {
                        skillsList.innerHTML = `
                            <div style="text-align: center; padding: 12px; opacity: 0.5; font-size: 0.75rem; width: 100%;">
                                ✨ Aucune compétence personnalisée créée pour l'instant.
                            </div>
                        `;
                    } else {
                        skillsData.forEach(sk => {
                            const item = document.createElement("div");
                            item.className = "service-item";
                            item.style.flexDirection = "column";
                            item.style.alignItems = "flex-start";
                            item.style.gap = "4px";
                            item.style.padding = "10px 14px";
                            
                            item.innerHTML = `
                                <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span>🛠️</span>
                                        <strong style="color: var(--accent-cyan); font-family: monospace; font-size: 0.85rem;">${sk.name}()</strong>
                                    </div>
                                    <div style="display: flex; align-items: center; gap: 6px;">
                                        <span style="font-size: 0.65rem; background: rgba(0, 243, 255, 0.08); border: 1px solid rgba(0, 243, 255, 0.2); border-radius: 4px; padding: 1px 6px; color: var(--accent-cyan);">Active</span>
                                        <button class="skill-delete-btn" title="Supprimer cette compétence" data-skill="${sk.name}" style="background: rgba(255,0,80,0.12); border: 1px solid rgba(255,0,80,0.4); color: #ff5b89; border-radius: 4px; padding: 1px 7px; cursor: pointer; font-size: 0.72rem; line-height: 1.4;">🗑️</button>
                                    </div>
                                </div>
                                <span style="font-size: 0.72rem; opacity: 0.8; margin-top: 2px;">${sk.description}</span>
                            `;
                            const delBtn = item.querySelector(".skill-delete-btn");
                            if (delBtn) delBtn.addEventListener("click", () => deleteSkill(sk.name));
                            skillsList.appendChild(item);
                        });
                    }
                }
            } catch (errSk) {
                console.error("Erreur de chargement des skills dans le cockpit :", errSk);
            }
        }
    } catch (err) {
        console.error("Erreur de télémétrie Cockpit :", err);
    }
}

// Suppression d'une compétence (Skill) depuis l'UI
async function deleteSkill(name) {
    if (!confirm(`Supprimer définitivement la compétence « ${name} » ?`)) return;
    try {
        const res = await apiFetch(`/api/config/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            logToTerminal(`Compétence supprimée : ${name}`, "success");
            if (typeof loadCockpitData === "function") loadCockpitData();
        } else {
            alert("Suppression impossible : " + (data.detail || res.status));
        }
    } catch (e) {
        alert("Erreur réseau : " + e);
    }
}

// Galerie Média
async function loadGalleryMedia() {
    const galleryContainer = document.getElementById("cockpit-gallery");
    if (!galleryContainer) return;
    
    galleryContainer.innerHTML = "<div style='grid-column: 1/-1; text-align: center; padding: 16px; opacity: 0.5; font-size: 0.75rem;'>Chargement des créations...</div>";
    
    try {
        const response = await apiFetch("/api/gallery");
        if (!response.ok) {
            galleryContainer.innerHTML = "<div style='grid-column: 1/-1; text-align: center; color: #ff5555; padding: 16px; font-size: 0.75rem;'>Erreur de chargement</div>";
            return;
        }
        const media = await response.json();
        
        if (media.length === 0) {
            galleryContainer.innerHTML = `
                <div style="grid-column: 1/-1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 24px 0; opacity: 0.4;">
                    <span style="font-size: 1.5rem;">🎨</span>
                    <span style="font-size: 0.75rem;">Aucun média généré pour l'instant.</span>
                </div>`;
            return;
        }
        
        galleryContainer.innerHTML = "";
        
        media.forEach(item => {
            const galleryItem = document.createElement("div");
            galleryItem.className = "gallery-item";
            
            // Si c'est une vidéo (GIF), ajouter un badge
            if (item.type === "video") {
                const badge = document.createElement("span");
                badge.className = "gallery-video-badge";
                badge.innerText = "ANIMATION";
                galleryItem.appendChild(badge);
            }
            
            const img = document.createElement("img");
            img.src = item.url;
            img.loading = "lazy";
            
            const overlay = document.createElement("div");
            overlay.className = "gallery-item-overlay";
            
            const btnZoom = document.createElement("button");
            btnZoom.className = "gallery-btn-icon";
            btnZoom.innerHTML = "🔍";
            btnZoom.title = "Agrandir";
            btnZoom.onclick = (e) => {
                e.stopPropagation();
                openLightbox(item.url, item.name);
            };
            
            const btnDL = document.createElement("a");
            btnDL.className = "gallery-btn-icon";
            btnDL.innerHTML = "💾";
            btnDL.title = "Télécharger";
            btnDL.href = item.url;
            btnDL.download = item.name;
            btnDL.onclick = (e) => e.stopPropagation();
            
            const btnDel = document.createElement("button");
            btnDel.className = "gallery-btn-icon";
            btnDel.style.backgroundColor = "rgba(255, 68, 68, 0.25)";
            btnDel.innerHTML = "🗑️";
            btnDel.title = "Supprimer";
            btnDel.onclick = async (e) => {
                e.stopPropagation();
                if (confirm(`Voulez-vous vraiment supprimer définitivement la création "${item.name}" ?`)) {
                    try {
                        const res = await apiFetch("/api/gallery/delete", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ path: item.path })
                        });
                        if (res.ok) {
                            logToTerminal(`Création '${item.name}' supprimée avec succès.`, "info");
                            loadGalleryMedia();
                        } else {
                            const errData = await res.json();
                            logToTerminal(`Erreur lors de la suppression : ${errData.detail}`, "error");
                        }
                    } catch (err) {
                        logToTerminal(`Erreur de connexion : ${err}`, "error");
                    }
                }
            };
            
            overlay.appendChild(btnZoom);
            overlay.appendChild(btnDL);
            overlay.appendChild(btnDel);
            galleryItem.appendChild(img);
            galleryItem.appendChild(overlay);
            
            // Cliquer sur l'item ouvre la lightbox
            galleryItem.onclick = () => openLightbox(item.url, item.name);
            
            galleryContainer.appendChild(galleryItem);
        });
    } catch (err) {
        galleryContainer.innerHTML = `<div style='grid-column: 1/-1; text-align: center; color: #ff5555; padding: 16px; font-size: 0.75rem;'>Exception : ${err}</div>`;
    }
}

// Lightbox pour affichage HD
function openLightbox(url, name) {
    const overlay = document.createElement("div");
    overlay.className = "lightbox-overlay";
    overlay.onclick = () => overlay.remove();
    
    const card = document.createElement("div");
    card.className = "lightbox-card";
    card.onclick = (e) => e.stopPropagation();
    
    const mediaElement = document.createElement("img");
    mediaElement.className = "lightbox-media";
    mediaElement.src = url;
    
    const title = document.createElement("div");
    title.className = "lightbox-title";
    title.innerText = name;
    
    card.appendChild(mediaElement);
    card.appendChild(title);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    
    // Fermeture avec la touche Échap
    const escHandler = (e) => {
        if (e.key === "Escape") {
            overlay.remove();
            document.removeEventListener("keydown", escHandler);
        }
    };
    document.addEventListener("keydown", escHandler);
}

// Centre de Notifications & Toasts
const NOTIFICATION_HISTORY = [];
let UNREAD_NOTIFICATIONS_COUNT = 0;

function pushNotification(title, text, type = "info") {
    const notif = {
        id: Date.now() + Math.random().toString(36).substr(2, 4),
        title,
        text,
        type,
        time: new Date().toLocaleTimeString(),
        unread: true
    };
    
    NOTIFICATION_HISTORY.unshift(notif);
    UNREAD_NOTIFICATIONS_COUNT++;
    
    updateNotificationBadge();
    renderNotificationList();
    
    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
        const toast = document.createElement("div");
        toast.className = `toast-alert ${type}`;
        
        let typeIcon = "ℹ️";
        if (type === "success") typeIcon = "✅";
        if (type === "warning") typeIcon = "⚠️";
        if (type === "error") typeIcon = "🚨";
        
        toast.innerHTML = `
            <span style="font-size: 1.1rem; flex-shrink: 0;">${typeIcon}</span>
            <div style="flex: 1; display: flex; flex-direction: column; gap: 2px; text-align: left;">
                <strong style="color: #fff; font-size: 0.8rem;">${title}</strong>
                <span style="color: rgba(255,255,255,0.7); font-size: 0.72rem;">${text}</span>
            </div>
            <button class="toast-close">×</button>
        `;
        
        toast.querySelector(".toast-close").onclick = () => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(50px) scale(0.9)";
            setTimeout(() => toast.remove(), 300);
        };
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.opacity = "0";
                toast.style.transform = "translateX(50px) scale(0.9)";
                setTimeout(() => toast.remove(), 300);
            }
        }, 5000);
    }
}

function updateNotificationBadge() {
    const badge = document.getElementById("notification-badge");
    if (!badge) return;
    
    if (UNREAD_NOTIFICATIONS_COUNT > 0) {
        badge.innerText = UNREAD_NOTIFICATIONS_COUNT;
        badge.style.display = "block";
    } else {
        badge.style.display = "none";
    }
}

function renderNotificationList() {
    const list = document.getElementById("notification-items-list");
    if (!list) return;
    
    if (NOTIFICATION_HISTORY.length === 0) {
        list.innerHTML = `<div style="padding: 16px; text-align: center; opacity: 0.5; font-size: 0.75rem;">Aucune notification</div>`;
        return;
    }
    
    list.innerHTML = "";
    
    NOTIFICATION_HISTORY.forEach(notif => {
        const item = document.createElement("div");
        item.className = `notification-item ${notif.unread ? 'unread' : ''}`;
        
        let icon = "ℹ️";
        if (notif.type === "success") icon = "✅";
        if (notif.type === "warning") icon = "⚠️";
        if (notif.type === "error") icon = "🚨";
        
        item.innerHTML = `
            <span style="font-size: 1rem; flex-shrink: 0; margin-top: 2px;">${icon}</span>
            <div style="flex: 1; text-align: left;">
                <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 4px; margin-bottom: 2px;">
                    <strong style="color: #fff; font-size: 0.75rem;">${notif.title}</strong>
                    <span style="font-size: 0.6rem; opacity: 0.4;">${notif.time}</span>
                </div>
                <div style="color: rgba(255,255,255,0.7); font-size: 0.7rem; overflow-wrap: anywhere;">${notif.text}</div>
            </div>
        `;
        
        item.onclick = () => {
            if (notif.unread) {
                notif.unread = false;
                UNREAD_NOTIFICATIONS_COUNT = Math.max(0, UNREAD_NOTIFICATIONS_COUNT - 1);
                updateNotificationBadge();
                item.classList.remove("unread");
            }
        };
        
        list.appendChild(item);
    });
}

// Liaison événementielle
const btnNotifications = document.getElementById("btn-notifications");
const notifDropdown = document.getElementById("notification-dropdown");
if (btnNotifications && notifDropdown) {
    btnNotifications.onclick = (e) => {
        e.stopPropagation();
        const shown = notifDropdown.style.display === "block";
        notifDropdown.style.display = shown ? "none" : "block";
        
        if (!shown) {
            NOTIFICATION_HISTORY.forEach(n => n.unread = false);
            UNREAD_NOTIFICATIONS_COUNT = 0;
            updateNotificationBadge();
            renderNotificationList();
        }
    };
    
    document.addEventListener("click", () => {
        notifDropdown.style.display = "none";
    });
    notifDropdown.onclick = (e) => e.stopPropagation();
}

const btnClearNotifications = document.getElementById("btn-clear-notifications");
if (btnClearNotifications) {
    btnClearNotifications.onclick = (e) => {
        e.stopPropagation();
        NOTIFICATION_HISTORY.length = 0;
        UNREAD_NOTIFICATIONS_COUNT = 0;
        updateNotificationBadge();
        renderNotificationList();
    };
}

// Liaison des boutons d'actualisation Cockpit & Galerie
const btnRefreshCockpit = document.getElementById("btn-refresh-cockpit");
if (btnRefreshCockpit) {
    btnRefreshCockpit.onclick = () => {
        loadCockpitData();
    };
}
const btnRefreshGallery = document.getElementById("btn-refresh-gallery");
if (btnRefreshGallery) {
    btnRefreshGallery.onclick = () => {
        loadGalleryMedia();
    };
}

// =========================================================================
// GESTIONNAIRE DE CONVERSATIONS (PERSISTENCE DE L'HISTORIQUE)
// =========================================================================
const selectConversations = document.getElementById("select-conversations");
const btnNewChat = document.getElementById("btn-new-chat");
const btnDeleteChat = document.getElementById("btn-delete-chat");

async function loadConversations() {
    if (!selectConversations) return;
    try {
        const response = await apiFetch("/api/conversations");
        if (!response.ok) return;
        const data = await response.json();
        
        selectConversations.innerHTML = "";
        if (!data.conversations || data.conversations.length === 0) {
            selectConversations.innerHTML = '<option value="default" selected>Discussion principale</option>';
        } else {
            data.conversations.forEach(conv => {
                const opt = document.createElement("option");
                opt.value = conv.id;
                opt.textContent = conv.name;
                opt.selected = conv.active;
                selectConversations.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Error loading conversations:", e);
    }
}

if (selectConversations) {
    selectConversations.onchange = async () => {
        const convId = selectConversations.value;
        try {
            const response = await apiFetch("/api/conversations/select", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id: convId })
            });
            if (response.ok) {
                await reloadChatHistory(true);
                pushNotification("Conversation", "Discussion chargée avec succès", "success");
            }
        } catch (e) {
            console.error("Error selecting conversation:", e);
        }
    };
}

if (btnNewChat) {
    btnNewChat.onclick = async () => {
        try {
            const response = await apiFetch("/api/conversations/new", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({})
            });
            if (response.ok) {
                await loadConversations();
                await reloadChatHistory(true);
                pushNotification("Conversation", "Nouvelle discussion créée !", "success");
            }
        } catch (e) {
            console.error("Error creating conversation:", e);
        }
    };
}

if (btnDeleteChat) {
    btnDeleteChat.onclick = async () => {
        const convId = selectConversations ? selectConversations.value : "default";
        if (convId === "default") {
            if (confirm("Voulez-vous vider l'historique de cette discussion principale ?")) {
                try {
                    const response = await apiFetch("/api/reset", { method: "POST" });
                    if (response.ok) {
                        await loadConversations();
                        await reloadChatHistory(true);
                        pushNotification("Conversation", "Discussion réinitialisée", "success");
                    }
                } catch (e) {
                    console.error("Error clearing chat:", e);
                }
            }
            return;
        }
        
        if (confirm("Voulez-vous supprimer définitivement cette discussion ?")) {
            try {
                const response = await apiFetch(`/api/conversations/${convId}`, { method: "DELETE" });
                if (response.ok) {
                    await loadConversations();
                    await reloadChatHistory(true);
                    pushNotification("Conversation", "Discussion supprimée", "success");
                }
            } catch (e) {
                console.error("Error deleting conversation:", e);
            }
        }
    };
}

// Charger l'historique au démarrage
loadConversations();

// Boucle de rafraîchissement automatique (toutes les 4 secondes)
setInterval(() => {
    // Les statistiques (tokens, coût) sont globales et toujours visibles en haut,
    // on doit donc toujours les rafraîchir.
    if (typeof loadCockpitData === "function") loadCockpitData();
    
    // La galerie ne se rafraîchit que si on est sur l'onglet cockpit
    const tabCockpit = document.getElementById("tab-cockpit");
    if (tabCockpit && tabCockpit.classList.contains("active")) {
        if (typeof loadGalleryMedia === "function") loadGalleryMedia();
    }
}, 4000);



// =========================================================================
// CONFIGURATION DES TARIFS LLM (PRICING UI)
// =========================================================================

let _pricingData = {};

async function loadPricingConfig() {
    const container = document.getElementById("pricing-rows-container");
    if (!container) return;
    container.innerHTML = "<div style='padding: 12px; text-align: center; opacity: 0.5; font-size: 0.8rem;'>Chargement des tarifs...</div>";
    try {
        const resp = await apiFetch("/api/pricing");
        if (!resp.ok) throw new Error("Erreur serveur");
        _pricingData = await resp.json();
        renderPricingRows(_pricingData);
    } catch (e) {
        container.innerHTML = `<div style='color: #ff5555; padding: 12px; font-size: 0.8rem;'>Erreur: ${e}</div>`;
    }
}

function renderPricingRows(data) {
    const container = document.getElementById("pricing-rows-container");
    if (!container) return;
    container.innerHTML = "";
    const header = document.createElement("div");
    header.style.cssText = "display: grid; grid-template-columns: 1fr 120px 120px 36px; gap: 6px; padding: 2px 10px; font-size: 0.65rem; text-transform: uppercase; color: rgba(255,255,255,0.4); letter-spacing: 0.05em;";
    header.innerHTML = "<span>Modèle</span><span style='text-align:right;color:#4ade80;'>Entrée €/M</span><span style='text-align:right;color:#f59e0b;'>Sortie €/M</span><span></span>";
    container.appendChild(header);
    Object.entries(data).forEach(([model, costs]) => {
        container.appendChild(createPricingRow(model, costs.input_cost_per_million, costs.output_cost_per_million));
    });
}

function createPricingRow(modelName, inputCost, outputCost) {
    const row = document.createElement("div");
    row.className = "pricing-row";
    row.style.cssText = "display: grid; grid-template-columns: 1fr 120px 120px 36px; gap: 6px; align-items: center; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); border-radius: 6px; padding: 8px 10px;";
    const inputModel = document.createElement("input");
    inputModel.type = "text"; inputModel.value = modelName || "";
    inputModel.placeholder = "Ex: gpt-4o-mini"; inputModel.className = "pricing-model-name";
    inputModel.style.cssText = "background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: #fff; padding: 5px 8px; font-size: 0.75rem; outline: none; font-family: 'Fira Code', monospace; width: 100%;";
    const inputIn = document.createElement("input");
    inputIn.type = "number"; inputIn.value = inputCost || 0; inputIn.step = "0.01"; inputIn.min = "0";
    inputIn.className = "pricing-input-cost"; inputIn.title = "Coût entrée €/million tokens";
    inputIn.style.cssText = "background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: #4ade80; padding: 5px 8px; font-size: 0.75rem; outline: none; text-align: right; width: 100%;";
    const inputOut = document.createElement("input");
    inputOut.type = "number"; inputOut.value = outputCost || 0; inputOut.step = "0.01"; inputOut.min = "0";
    inputOut.className = "pricing-output-cost"; inputOut.title = "Coût sortie €/million tokens";
    inputOut.style.cssText = "background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: #f59e0b; padding: 5px 8px; font-size: 0.75rem; outline: none; text-align: right; width: 100%;";
    const btnDel = document.createElement("button");
    btnDel.innerText = "🗑"; btnDel.title = "Supprimer";
    btnDel.style.cssText = "background: rgba(255,85,85,0.15); border: 1px solid rgba(255,85,85,0.3); border-radius: 4px; color: #ff5555; cursor: pointer; padding: 4px 8px; font-size: 0.85rem;";
    btnDel.onclick = () => row.remove();
    row.appendChild(inputModel); row.appendChild(inputIn); row.appendChild(inputOut); row.appendChild(btnDel);
    return row;
}

const btnAddPricingRow = document.getElementById("btn-add-pricing-row");
if (btnAddPricingRow) {
    btnAddPricingRow.onclick = () => {
        const container = document.getElementById("pricing-rows-container");
        if (!container) return;
        container.appendChild(createPricingRow("", 0.50, 1.50));
    };
}

const btnSavePricing = document.getElementById("btn-save-pricing");
if (btnSavePricing) {
    btnSavePricing.onclick = async () => {
        const container = document.getElementById("pricing-rows-container");
        const status = document.getElementById("pricing-save-status");
        if (!container) return;
        const payload = {};
        container.querySelectorAll(".pricing-row").forEach(row => {
            const name = row.querySelector(".pricing-model-name")?.value?.trim();
            const inCost = parseFloat(row.querySelector(".pricing-input-cost")?.value || 0);
            const outCost = parseFloat(row.querySelector(".pricing-output-cost")?.value || 0);
            if (name) payload[name] = { input_cost_per_million: inCost, output_cost_per_million: outCost };
        });
        try {
            const resp = await apiFetch("/api/pricing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            if (resp.ok) {
                const result = await resp.json();
                if (status) status.innerHTML = `<span style='color:#4ade80;'>✅ ${result.models_count} modèle(s) sauvegardé(s)</span>`;
                pushNotification("Tarifs LLM", `${result.models_count} modèles mis à jour`, "success");
                setTimeout(() => { if (status) status.innerHTML = ""; }, 4000);
            } else { throw new Error(await resp.text()); }
        } catch (e) {
            if (status) status.innerHTML = `<span style='color:#ff5555;'>❌ Erreur : ${e}</span>`;
        }
    };
}

const btnResetPricing = document.getElementById("btn-reset-pricing");
if (btnResetPricing) {
    btnResetPricing.onclick = async () => {
        if (!confirm("Réinitialiser aux tarifs par défaut ?")) return;
        const status = document.getElementById("pricing-save-status");
        try {
            const resp = await apiFetch("/api/pricing/reset", { method: "POST" });
            if (resp.ok) {
                const result = await resp.json();
                renderPricingRows(result.data);
                if (status) status.innerHTML = `<span style='color:#f59e0b;'>↺ Tarifs réinitialisés par défaut</span>`;
                setTimeout(() => { if (status) status.innerHTML = ""; }, 4000);
            }
        } catch (e) {
            if (status) status.innerHTML = `<span style='color:#ff5555;'>Erreur: ${e}</span>`;
        }
    };
}

// =========================================================================
// GESTION DU REDIMENSIONNEMENT DU PANNEAU DE CHAT EN DRAG-AND-DROP
// =========================================================================
window.addEventListener("DOMContentLoaded", () => {
    const resizer = document.getElementById("layout-resizer");
    const appContainer = document.querySelector(".app-container");
    
    if (resizer && appContainer) {
        let isDragging = false;
        
        resizer.addEventListener("mousedown", (e) => {
            isDragging = true;
            resizer.classList.add("dragging");
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
        });
        
        document.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            
            // Calculer la nouvelle largeur du chat
            const containerWidth = window.innerWidth;
            const newChatWidth = containerWidth - e.clientX - 3;
            
            // Permettre au chat d'occuper presque tout l'écran (jusqu'à 150px de viewport central)
            const maxChatWidth = containerWidth - 150;
            if (newChatWidth >= 260 && newChatWidth <= maxChatWidth) {
                appContainer.style.gridTemplateColumns = `76px 1fr 6px ${newChatWidth}px`;
            }
        });
        
        document.addEventListener("mouseup", () => {
            if (isDragging) {
                isDragging = false;
                resizer.classList.remove("dragging");
                document.body.style.cursor = "";
                document.body.style.userSelect = "";
                
                // Forcer le recalcul du bureau virtuel isométrique et du graphe
                if (typeof rebuildOfficeFloor === "function") {
                    rebuildOfficeFloor();
                }
                if (typeof rebuildGraphView === "function") {
                    rebuildGraphView();
                }
            }
        });
    }

    // Gestion du bouton flottant pour tablettes et mobiles
    const mobileChatToggleBtn = document.getElementById("btn-mobile-chat-toggle");
    const rightChatSidebar = document.querySelector(".right-chat-sidebar");
    
    if (mobileChatToggleBtn && rightChatSidebar) {
        mobileChatToggleBtn.addEventListener("click", () => {
            rightChatSidebar.classList.toggle("mobile-open");
            if (rightChatSidebar.classList.contains("mobile-open")) {
                mobileChatToggleBtn.innerHTML = "❌";
                mobileChatToggleBtn.style.background = "#ff5555";
                mobileChatToggleBtn.style.boxShadow = "0 0 15px #ff5555";
            } else {
                mobileChatToggleBtn.innerHTML = "💬";
                mobileChatToggleBtn.style.background = "";
                mobileChatToggleBtn.style.boxShadow = "";
            }
        });
    }

    // =========================================================================
    // CONTRÔLEUR DU RESUMEUR DE RÉUNION (TRANCRIPTION & DIARISATION AUDIO)
    // =========================================================================
    const dropzone = document.getElementById("meeting-dropzone");
    const audioInput = document.getElementById("meeting-audio-file");
    const playerWrapper = document.getElementById("meeting-player-wrapper");
    const audioPlayer = document.getElementById("meeting-audio-player");
    const btnStart = document.getElementById("btn-start-transcription");
    const loadingArea = document.getElementById("meeting-loading");
    const statusText = document.getElementById("meeting-status-text");
    const transcriptBox = document.getElementById("meeting-transcript-box");
    const summaryBox = document.getElementById("meeting-summary-box");
    const btnDownload = document.getElementById("btn-download-meeting");
    
    // Éléments pour l'enregistrement direct au micro
    const btnRecord = document.getElementById("btn-record-meeting");
    const recordIcon = document.getElementById("record-icon");
    const recordText = document.getElementById("record-text");
    
    let selectedAudioFile = null;
    let transcriptionResult = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let recordingStartTime = 0;
    let recordingInterval = null;
    
    if (btnRecord) {
        btnRecord.addEventListener("click", async (e) => {
            e.stopPropagation(); // Évite de déclencher le click de la dropzone
            
            if (!isRecording) {
                // Démarre l'enregistrement
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    audioChunks = [];
                    mediaRecorder = new MediaRecorder(stream);
                    
                    mediaRecorder.ondataavailable = (event) => {
                        if (event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    mediaRecorder.onstop = () => {
                        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
                        const audioFile = new File([audioBlob], `enregistrement_${Date.now()}.webm`, { type: "audio/webm" });
                        handleAudioFileSelected(audioFile);
                        
                        // Libérer le micro en coupant toutes les pistes
                        stream.getTracks().forEach(track => track.stop());
                    };
                    
                    mediaRecorder.start();
                    isRecording = true;
                    recordingStartTime = Date.now();
                    
                    // Modifier l'apparence du bouton
                    btnRecord.style.borderColor = "#ff5555";
                    btnRecord.style.background = "rgba(255, 85, 85, 0.15)";
                    btnRecord.style.boxShadow = "0 0 15px rgba(255, 85, 85, 0.4)";
                    recordIcon.style.animation = "pulse 1s infinite alternate";
                    recordIcon.textContent = "⏹️";
                    
                    // Lancer le chronomètre en temps réel
                    recordingInterval = setInterval(() => {
                        const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                        const mins = String(Math.floor(elapsed / 60)).padStart(2, "0");
                        const secs = String(elapsed % 60).padStart(2, "0");
                        recordText.textContent = `ARRÊTER L'ENREGISTREMENT (${mins}:${secs})`;
                    }, 500);
                    
                } catch (err) {
                    console.error("Erreur d'accès au microphone :", err);
                    alert("Impossible d'accéder à votre microphone. Veuillez accorder les permissions d'enregistrement audio.");
                }
            } else {
                // Arrête l'enregistrement
                if (mediaRecorder && mediaRecorder.state !== "inactive") {
                    mediaRecorder.stop();
                }
                
                isRecording = false;
                clearInterval(recordingInterval);
                
                // Réinitialiser le style du bouton
                btnRecord.style.borderColor = "rgba(255,255,255,0.15)";
                btnRecord.style.background = "rgba(255,255,255,0.05)";
                btnRecord.style.boxShadow = "0 4px 15px rgba(0,0,0,0.2)";
                recordIcon.style.animation = "";
                recordIcon.textContent = "🔴";
                recordText.textContent = "ENREGISTRER EN DIRECT";
            }
        });
    }
    
    if (dropzone && audioInput) {
        // Clic sur la zone de drop pour ouvrir le sélecteur
        dropzone.addEventListener("click", () => {
            audioInput.click();
        });
        
        // Drag & Drop visual highlights
        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.style.borderColor = "var(--accent-color)";
            dropzone.style.background = "rgba(0, 0, 0, 0.4)";
        });
        
        dropzone.addEventListener("dragleave", () => {
            dropzone.style.borderColor = "rgba(255, 255, 255, 0.15)";
            dropzone.style.background = "rgba(0, 0, 0, 0.2)";
        });
        
        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.style.borderColor = "rgba(255, 255, 255, 0.15)";
            dropzone.style.background = "rgba(0, 0, 0, 0.2)";
            
            if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                handleAudioFileSelected(e.dataTransfer.files[0]);
            }
        });
        
        audioInput.addEventListener("change", (e) => {
            if (e.target.files && e.target.files[0]) {
                handleAudioFileSelected(e.target.files[0]);
            }
        });
    }
    
    function handleAudioFileSelected(file) {
        selectedAudioFile = file;
        
        // Charger dans le lecteur audio
        const fileURL = URL.createObjectURL(file);
        audioPlayer.src = fileURL;
        
        // Mettre à jour l'UI
        dropzone.querySelector("span[style*='font-weight']").textContent = `Fichier prêt : ${file.name}`;
        dropzone.style.borderColor = "var(--color-Jarvis)";
        
        playerWrapper.style.display = "flex";
        btnStart.style.display = "inline-block";
        btnStart.disabled = false;
        btnStart.textContent = "Lancer la transcription";
    }
    
    if (btnStart) {
        btnStart.addEventListener("click", async () => {
            if (!selectedAudioFile) return;
            
            // Masquer le bouton de départ et afficher la zone de chargement
            btnStart.style.display = "none";
            loadingArea.style.display = "flex";
            statusText.textContent = "Téléchargement et analyse du fichier audio...";
            
            transcriptBox.innerHTML = '<div style="opacity: 0.5; text-align: center; margin: auto;">Analyse des voix en cours...</div>';
            summaryBox.innerHTML = '<div style="opacity: 0.5; text-align: center; margin: auto;">Rédaction du compte-rendu en cours...</div>';
            btnDownload.style.display = "none";
            
            const formData = new FormData();
            formData.append("file", selectedAudioFile);
            
            try {
                // Étape 2: Envoyer au serveur de transcription
                statusText.textContent = "Transcription des voix & Diarisation par l'IA...";
                const res = await fetch("/api/meeting/transcribe", {
                    method: "POST",
                    body: formData
                });
                
                const data = await res.json();
                loadingArea.style.display = "none";
                
                if (data.error) {
                    transcriptBox.innerHTML = `<div style="color: #ff5555; text-align: center; margin: auto; padding: 12px;">❌ Erreur : ${data.error}</div>`;
                    summaryBox.innerHTML = `<div style="color: #ff5555; text-align: center; margin: auto; padding: 12px;">Impossible de générer le compte-rendu.</div>`;
                    btnStart.style.display = "inline-block";
                    return;
                }
                
                transcriptionResult = data;
                renderDiarizedTranscript(data.transcript);
                renderStructuredSummary(data.summary);
                
                // Activer l'export
                btnDownload.style.display = "inline-block";
                
            } catch (err) {
                loadingArea.style.display = "none";
                transcriptBox.innerHTML = `<div style="color: #ff5555; text-align: center; margin: auto; padding: 12px;">❌ Exception : ${err.message}</div>`;
                summaryBox.innerHTML = `<div style="color: #ff5555; text-align: center; margin: auto; padding: 12px;">Échec de la connexion avec le serveur.</div>`;
                btnStart.style.display = "inline-block";
            }
        });
    }
    
    // Rendu du dialogue diarisé sous forme de bulles stylisées
    function renderDiarizedTranscript(dialogue) {
        if (!dialogue || dialogue.length === 0) {
            transcriptBox.innerHTML = '<div style="opacity: 0.4; text-align: center; margin: auto;">Aucun dialogue détecté.</div>';
            return;
        }
        
        transcriptBox.innerHTML = "";
        
        // Assigner dynamiquement des couleurs aux locuteurs distincts
        const speakerColors = {};
        const colors = [
            "var(--color-Jarvis)", // Cyan
            "#a855f7", // Violet
            "#eab308", // Jaune
            "#ec4899", // Rose
            "#10b981", // Vert
            "#3b82f6"  // Bleu
        ];
        let colorIdx = 0;
        
        dialogue.forEach(line => {
            const speaker = line.speaker || "Locuteur Inconnu";
            if (!speakerColors[speaker]) {
                speakerColors[speaker] = colors[colorIdx % colors.length];
                colorIdx++;
            }
            
            const color = speakerColors[speaker];
            
            const lineEl = document.createElement("div");
            lineEl.className = "transcript-bubble glass";
            lineEl.style.padding = "10px 14px";
            lineEl.style.borderRadius = "8px";
            lineEl.style.background = "rgba(255, 255, 255, 0.02)";
            lineEl.style.borderLeft = `3px solid ${color}`;
            lineEl.style.display = "flex";
            lineEl.style.flexDirection = "column";
            lineEl.style.gap = "4px";
            lineEl.style.boxShadow = "0 2px 8px rgba(0,0,0,0.2)";
            
            lineEl.innerHTML = `
                <div style="font-weight: bold; font-size: 0.8rem; color: ${color};">${speaker}</div>
                <div style="font-size: 0.85rem; line-height: 1.4; color: #fff;">${line.text}</div>
            `;
            
            transcriptBox.appendChild(lineEl);
        });
    }
    
    // Rendu du compte-rendu markdown
    function renderStructuredSummary(markdownText) {
        if (!markdownText) {
            summaryBox.innerHTML = '<div style="opacity: 0.4; text-align: center; margin: auto;">Aucun compte-rendu généré.</div>';
            return;
        }
        
        // Utiliser marked.parse si présent, sinon afficher en texte brut formaté
        if (window.marked && typeof window.marked.parse === "function") {
            summaryBox.innerHTML = window.marked.parse(markdownText);
        } else {
            summaryBox.textContent = markdownText;
        }
    }
    
    // Export/téléchargement du compte-rendu Markdown
    if (btnDownload) {
        btnDownload.addEventListener("click", () => {
            if (!transcriptionResult || !transcriptionResult.summary) return;
            
            const blob = new Blob([transcriptionResult.summary], { type: "text/markdown;charset=utf-8;" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", `compte_rendu_${Date.now()}.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }
});

// =========================================================================
// MODULE DE SAISIE ET AUTOCOMPLÉTION PREMIUM POUR LES MENTIONS @AGENT
// =========================================================================
let selectedMentionIndex = 0;
let filteredAgentsList = [];

function initMentionAutocomplete() {
    const chatInput = document.getElementById("chat-input");
    if (!chatInput) return;

    // Création du dropdown flottant
    const dropdown = document.createElement("div");
    dropdown.id = "mention-autocomplete-dropdown";
    document.body.appendChild(dropdown);

    // Injection des styles haut de gamme pour l'autocomplétion
    const style = document.createElement("style");
    style.textContent = `
        #mention-autocomplete-dropdown {
            position: absolute;
            background: rgba(15, 15, 20, 0.92);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid rgba(0, 240, 255, 0.25);
            border-radius: 14px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7), 0 0 15px rgba(0, 240, 255, 0.1);
            z-index: 999999;
            display: none;
            flex-direction: column;
            max-height: 250px;
            overflow-y: auto;
            width: 280px;
            padding: 6px;
            scrollbar-width: thin;
            scrollbar-color: rgba(0, 240, 255, 0.3) transparent;
        }
        #mention-autocomplete-dropdown::-webkit-scrollbar {
            width: 4px;
        }
        #mention-autocomplete-dropdown::-webkit-scrollbar-thumb {
            background: rgba(0, 240, 255, 0.3);
            border-radius: 2px;
        }
        .mention-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 10px;
            color: rgba(255, 255, 255, 0.85);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            font-family: 'Inter', sans-serif;
            border: 1px solid transparent;
        }
        .mention-item:hover, .mention-item.active {
            background: linear-gradient(90deg, rgba(0, 240, 255, 0.12) 0%, rgba(0, 240, 255, 0.03) 100%);
            border-color: rgba(0, 240, 255, 0.25);
            color: #ffffff;
            transform: translateX(4px);
        }
        .mention-emoji {
            font-size: 1.2rem;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
        }
        .mention-details {
            display: flex;
            flex-direction: column;
            gap: 1px;
        }
        .mention-name {
            font-weight: 600;
            color: #ffffff;
            font-family: 'Fira Code', monospace;
        }
        .mention-role {
            font-size: 0.72rem;
            color: rgba(255, 255, 255, 0.45);
        }
    `;
    document.head.appendChild(style);

    // Ajustement dynamique du positionnement
    function positionDropdown() {
        const rect = chatInput.getBoundingClientRect();
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.bottom = `${window.innerHeight - window.scrollY - rect.top + 8}px`;
    }

    // Capture des frappes utilisateur
    chatInput.addEventListener("input", () => {
        const text = chatInput.value;
        const selectionStart = chatInput.selectionStart;
        
        // Détecter si on écrit derrière un caractère @
        const lastAtIndex = text.lastIndexOf("@", selectionStart - 1);
        
        if (lastAtIndex !== -1) {
            // S'assurer qu'aucun espace n'est présent entre le @ et le curseur (mot en cours)
            const prefix = text.substring(lastAtIndex + 1, selectionStart);
            if (!prefix.includes(" ")) {
                showMentions(prefix, lastAtIndex);
                return;
            }
        }
        
        hideMentions();
    });

    // Génération et affichage de la liste de suggestions
    function showMentions(prefix, lastAtIndex) {
        // Filtrer les agents dynamiquement basés sur la config courante
        filteredAgentsList = agentsConfig.filter(agent => {
            const nameMatch = agent.name.toLowerCase().includes(prefix.toLowerCase());
            const displayMatch = agent.display_name && agent.display_name.toLowerCase().includes(prefix.toLowerCase());
            return nameMatch || displayMatch;
        });

        // Toujours proposer l'orchestrateur (renommable) s'il correspond au préfixe
        const _orchN = orchestratorName();
        if (_orchN.toLowerCase().includes(prefix.toLowerCase()) && !filteredAgentsList.some(a => a.name.toLowerCase() === _orchN.toLowerCase())) {
            const _orchA = orchestratorAgent();
            filteredAgentsList.unshift({
                name: _orchN,
                display_name: (_orchA && _orchA.display_name) || _orchN,
                avatar_type: (_orchA && _orchA.avatar_type) || "robot_neon",
            });
        }

        if (filteredAgentsList.length === 0) {
            hideMentions();
            return;
        }

        dropdown.innerHTML = "";
        selectedMentionIndex = 0;

        filteredAgentsList.forEach((agent, index) => {
            const item = document.createElement("div");
            item.className = `mention-item ${index === selectedMentionIndex ? 'active' : ''}`;
            
            const emoji = getAgentEmoji(agent.avatar_type || agent.name);
            
            item.innerHTML = `
                <span class="mention-emoji">${emoji}</span>
                <div class="mention-details">
                    <span class="mention-name">@${agent.name}</span>
                    <span class="mention-role">${agent.display_name || 'Agent Spécialiste'}</span>
                </div>
            `;

            // Sélection au clic de la souris
            item.addEventListener("click", () => {
                insertMention(agent.name, lastAtIndex);
            });

            dropdown.appendChild(item);
        });

        positionDropdown();
        dropdown.style.display = "flex";
    }

    // Insertion intelligente de la mention sélectionnée
    function insertMention(agentName, lastAtIndex) {
        const text = chatInput.value;
        const selectionStart = chatInput.selectionStart;
        const before = text.substring(0, lastAtIndex);
        const after = text.substring(selectionStart);
        
        chatInput.value = before + "@" + agentName + " " + after;
        chatInput.focus();
        
        // Repositionner le curseur juste après le tag inséré
        const newCursorPos = lastAtIndex + agentName.length + 2;
        chatInput.setSelectionRange(newCursorPos, newCursorPos);
        
        hideMentions();
    }

    function hideMentions() {
        dropdown.style.display = "none";
    }

    // Masquer le dropdown en cas de clic en dehors
    document.addEventListener("click", (e) => {
        if (e.target !== chatInput && !dropdown.contains(e.target)) {
            hideMentions();
        }
    });

    // Mettre à jour la position en cas de resize/scroll
    window.addEventListener("resize", positionDropdown);
    window.addEventListener("scroll", positionDropdown);

    // Gestion de la navigation au clavier (Premium User Experience)
    chatInput.addEventListener("keydown", (e) => {
        if (dropdown.style.display === "flex") {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                selectedMentionIndex = (selectedMentionIndex + 1) % filteredAgentsList.length;
                updateActiveItem();
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                selectedMentionIndex = (selectedMentionIndex - 1 + filteredAgentsList.length) % filteredAgentsList.length;
                updateActiveItem();
            } else if (e.key === "Enter" || e.key === "Tab") {
                e.preventDefault();
                const activeAgent = filteredAgentsList[selectedMentionIndex];
                if (activeAgent) {
                    const text = chatInput.value;
                    const selectionStart = chatInput.selectionStart;
                    const lastAtIndex = text.lastIndexOf("@", selectionStart - 1);
                    insertMention(activeAgent.name, lastAtIndex);
                }
            } else if (e.key === "Escape") {
                e.preventDefault();
                hideMentions();
            }
        }
    });

    // Mettre à jour visuellement l'élément sélectionné
    function updateActiveItem() {
        const items = dropdown.querySelectorAll(".mention-item");
        items.forEach((item, index) => {
            if (index === selectedMentionIndex) {
                item.classList.add("active");
                item.scrollIntoView({ block: "nearest" });
            } else {
                item.classList.remove("active");
            }
        });
    }
}

// Initialisation globale au chargement de la page
if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", initMentionAutocomplete);
} else {
    initMentionAutocomplete();
}

// =========================================================================
// GESTION PREMIUM DES ENVOIS DE DOCUMENTS DEPUIS LA ZONE DE CHAT
// =========================================================================
async function uploadAndIngestFromChat(file) {
    const chatInput = document.getElementById("chat-input");
    if (!chatInput) return;
    
    logToTerminal(`Traitement du fichier '${file.name}' depuis le chat... ⏳`, "info");
    
    // Mettre un indicateur de chargement dans le placeholder de l'input
    const origPlaceholder = chatInput.placeholder;
    chatInput.placeholder = `Ingestion de ${file.name} en cours... ⏳`;
    chatInput.disabled = true;
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await apiFetch("/api/workspace/upload", {
            method: "POST",
            body: formData
        });
        const res = await response.json();
        
        if (response.ok) {
            logToTerminal(`Fichier '${file.name}' téléversé avec succès.`, "success");
            
            if (res.ingested && res.report) {
                // Log le rapport RAG
                logToTerminal(res.report, "success");
                
                // Afficher un message de confirmation spécial dans le flux de chat
                appendSystemMessage(`📖 **Document ingéré** : \`${file.name}\` a été segmenté et indexé avec succès dans ma mémoire sémantique. Vous pouvez maintenant me poser des questions sur son contenu !`);
            } else {
                appendSystemMessage(`📁 **Fichier téléversé** : \`${file.name}\` est disponible dans le dossier de travail.`);
            }
            
            // Proposer une action de prompt prête à l'emploi
            chatInput.value = `Analyse le document "${file.name}" que je viens d'importer et résume ses points clés.`;
            
            // Actualiser l'explorateur de fichiers s'il est visible en arrière-plan
            if (typeof loadWorkspaceFiles === "function") {
                await loadWorkspaceFiles();
            }
        } else {
            alert("Erreur lors de l'envoi du fichier : " + res.detail);
        }
    } catch (err) {
        alert("Erreur réseau : " + err);
    } finally {
        chatInput.placeholder = origPlaceholder;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

// Petite fonction utilitaire pour ajouter un message système dans le flux de chat
function appendSystemMessage(text) {
    const chatMessages = document.getElementById("chat-messages");
    if (!chatMessages) return;
    
    const msgDiv = document.createElement("div");
    msgDiv.className = "chat-message system";
    msgDiv.style.alignSelf = "center";
    msgDiv.style.margin = "8px auto";
    msgDiv.style.padding = "6px 12px";
    msgDiv.style.borderRadius = "8px";
    msgDiv.style.background = "rgba(0, 240, 255, 0.05)";
    msgDiv.style.border = "1px solid rgba(0, 240, 255, 0.15)";
    msgDiv.style.color = "var(--accent-color)";
    msgDiv.style.fontSize = "0.75rem";
    msgDiv.style.maxWidth = "80%";
    msgDiv.style.textAlign = "center";
    
    // Parser le markdown basique (* ou `)
    msgDiv.innerHTML = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                           .replace(/\`(.*?)\`/g, '<code>$1</code>');
                           
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}



/* ===== Panneau de logs serveur live (autonome, injecté en JS) ===== */
function _initLogPanel() {
  if (window.__logPanel) return;
  window.__logPanel = true;
  let open = false, paused = false, level = "INFO";
  const LV = { DEBUG:"#7f8c9a", INFO:"#5cc8ff", WARNING:"#ffcc66", ERROR:"#ff6b6b", CRITICAL:"#ff3b3b" };

  const btn = document.createElement("button");
  btn.textContent = "🗒 Logs";
  btn.title = "Logs serveur (live)";
  btn.style.cssText = "position:fixed;bottom:12px;right:12px;z-index:9998;background:#111;color:#fff;border:1px solid #444;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:12px;opacity:.85;";
  document.body.appendChild(btn);

  const panel = document.createElement("div");
  panel.style.cssText = "position:fixed;bottom:52px;right:12px;width:min(640px,92vw);height:min(360px,60vh);z-index:9999;background:#0c0f14;border:1px solid #2a3340;border-radius:10px;display:none;flex-direction:column;box-shadow:0 8px 30px rgba(0,0,0,.5);font-family:ui-monospace,Menlo,Consolas,monospace;";
  panel.innerHTML =
    '<div style="display:flex;gap:8px;align-items:center;padding:6px 10px;background:#11161d;border-bottom:1px solid #2a3340;font-size:12px;color:#cdd6e0;">' +
    '<span style="font-weight:700;">🗒 Logs serveur</span>' +
    '<select id="logp-level" style="background:#0c0f14;color:#cdd6e0;border:1px solid #2a3340;border-radius:5px;font-size:11px;"></select>' +
    '<label style="display:flex;gap:4px;align-items:center;"><input type="checkbox" id="logp-pause"> pause</label>' +
    '<button id="logp-clear" style="background:none;border:1px solid #2a3340;color:#cdd6e0;border-radius:5px;cursor:pointer;">vider</button>' +
    '<span style="flex:1;"></span>' +
    '<button id="logp-close" style="background:none;border:none;color:#cdd6e0;cursor:pointer;font-size:14px;">✕</button>' +
    '</div>' +
    '<div id="logp-body" style="flex:1;overflow:auto;padding:6px 10px;font-size:11.5px;line-height:1.45;color:#cdd6e0;white-space:pre-wrap;word-break:break-word;"></div>';
  document.body.appendChild(panel);

  const body = panel.querySelector("#logp-body");
  const sel = panel.querySelector("#logp-level");
  ["DEBUG","INFO","WARNING","ERROR"].forEach(function(l){ const o=document.createElement("option"); o.value=l; o.textContent=l; sel.appendChild(o); });
  sel.value = level;

  async function refresh() {
    if (!open || paused) return;
    try {
      const r = await apiFetch("/api/logs?level=" + encodeURIComponent(level) + "&limit=300");
      if (!r.ok) return;
      const data = await r.json();
      body.innerHTML = "";
      (data.logs || []).forEach(function(l) {
        const row = document.createElement("div");
        const ts = document.createElement("span"); ts.style.color = "#5b6675"; ts.textContent = new Date(l.t*1000).toLocaleTimeString() + " ";
        const lv = document.createElement("span"); lv.style.color = LV[l.level] || "#cdd6e0"; lv.style.fontWeight = "700"; lv.textContent = (l.level + "       ").slice(0,7) + " ";
        const nm = document.createElement("span"); nm.style.color = "#7f8c9a"; nm.textContent = "[" + l.name + "] ";
        const ms = document.createElement("span"); ms.textContent = l.msg;
        row.append(ts, lv, nm, ms);
        body.appendChild(row);
      });
      body.scrollTop = body.scrollHeight;
    } catch (e) { /* silencieux */ }
  }

  btn.onclick = function(){ open = !open; panel.style.display = open ? "flex" : "none"; if (open) refresh(); };
  panel.querySelector("#logp-close").onclick = function(){ open = false; panel.style.display = "none"; };
  panel.querySelector("#logp-pause").onchange = function(e){ paused = e.target.checked; };
  panel.querySelector("#logp-clear").onclick = function(){ body.innerHTML = ""; };
  sel.onchange = async function(){
    level = sel.value;
    try { await apiFetch("/api/logs/level", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ level: level }) }); } catch (e) {}
    refresh();
  };
  setInterval(refresh, 2500);
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _initLogPanel);
else _initLogPanel();


// --- MCP MARKETPLACE LOGIC ---
async function loadMcpMarketplace() {
    try {
        const r = await apiFetch("/api/config/mcp/marketplace");
        if (r.ok) {
            mcpMarketplaceCatalogs = await r.json();
            renderMcpMarketplaceCategories();
            renderMcpMarketplaceGrid();
        }
    } catch (e) {
        console.error("Erreur chargement marketplace MCP", e);
    }
}

function renderMcpMarketplaceCategories() {
    const sel = document.getElementById("mcp-market-category");
    if (!sel) return;
    sel.innerHTML = `<option value="all">Tous les catalogues</option>`;
    mcpMarketplaceCatalogs.forEach((cat, idx) => {
        sel.innerHTML += `<option value="${idx}">${cat.category}</option>`;
    });
    sel.onchange = renderMcpMarketplaceGrid;
}

function renderMcpMarketplaceGrid() {
    const grid = document.getElementById("mcp-market-grid");
    const sel = document.getElementById("mcp-market-category");
    if (!grid || !sel) return;
    
    const catIdx = sel.value;
    grid.innerHTML = "";
    
    let serversToShow = [];
    if (catIdx === "all") {
        mcpMarketplaceCatalogs.forEach(cat => serversToShow.push(...cat.servers));
    } else {
        serversToShow = mcpMarketplaceCatalogs[catIdx]?.servers || [];
    }
    
    serversToShow.forEach(srv => {
        const card = document.createElement("div");
        card.className = "mcp-market-card";
        
        // stringify for onclick handler safely
        const payload = encodeURIComponent(JSON.stringify(srv));
        
        card.innerHTML = `
            <div>
                <div class="mcp-market-card-header">
                    <span style="font-size: 1.5rem;">${srv.icon || '🧩'}</span>
                    <div class="mcp-market-card-title">${srv.label}</div>
                </div>
                <div class="mcp-market-card-desc">${srv.note}</div>
                <div style="font-size: 0.7rem; color: #888; margin-bottom: 12px; font-family: monospace;">${srv.command} ${srv.args[0] || ''}...</div>
            </div>
            <button class="mcp-market-card-btn" onclick="installMarketplaceServer('${payload}')">Installer</button>
        `;
        grid.appendChild(card);
    });
}

function installMarketplaceServer(payloadStr) {
    const srv = JSON.parse(decodeURIComponent(payloadStr));
    
    // Switch to 'Mes Serveurs' tab
    document.getElementById("tab-mcp-mine").click();
    
    // Open Add form
    document.getElementById("btn-mcp-add-new").click();
    
    // Fill form
    document.getElementById("mcp-name").value = srv.name;
    document.getElementById("mcp-command").value = srv.command;
    document.getElementById("mcp-args").value = (srv.args || []).join(" ");
    
    // renderMcpEnv if exists (needs to be adapted if the function expects obj)
    // Actually we just need to re-render the env html list
    const envList = document.getElementById("mcp-env-list");
    if (envList) {
        envList.innerHTML = "";
        for (const [k, v] of Object.entries(srv.env || {})) {
            const row = document.createElement("div");
            row.className = "mcp-env-row form-group";
            row.style.flexDirection = "row";
            row.innerHTML = `
                <input type="text" class="env-k" value="${k}" placeholder="Clé (ex: API_KEY)" style="flex:1;">
                <input type="text" class="env-v" value="${v}" placeholder="Valeur" style="flex:2;">
                <button type="button" class="btn btn-remove-env" style="padding:4px 8px;">✕</button>
            `;
            row.querySelector(".btn-remove-env").onclick = () => row.remove();
            envList.appendChild(row);
        }
    }
    
    document.getElementById("mcp-disabled").checked = false;
    
    const noteEl = document.getElementById("mcp-preset-note");
    if (noteEl) {
        noteEl.innerHTML = `<b>ℹ️ ${srv.label}</b> : Remplissez les variables d'environnement si nécessaire, puis Enregistrez.`;
        noteEl.style.display = "block";
    }
}

// --- TABS LOGIC ---
const tabMine = document.getElementById("tab-mcp-mine");
const tabMarket = document.getElementById("tab-mcp-market");
const viewMine = document.getElementById("mcp-view-mine");
const viewMarket = document.getElementById("mcp-view-market");

if (tabMine && tabMarket) {
    tabMine.onclick = () => {
        tabMine.classList.add("active");
        tabMarket.classList.remove("active");
        viewMine.style.display = "block";
        viewMarket.style.display = "none";
    };
    tabMarket.onclick = () => {
        tabMarket.classList.add("active");
        tabMine.classList.remove("active");
        viewMarket.style.display = "block";
        viewMine.style.display = "none";
        
        // Hide form if open
        const formContainer = document.getElementById("mcp-form-container");
        if (formContainer) formContainer.style.display = "none";
    };
}
