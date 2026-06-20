// AthenaDesign - Frontend Logic and Interactive Controls

// MULTI-UTILISATEUR : le studio tourne dans une iframe SAME-ORIGIN → il partage le
// localStorage de l'app Athena. On lit le jeton de session et on l'ajoute en Authorization
// sur tous les appels /api (sinon 401 quand l'auth d'Athena est activée). En mode local
// sans auth, le jeton est vide → aucun en-tête ajouté, comportement inchangé.
(function () {
    const _origFetch = window.fetch.bind(window);
    const _token = () => { try { return localStorage.getItem("athena_session_token") || ""; } catch (e) { return ""; } };
    window.fetch = function (input, init) {
        init = init || {};
        const url = (typeof input === "string") ? input : (input && input.url) || "";
        const t = _token();
        if (url.startsWith("/api/") || url.startsWith("api/")) {
            const h = new Headers(init.headers || (typeof input !== "string" && input.headers) || {});
            if (t && !h.has("Authorization")) h.set("Authorization", "Bearer " + t);
            // Langue d'interface partagée (iframe same-origin) → réponses des agents dans
            // la bonne langue. Repli "fr" si non défini.
            try { if (!h.has("X-Athena-Lang")) h.set("X-Athena-Lang", localStorage.getItem("athena_lang") || "fr"); } catch (e) {}
            init.headers = h;
        }
        return _origFetch(input, init);
    };
})();

// Charge un fichier généré (plot/plotly/pptx) via l'endpoint AUTHENTIFIÉ + ownership et
// renvoie un objectURL : les <img>/<iframe>/<a> natifs ne portent pas le Bearer, donc on
// passe par fetch (qui ajoute le token) → blob.
async function adFileBlobUrl(projectId, filename) {
    const r = await fetch(`/api/athenadesign/file/${projectId}/${encodeURIComponent(filename)}`);
    if (!r.ok) throw new Error("HTTP " + r.status);
    return URL.createObjectURL(await r.blob());
}

document.addEventListener("DOMContentLoaded", () => {
    // Check if framed inside an iframe
    if (window.self !== window.top) {
        document.body.classList.add("framed");
    }

    // Safe wrapper for Lucide icons initialization
    function safeCreateIcons() {
        if (typeof lucide !== "undefined" && lucide && typeof lucide.createIcons === "function") {
            try {
                lucide.createIcons();
            } catch (e) {
                console.error("Failed to run lucide.createIcons:", e);
            }
        } else {
            console.warn("Lucide library is not loaded. Icons won't be rendered.");
        }
    }

    // Icons
    safeCreateIcons();

    // DOM Elements
    const themeToggleBtn = document.getElementById("theme-toggle-btn");
    const aiProviderSelect = document.getElementById("ai-provider");
    const apiKeyGroup = document.getElementById("api-key-group");
    const modelGroup = document.getElementById("model-group");
    const apiKeyInput = document.getElementById("api-key");
    const modelNameInput = document.getElementById("model-name");
    
    const projectsList = document.getElementById("projects-list");
    const btnNewProject = document.getElementById("btn-new-project");
    const currentProjectTitle = document.getElementById("current-project-title");
    const appStatus = document.getElementById("app-status");
    
    const chatMessages = document.getElementById("chat-messages");
    const promptInput = document.getElementById("prompt-input");
    const chatForm = document.getElementById("chat-form");
    
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    const btnRunPython = document.getElementById("btn-run-python");
    const btnExportPdf = document.getElementById("btn-export-pdf");
    const btnCopy = document.getElementById("btn-copy");
    const btnDownload = document.getElementById("btn-download");
    const btnHandoff = document.getElementById("btn-handoff");
    const btnRefreshPreview = document.getElementById("btn-refresh-preview");
    const btnOpenExternal = document.getElementById("btn-open-external");
    const responsiveToolbar = document.getElementById("responsive-toolbar");
    const respBtns = document.querySelectorAll(".resp-btn");
    
    const previewFrameContainer = document.getElementById("preview-frame-container");
    const htmlPreviewFrame = document.getElementById("html-preview-frame");
    
    const pythonPreviewContainer = document.getElementById("python-preview-container");
    const pythonPromptRun = document.getElementById("python-prompt-run");
    const pythonExecuting = document.getElementById("python-executing");
    const pythonPlotsWrapper = document.getElementById("python-plots-wrapper");
    const plotsContainer = document.getElementById("plots-container");
    
    const canvasEmptyState = document.getElementById("canvas-empty-state");
    
    const fallbackCodeArea = document.getElementById("fallback-code-area");
    const consoleOutput = document.getElementById("console-output");
    const btnClearConsole = document.getElementById("btn-clear-console");
    const versionsTimeline = document.getElementById("versions-timeline");

    // Comment/Annotation UI Elements
    const btnCommentMode = document.getElementById("btn-comment-mode");
    const annotationToolbar = document.getElementById("annotation-toolbar");
    const annotationOverlay = document.getElementById("annotation-overlay");
    const drawingCanvas = document.getElementById("drawing-canvas");
    const commentPopup = document.getElementById("comment-popup");
    const commentTextInput = document.getElementById("comment-text-input");
    const btnSubmitComment = document.getElementById("btn-submit-comment");
    const btnClosePopup = document.getElementById("btn-close-popup");
    const btnClearDrawing = document.getElementById("btn-clear-drawing");
    const commentsSidebar = document.getElementById("comments-sidebar");
    const versionCommentsList = document.getElementById("version-comments-list");
    const commentPinsContainer = document.getElementById("comment-pins-container");
    
    const pythonAnnotationOverlay = document.getElementById("python-annotation-overlay");
    const pythonDrawingCanvas = document.getElementById("python-drawing-canvas");
    const pythonCommentPinsContainer = document.getElementById("python-comment-pins-container");

    // Preview JS Error Auto-fix UI Elements
    const previewErrorOverlay = document.getElementById("preview-error-overlay");
    const previewErrorMessage = document.getElementById("preview-error-message");
    const btnAutofixError = document.getElementById("btn-autofix-error");
    const btnCloseError = document.getElementById("btn-close-error");

    // Point-and-Modify Element Selection Context Menu
    const contextMenuBubble = document.getElementById("context-menu-bubble");
    const bubbleTargetElement = document.getElementById("bubble-target-element");
    const btnCloseBubble = document.getElementById("btn-close-bubble");
    const bubbleSuggestionsList = document.getElementById("bubble-suggestions-list");
    const bubbleCustomInput = document.getElementById("bubble-custom-input");
    const btnSubmitBubble = document.getElementById("btn-submit-bubble");

    // Dynamic Tweaks Sidebar
    const tweaksSidebar = document.getElementById("tweaks-sidebar");
    const btnCloseTweaks = document.getElementById("btn-close-tweaks");
    const btnOpenTweaks = document.getElementById("btn-open-tweaks");
    const tweaksControlsList = document.getElementById("tweaks-controls-list");

    // Agentic Loop Suggestions
    const suggestionsChips = document.getElementById("suggestions-chips");
    const starterChips = document.getElementById("starter-chips");

    // Renommer un projet : clic sur son titre → invite + POST rename (cohérent avec les autres fetch).
    if (currentProjectTitle) {
        currentProjectTitle.style.cursor = "pointer";
        currentProjectTitle.title = "Cliquer pour renommer le projet";
        currentProjectTitle.addEventListener("click", async () => {
            if (!currentProjectId) return;
            const nn = prompt("Nouveau nom du projet :", currentProjectTitle.textContent.trim());
            if (!nn || !nn.trim()) return;
            try {
                const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/rename`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: nn.trim() })
                });
                if (!r.ok) throw new Error("HTTP " + r.status);
                currentProjectTitle.textContent = nn.trim();
                if (currentProjectData) currentProjectData.name = nn.trim();
                if (typeof loadProjects === "function") loadProjects();
            } catch (e) { alert("Renommage impossible : " + e.message); }
        });
    }

    // Application State
    let currentProjectId = null;
    let currentProjectData = null;
    let currentVersionIndex = null; // 0-indexed in currentProjectData.versions
    let currentWorkspacePreview = null; // {projectId, entry} quand on prévisualise les fichiers du workspace (projet Code)
    let currentSources = { base: null, design: null }; // pages prévisualisables : code de base (racine) vs sortie Design

    // ── Imports (références) + Design System ──────────────────────────────────
    let pendingAttachments = [];
    const attachmentsBar = document.getElementById("attachments-bar");
    const attachFileInput = document.getElementById("attach-file-input");
    const btnAttachFile = document.getElementById("btn-attach-file");
    const btnAttachWeb = document.getElementById("btn-attach-web");
    const designSystemInput = document.getElementById("design-system-input");
    const btnDsSave = document.getElementById("btn-ds-save");
    const btnDsExtract = document.getElementById("btn-ds-extract");

    function renderAttachments() {
        if (!attachmentsBar) return;
        attachmentsBar.innerHTML = "";
        attachmentsBar.style.display = pendingAttachments.length ? "flex" : "none";
        pendingAttachments.forEach((a, i) => {
            const chip = document.createElement("span");
            chip.className = "attachment-chip";
            chip.style.cssText = "display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:12px;background:rgba(255,255,255,0.08);font-size:0.72rem;";
            const label = a.kind === "image" ? "🖼️" : (a.kind === "web" ? "🔗" : "📄");
            chip.textContent = `${label} ${a.name || a.url || a.kind}`;
            const x = document.createElement("button");
            x.type = "button"; x.textContent = "✕";
            x.style.cssText = "background:none;border:none;color:inherit;cursor:pointer;font-size:0.7rem;";
            x.addEventListener("click", () => { pendingAttachments.splice(i, 1); renderAttachments(); });
            chip.appendChild(x);
            attachmentsBar.appendChild(chip);
        });
    }
    function clearAttachments() { pendingAttachments = []; renderAttachments(); }

    if (btnAttachFile && attachFileInput) {
        btnAttachFile.addEventListener("click", () => attachFileInput.click());
        attachFileInput.addEventListener("change", () => {
            Array.from(attachFileInput.files || []).slice(0, 8).forEach(file => {
                const reader = new FileReader();
                reader.onload = () => {
                    const isImg = (file.type || "").startsWith("image/");
                    pendingAttachments.push({
                        kind: isImg ? "image" : "document",
                        name: file.name,
                        data_url: reader.result
                    });
                    renderAttachments();
                };
                reader.readAsDataURL(file);
            });
            attachFileInput.value = "";
        });
    }
    if (btnAttachWeb) {
        btnAttachWeb.addEventListener("click", () => {
            const url = prompt("URL de la page à utiliser comme référence (capture web) :");
            if (url && /^https?:\/\//i.test(url)) {
                pendingAttachments.push({ kind: "web", url: url.trim() });
                renderAttachments();
            }
        });
    }

    // -- Visual Design System Editor Logic --
    const btnDsModeVisual = document.getElementById("btn-ds-mode-visual");
    const btnDsModeRaw = document.getElementById("btn-ds-mode-raw");
    const dsVisualEditor = document.getElementById("ds-visual-editor");
    const dsRawEditor = document.getElementById("ds-raw-editor");

    const dsColorPrimary = document.getElementById("ds-color-primary");
    const dsColorPrimaryText = document.getElementById("ds-color-primary-text");
    const dsColorSecondary = document.getElementById("ds-color-secondary");
    const dsColorSecondaryText = document.getElementById("ds-color-secondary-text");
    const dsFont = document.getElementById("ds-font");
    const dsTheme = document.getElementById("ds-theme");
    const dsRadius = document.getElementById("ds-radius");
    const dsSpacing = document.getElementById("ds-spacing");

    if (btnDsModeVisual && btnDsModeRaw) {
        btnDsModeVisual.addEventListener("click", () => {
            btnDsModeVisual.classList.add("active");
            btnDsModeVisual.style.color = "var(--text-primary)";
            btnDsModeVisual.style.borderBottom = "2px solid var(--accent-primary)";
            btnDsModeRaw.classList.remove("active");
            btnDsModeRaw.style.color = "var(--text-secondary)";
            btnDsModeRaw.style.borderBottom = "none";
            if (dsVisualEditor) dsVisualEditor.style.display = "flex";
            if (dsRawEditor) dsRawEditor.style.display = "none";
        });
        btnDsModeRaw.addEventListener("click", () => {
            btnDsModeRaw.classList.add("active");
            btnDsModeRaw.style.color = "var(--text-primary)";
            btnDsModeRaw.style.borderBottom = "2px solid var(--accent-primary)";
            btnDsModeVisual.classList.remove("active");
            btnDsModeVisual.style.color = "var(--text-secondary)";
            btnDsModeVisual.style.borderBottom = "none";
            if (dsVisualEditor) dsVisualEditor.style.display = "none";
            if (dsRawEditor) dsRawEditor.style.display = "block";
        });
    }

    function compileDsToText() {
        if (!designSystemInput) return;
        const prim = (dsColorPrimaryText && dsColorPrimaryText.value) || "#4f46e5";
        const sec = (dsColorSecondaryText && dsColorSecondaryText.value) || "#ec4899";
        const font = (dsFont && dsFont.value) || "Inter, sans-serif";
        const theme = (dsTheme && dsTheme.value) || "Neutre / Moderne (Clair/Sombre dynamique)";
        const rad = (dsRadius && dsRadius.value) || "8px (Standard fluide)";
        const space = (dsSpacing && dsSpacing.value) || "Confortable (Standard)";

        const lines = [
            `Couleurs de marque : Primaire: ${prim}, Secondaire/Accent: ${sec}`,
            `Typographie : ${font}`,
            `Style global / Thème : ${theme}`,
            `Bordures & Arrondis : ${rad}`,
            `Espacements & Marges : ${space}`
        ];
        designSystemInput.value = lines.join("\n");
        if (currentProjectData) currentProjectData.design_system = designSystemInput.value;
    }

    function parseTextToDs(text) {
        if (!text) return;
        
        // Match Primary Color
        const primMatch = text.match(/Couleurs de marque\s*:\s*Primaire:\s*(#[0-9a-fA-F]{3,6})/i);
        if (primMatch && dsColorPrimaryText && dsColorPrimary) {
            dsColorPrimaryText.value = primMatch[1];
            dsColorPrimary.value = primMatch[1];
        }
        
        // Match Secondary Color
        const secMatch = text.match(/Secondaire\/Accent:\s*(#[0-9a-fA-F]{3,6})/i);
        if (secMatch && dsColorSecondaryText && dsColorSecondary) {
            dsColorSecondaryText.value = secMatch[1];
            dsColorSecondary.value = secMatch[1];
        }
        
        // Match Font Family
        const fontMatch = text.match(/Typographie\s*:\s*([^\n]+)/i);
        if (fontMatch && dsFont) {
            const val = fontMatch[1].trim();
            for (let opt of dsFont.options) {
                if (opt.value === val || val.includes(opt.value.split(',')[0])) {
                    dsFont.value = opt.value;
                    break;
                }
            }
        }
        
        // Match Theme
        const themeMatch = text.match(/Style global \/ Thème\s*:\s*([^\n]+)/i);
        if (themeMatch && dsTheme) {
            const val = themeMatch[1].trim();
            for (let opt of dsTheme.options) {
                if (opt.value === val || val.includes(opt.value.split(' ')[0])) {
                    dsTheme.value = opt.value;
                    break;
                }
            }
        }
        
        // Match Radius
        const radMatch = text.match(/Bordures & Arrondis\s*:\s*([^\n]+)/i);
        if (radMatch && dsRadius) {
            const val = radMatch[1].trim();
            for (let opt of dsRadius.options) {
                if (opt.value === val || val.includes(opt.value.split(' ')[0])) {
                    dsRadius.value = opt.value;
                    break;
                }
            }
        }
        
        // Match Spacing
        const spaceMatch = text.match(/Espacements & Marges\s*:\s*([^\n]+)/i);
        if (spaceMatch && dsSpacing) {
            const val = spaceMatch[1].trim();
            for (let opt of dsSpacing.options) {
                if (opt.value === val || val.includes(opt.value.split(' ')[0])) {
                    dsSpacing.value = opt.value;
                    break;
                }
            }
        }
    }

    // Hook change events on visual controls
    if (dsColorPrimary) {
        dsColorPrimary.addEventListener("input", () => {
            if (dsColorPrimaryText) dsColorPrimaryText.value = dsColorPrimary.value;
            compileDsToText();
        });
    }
    if (dsColorPrimaryText) {
        dsColorPrimaryText.addEventListener("input", () => {
            const val = dsColorPrimaryText.value.trim();
            if (/^#[0-9a-fA-F]{3,6}$/.test(val) && dsColorPrimary) {
                dsColorPrimary.value = val;
            }
            compileDsToText();
        });
    }
    if (dsColorSecondary) {
        dsColorSecondary.addEventListener("input", () => {
            if (dsColorSecondaryText) dsColorSecondaryText.value = dsColorSecondary.value;
            compileDsToText();
        });
    }
    if (dsColorSecondaryText) {
        dsColorSecondaryText.addEventListener("input", () => {
            const val = dsColorSecondaryText.value.trim();
            if (/^#[0-9a-fA-F]{3,6}$/.test(val) && dsColorSecondary) {
                dsColorSecondary.value = val;
            }
            compileDsToText();
        });
    }
    [dsFont, dsTheme, dsRadius, dsSpacing].forEach(el => {
        if (el) el.addEventListener("change", compileDsToText);
    });

    async function saveDesignSystem(useSource) {
        if (!currentProjectId) { appendSystemMessage && appendSystemMessage("Crée/ouvre un projet d'abord."); return; }
        if (dsVisualEditor && dsVisualEditor.style.display !== "none") {
            compileDsToText();
        }
        const val = designSystemInput ? designSystemInput.value : "";
        const body = useSource ? { source: val } : { design_system: val };
        try {
            const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/design-system`, {
                method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
            });
            const d = await r.json();
            if (designSystemInput) {
                designSystemInput.value = d.design_system || "";
                parseTextToDs(d.design_system);
            }
            if (currentProjectData) currentProjectData.design_system = d.design_system || "";
        } catch (e) { /* silencieux */ }
    }
    if (btnDsSave) btnDsSave.addEventListener("click", () => saveDesignSystem(false));
    if (btnDsExtract) btnDsExtract.addEventListener("click", () => saveDesignSystem(true));

    const btnDsUrl = document.getElementById("btn-ds-url");
    if (btnDsUrl) {
        btnDsUrl.addEventListener("click", async () => {
            if (!currentProjectId) { appendSystemMessage && appendSystemMessage("Ouvre un projet d'abord."); return; }
            const url = prompt("URL du site dont extraire la charte (couleurs / typographie) :");
            if (!url || !/^https?:\/\//i.test(url)) return;
            btnDsUrl.disabled = true;
            const old = btnDsUrl.textContent; btnDsUrl.textContent = "⏳ Extraction…";
            try {
                const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/design-system`, {
                    method: "PUT", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url: url.trim() })
                });
                const d = await r.json();
                if (designSystemInput) {
                    designSystemInput.value = d.design_system || "";
                    parseTextToDs(d.design_system);
                }
                if (currentProjectData) currentProjectData.design_system = d.design_system || "";
                if (!(d.design_system || "").trim())
                    appendSystemMessage && appendSystemMessage("Aucune couleur/police détectée sur cette page.");
            } catch (e) {
                appendConsoleLine && appendConsoleLine("stderr", "[Charte URL] échec : " + e.message);
            } finally { btnDsUrl.disabled = false; btnDsUrl.textContent = old; }
        });
    }

    // Modèles de départ : pré-remplissent un prompt riche (évite le « blank canvas »).
    const STARTER_TEMPLATES = {
        landing: "Crée une landing page moderne et responsive pour [PRODUIT] : hero plein écran (titre accrocheur, sous-titre, CTA), section 3 avantages avec icônes, témoignages, et footer. Style premium glassmorphism, palette soignée, micro-animations.",
        deck: "Crée une présentation PowerPoint (.pptx) de 7 slides pour pitcher [PROJET] : couverture, problème, solution, marché, produit, business model, contact. Épuré et professionnel, ≤6 lignes par slide, sans débordement.",
        onepager: "Crée un one-pager HTML imprimable pour [SUJET] : en-tête avec titre + accroche, 3-4 sections concises, un visuel clé, et un encadré contact. Mise en page claire, typographie soignée.",
        dashboard: "Crée un dashboard analytique moderne (HTML + Chart.js via CDN) : 4 cartes KPI, 2 graphiques (ligne + barres), thème sombre glassmorphism, responsive.",
        chart: "Génère un script Python (matplotlib) qui trace [DONNÉES] avec un style moderne (couleurs soignées, grille discrète, pas de fond gris). Termine par plt.show().",
        react: "Crée un composant React interactif `App` pour [FONCTIONNALITÉ] (ex. todo list, calculateur, tableau filtrable). Utilise les hooks (React.useState/useEffect) et des classes Tailwind, design premium et responsive. Pas d'import/export.",
        mermaid: "Crée un diagramme Mermaid pour [SUJET] (ex. flowchart d'un processus, sequenceDiagram d'une API, erDiagram d'une base). Syntaxe Mermaid pure, claire et bien structurée.",
    };
    // Sliders WYSIWYG : ajustent l'aperçu HTML EN DIRECT en injectant un <style> dans le
    // document de l'iframe (srcdoc same-origin → contentDocument accessible). Réappliqué au
    // (re)chargement de l'iframe.
    const adjustToolbar = document.getElementById("adjust-toolbar");
    const adjAccent = document.getElementById("adj-accent");
    const adjRadius = document.getElementById("adj-radius");
    const adjFont = document.getElementById("adj-font");
    const adjReset = document.getElementById("adj-reset");
    const adjSave = document.getElementById("adj-save");
    function applyAdjustments() {
        try {
            const doc = htmlPreviewFrame && htmlPreviewFrame.contentDocument;
            if (!doc || !doc.head) return;
            let s = doc.getElementById("ad-adjust");
            if (!s) { s = doc.createElement("style"); s.id = "ad-adjust"; doc.head.appendChild(s); }
            const accent = adjAccent.value;
            const radius = adjRadius.value;
            const font = (parseInt(adjFont.value, 10) || 100) / 100;
            s.textContent =
                `:root{--accent:${accent}!important;--primary:${accent}!important;` +
                `--accent-color:${accent}!important;--brand:${accent}!important;--accent-cyan:${accent}!important;}\n` +
                `html{font-size:${(16 * font).toFixed(1)}px!important;}\n` +
                `:where(button,input,select,textarea,img,.card,.btn,[class*="card"],[class*="btn"],[class*="panel"])` +
                `{border-radius:${radius}px!important;}`;
        } catch (e) { /* cross-origin improbable (srcdoc) */ }
    }
    [adjAccent, adjRadius, adjFont].forEach(el => el && el.addEventListener("input", applyAdjustments));
    if (adjReset) adjReset.addEventListener("click", () => {
        if (adjAccent) adjAccent.value = "#6366f1";
        if (adjRadius) adjRadius.value = 12;
        if (adjFont) adjFont.value = 100;
        applyAdjustments();
    });
    if (adjSave) {
        adjSave.addEventListener("click", async () => {
            if (!currentProjectId) return;
            const accent = adjAccent.value;
            const radius = adjRadius.value;
            const font = adjFont.value;
            const newDesignSystem = `Couleur d'accent principale : ${accent}\nArrondi des bordures (border-radius) : ${radius}px\nTaille de police (font-size multiplier) : ${font}%`;
            try {
                const resp = await fetch(`/api/athenadesign/projects/${currentProjectId}/design_system`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ design_system: newDesignSystem })
                });
                if (resp.ok) {
                    if (designSystemInput) {
                        designSystemInput.value = newDesignSystem;
                        parseTextToDs(newDesignSystem);
                    }
                    if (currentProjectData) currentProjectData.design_system = newDesignSystem;
                    showToast("💾 Charte graphique enregistrée avec succès !");
                } else {
                    showToast("⚠️ Échec de l'enregistrement de la charte.");
                }
            } catch (err) {
                console.error("Error saving design system:", err);
                showToast("⚠️ Erreur réseau lors de la sauvegarde.");
            }
        });
    }
    // Route Selector navigation logic
    const routeSelector = document.getElementById("design-route-selector");
    if (routeSelector && htmlPreviewFrame) {
        routeSelector.addEventListener("change", (e) => {
            const val = e.target.value;
            if (!val) return;
            
            const doc = htmlPreviewFrame.contentDocument || htmlPreviewFrame.contentWindow.document;
            if (val.startsWith("#")) {
                if (doc) {
                    const el = doc.getElementById(val.substring(1));
                    if (el) {
                        el.scrollIntoView({ behavior: "smooth" });
                    }
                }
            } else if (val === "/") {
                if (htmlPreviewFrame.srcdoc) {
                    htmlPreviewFrame.srcdoc = htmlPreviewFrame.srcdoc;
                } else if (htmlPreviewFrame.src) {
                    htmlPreviewFrame.src = htmlPreviewFrame.src;
                }
            } else {
                try {
                    if (htmlPreviewFrame.contentWindow) {
                        htmlPreviewFrame.contentWindow.location.href = val;
                    }
                } catch (err) {
                    htmlPreviewFrame.src = val;
                }
            }
        });
    }

    if (htmlPreviewFrame) {
        htmlPreviewFrame.addEventListener("load", () => {
            applyAdjustments();
            applyAllCurrentTweaks();
            setupIframeInspector();
            
            // Dynamic route detection inside iframe DOM
            try {
                const doc = htmlPreviewFrame.contentDocument || htmlPreviewFrame.contentWindow.document;
                if (doc && routeSelector) {
                    const currentVal = routeSelector.value;
                    routeSelector.innerHTML = '<option value="/">Page d\'accueil</option>';
                    
                    // 1. Anchors / Sections
                    const headings = doc.querySelectorAll("h1[id], h2[id], h3[id], section[id], div[id]");
                    if (headings.length > 0) {
                        const optGroup = document.createElement("optgroup");
                        optGroup.label = "Ancres & Sections";
                        headings.forEach(el => {
                            const id = el.id;
                            const text = el.textContent.trim().substring(0, 30) || (el.tagName.toLowerCase() + "#" + id);
                            const opt = document.createElement("option");
                            opt.value = "#" + id;
                            opt.textContent = `#${id} (${text})`;
                            optGroup.appendChild(opt);
                        });
                        routeSelector.appendChild(optGroup);
                    }
                    
                    // 2. Links
                    const links = doc.querySelectorAll("a[href]");
                    const localLinks = new Set();
                    links.forEach(a => {
                        const href = a.getAttribute("href");
                        if (href && !href.startsWith("http") && !href.startsWith("javascript") && href !== "#" && href !== "") {
                            localLinks.add(href);
                        }
                    });
                    
                    if (localLinks.size > 0) {
                        const optGroup = document.createElement("optgroup");
                        optGroup.label = "Liens internes";
                        localLinks.forEach(href => {
                            const opt = document.createElement("option");
                            opt.value = href;
                            opt.textContent = href;
                            optGroup.appendChild(opt);
                        });
                        routeSelector.appendChild(optGroup);
                    }
                    
                    routeSelector.value = currentVal;
                }
            } catch (e) {
                console.warn("Cross-origin or empty iframe when detecting routes:", e);
            }
        });
    }

    const btnShare = document.getElementById("btn-share");
    if (btnShare) {
        btnShare.addEventListener("click", async () => {
            if (!currentProjectId) { appendSystemMessage && appendSystemMessage("Ouvre un projet d'abord."); return; }
            try {
                const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/share`, { method: "POST" });
                const d = await r.json();
                const link = window.location.origin + d.url;
                try { await navigator.clipboard.writeText(link); } catch (e) {}
                window.prompt("Lien de partage (lecture seule) — copié :", link);
            } catch (e) {
                appendConsoleLine && appendConsoleLine("stderr", "[Partage] échec : " + e.message);
            }
        });
    }

    if (btnExportPdf) {
        btnExportPdf.addEventListener("click", async () => {
            if (!currentProjectId) return;
            const vnum = (currentVersionIndex != null) ? currentVersionIndex + 1 : undefined;
            btnExportPdf.disabled = true;
            try {
                const r = await fetch("/api/athenadesign/export/pdf", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ project_id: currentProjectId, version_num: vnum })
                });
                if (!r.ok) throw new Error("HTTP " + r.status);
                const url = URL.createObjectURL(await r.blob());
                const a = document.createElement("a");
                a.href = url; a.download = (currentProjectData && currentProjectData.name ? currentProjectData.name : "design") + ".pdf";
                document.body.appendChild(a); a.click(); a.remove();
                setTimeout(() => URL.revokeObjectURL(url), 10000);
            } catch (e) {
                appendConsoleLine && appendConsoleLine("stderr", "[Export PDF] échec : " + e.message);
            } finally { btnExportPdf.disabled = false; }
        });
    }

    document.querySelectorAll(".starter-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const tpl = STARTER_TEMPLATES[chip.getAttribute("data-tpl")];
            if (tpl && promptInput) {
                promptInput.value = tpl;
                promptInput.focus();
                promptInput.setSelectionRange(tpl.indexOf("["), tpl.indexOf("]") + 1 || tpl.length);
            }
        });
    });
    let editor = null;
    let fallbackMode = false;
    let currentCode = "";
    let currentLanguage = "html";

    // Annotation Drawing State
    let isCommentMode = false;
    let activeTool = "point"; // point, brush, rect
    let activeColor = "#ef4444";
    let isDrawing = false;
    let startX = 0, startY = 0;
    let lastX = 0, lastY = 0;
    let currentDrawingPoints = [];
    let currentRect = null;
    let temporaryCommentData = null;

    // Setup Theme Toggle
    themeToggleBtn.addEventListener("click", () => {
        document.body.classList.toggle("light-theme");
        document.body.classList.toggle("dark-theme");
        const isDark = document.body.classList.contains("dark-theme");
        if (editor) {
            monaco.editor.setTheme(isDark ? "vs-dark" : "vs");
        }
    });

    // Setup Provider Fields Toggle
    aiProviderSelect.addEventListener("change", () => {
        const provider = aiProviderSelect.value;
        // 'athena' = API LLM intégrée d'Athena (clés/endpoint côté serveur) → comme 'mock',
        // aucun champ clé/modèle à saisir.
        if (provider === "mock" || provider === "athena") {
            apiKeyGroup.style.display = "none";
            modelGroup.style.display = "none";
        } else {
            apiKeyGroup.style.display = "block";
            modelGroup.style.display = "block";
            
            // Suggest default models
            if (provider === "gemini") {
                modelNameInput.placeholder = "Ex: gemini-2.5-flash";
                if (!modelNameInput.value) modelNameInput.value = "gemini-2.5-flash";
            } else if (provider === "anthropic") {
                modelNameInput.placeholder = "Ex: claude-3-5-sonnet-latest";
                if (!modelNameInput.value) modelNameInput.value = "claude-3-5-sonnet-latest";
            } else if (provider === "openai") {
                modelNameInput.placeholder = "Ex: gpt-4o-mini";
                if (!modelNameInput.value) modelNameInput.value = "gpt-4o-mini";
            }
        }
    });

    // Monaco Editor Initialization
    function initMonaco() {
        if (typeof require === "undefined") {
            console.warn("Monaco Loader not available. Falling back to textarea.");
            enableFallbackEditor();
            return;
        }
        
        require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.39.0/min/vs' } });
        require(['vs/editor/editor.main'], function () {
            fallbackCodeArea.style.display = "none";
            
            editor = monaco.editor.create(document.getElementById('editor-container'), {
                value: currentCode,
                language: currentLanguage,
                theme: document.body.classList.contains("dark-theme") ? 'vs-dark' : 'vs',
                automaticLayout: true,
                fontSize: 14,
                fontFamily: "'Fira Code', monospace",
                minimap: { enabled: false },
                roundedSelection: true,
                scrollBeyondLastLine: false,
                cursorBlinking: "smooth",
                cursorSmoothCaretAnimation: "on"
            });
            
            editor.onDidChangeModelContent(() => {
                currentCode = editor.getValue();
            });
        });
    }

    function enableFallbackEditor() {
        fallbackMode = true;
        fallbackCodeArea.style.display = "block";
        fallbackCodeArea.value = currentCode;
        fallbackCodeArea.addEventListener("input", (e) => {
            currentCode = e.target.value;
        });
    }

    function setEditorValue(code, lang) {
        currentCode = code;
        currentLanguage = lang;
        if (editor) {
            editor.setValue(code);
            monaco.editor.setModelLanguage(editor.getModel(), lang);
        } else if (fallbackMode) {
            fallbackCodeArea.value = code;
        }
    }

    // Initialize Monaco
    initMonaco();

    // Tab Management
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            const tabName = btn.getAttribute("data-tab");
            document.getElementById(`tab-${tabName}`).classList.add("active");
        });
    });

    // --- ANNOTATIONS DRAWING ENGINE ---
    function getActiveCanvas() {
        if (currentProjectData && currentProjectData.versions[currentVersionIndex]) {
            const ver = currentProjectData.versions[currentVersionIndex];
            if (ver.type === "python") {
                return {
                    canvas: pythonDrawingCanvas,
                    overlay: pythonAnnotationOverlay,
                    pins: pythonCommentPinsContainer
                };
            }
        }
        return {
            canvas: drawingCanvas,
            overlay: annotationOverlay,
            pins: commentPinsContainer
        };
    }

    function resizeCanvases() {
        const active = getActiveCanvas();
        [drawingCanvas, pythonDrawingCanvas].forEach(canvas => {
            if (!canvas) return;
            const parent = canvas.parentElement;
            if (parent) {
                canvas.width = parent.clientWidth;
                canvas.height = parent.clientHeight;
            }
        });
    }

    window.addEventListener("resize", resizeCanvases);

    function getMousePos(canvas, e) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }

    function handleCanvasMouseDown(e) {
        const { canvas } = getActiveCanvas();
        if (!canvas || activeTool === "point") return;
        
        isDrawing = true;
        const pos = getMousePos(canvas, e);
        lastX = pos.x;
        lastY = pos.y;
        startX = pos.x;
        startY = pos.y;
        currentDrawingPoints = [pos];
    }

    function handleCanvasMouseMove(e) {
        const { canvas } = getActiveCanvas();
        if (!canvas || !isDrawing) return;
        
        const pos = getMousePos(canvas, e);
        const ctx = canvas.getContext("2d");
        
        if (activeTool === "brush") {
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(pos.x, pos.y);
            ctx.strokeStyle = activeColor;
            ctx.lineWidth = 4;
            ctx.stroke();
            lastX = pos.x;
            lastY = pos.y;
            currentDrawingPoints.push(pos);
        } else if (activeTool === "rect") {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.beginPath();
            ctx.strokeStyle = activeColor;
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);
            ctx.rect(startX, startY, pos.x - startX, pos.y - startY);
            ctx.stroke();
            ctx.setLineDash([]);
            currentRect = {
                x: Math.min(startX, pos.x),
                y: Math.min(startY, pos.y),
                w: Math.abs(pos.x - startX),
                h: Math.abs(pos.y - startY)
            };
        }
    }

    function handleCanvasMouseUp(e) {
        if (!isDrawing) return;
        isDrawing = false;
        
        const { canvas } = getActiveCanvas();
        const pos = getMousePos(canvas, e);
        
        let x = 0, y = 0, w = 0, h = 0;
        let drawingData = "";
        
        if (activeTool === "brush" && currentDrawingPoints.length > 0) {
            const xs = currentDrawingPoints.map(p => p.x);
            const ys = currentDrawingPoints.map(p => p.y);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            
            x = minX + (maxX - minX) / 2;
            y = minY + (maxY - minY) / 2;
            w = maxX - minX;
            h = maxY - minY;
            
            drawingData = canvas.toDataURL();
        } else if (activeTool === "rect" && currentRect) {
            x = currentRect.x + currentRect.w / 2;
            y = currentRect.y + currentRect.h / 2;
            w = currentRect.w;
            h = currentRect.h;
            
            // Draw clean solid rectangle
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.beginPath();
            ctx.strokeStyle = activeColor;
            ctx.lineWidth = 2;
            ctx.rect(currentRect.x, currentRect.y, w, h);
            ctx.stroke();
            
            drawingData = canvas.toDataURL();
        }
        
        temporaryCommentData = {
            x: (x / canvas.width) * 100,
            y: (y / canvas.height) * 100,
            width: (w / canvas.width) * 100,
            height: (h / canvas.height) * 100,
            drawing_data: drawingData,
            tool: activeTool,
            color: activeColor
        };
        
        showCommentPopup(pos.x, pos.y);
    }

    function handleCanvasClick(e) {
        if (activeTool !== "point") return;
        
        const { canvas } = getActiveCanvas();
        const pos = getMousePos(canvas, e);
        
        temporaryCommentData = {
            x: (pos.x / canvas.width) * 100,
            y: (pos.y / canvas.height) * 100,
            width: 0,
            height: 0,
            drawing_data: "",
            tool: activeTool,
            color: activeColor
        };
        
        showCommentPopup(pos.x, pos.y);
    }

    function showCommentPopup(x, y) {
        commentPopup.style.display = "flex";
        
        const container = commentPopup.parentElement;
        const maxLeft = container.clientWidth - commentPopup.clientWidth - 20;
        const maxTop = container.clientHeight - commentPopup.clientHeight - 20;
        
        let left = Math.min(x + 15, maxLeft);
        let top = Math.min(y + 15, maxTop);
        
        commentPopup.style.left = `${Math.max(15, left)}px`;
        commentPopup.style.top = `${Math.max(15, top)}px`;
        commentPopup.style.right = "auto";
        
        commentTextInput.value = "";
        commentTextInput.focus();
    }

    let hoveredElement = null;

    function setupIframeInspector() {
        if (!htmlPreviewFrame) return;
        try {
            const doc = htmlPreviewFrame.contentDocument;
            if (!doc || !doc.body) return;

            let s = doc.getElementById("athena-inspector-style");
            if (!s) {
                s = doc.createElement("style");
                s.id = "athena-inspector-style";
                s.textContent = `
                    #athena-inspector-highlight {
                        position: absolute !important;
                        pointer-events: none !important;
                        outline: 2px dashed #00f0ff !important;
                        outline-offset: -2px !important;
                        background: rgba(0, 240, 255, 0.08) !important;
                        z-index: 999999 !important;
                        transition: all 0.05s ease !important;
                        display: none;
                    }
                    #athena-inspector-label {
                        position: absolute !important;
                        top: -20px !important;
                        left: 0 !important;
                        background: #00f0ff !important;
                        color: #000000 !important;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                        font-size: 10px !important;
                        font-weight: bold !important;
                        padding: 2px 6px !important;
                        border-radius: 3px !important;
                        white-space: nowrap !important;
                        pointer-events: none !important;
                        z-index: 1000000 !important;
                        line-height: 1.2 !important;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.3) !important;
                    }
                `;
                doc.head.appendChild(s);
            }

            let highlightDiv = doc.getElementById("athena-inspector-highlight");
            if (!highlightDiv) {
                highlightDiv = doc.createElement("div");
                highlightDiv.id = "athena-inspector-highlight";
                
                const labelSpan = doc.createElement("span");
                labelSpan.id = "athena-inspector-label";
                highlightDiv.appendChild(labelSpan);
                
                doc.body.appendChild(highlightDiv);
            }

            doc.removeEventListener("mouseover", onIframeMouseOver);
            doc.removeEventListener("mouseout", onIframeMouseOut);
            doc.removeEventListener("click", onIframeClick, true);
            doc.removeEventListener("click", onIframeLinkClick);

            doc.addEventListener("mouseover", onIframeMouseOver);
            doc.addEventListener("mouseout", onIframeMouseOut);
            doc.addEventListener("click", onIframeClick, true);
            doc.addEventListener("click", onIframeLinkClick);
        } catch (e) {
            console.warn("Inspector bind skipped:", e);
        }
    }

    function onIframeMouseOver(e) {
        if (!isCommentMode || activeTool !== "inspect") return;
        
        if (e.target.id === "athena-inspector-highlight" || e.target.id === "athena-inspector-label") {
            return;
        }
        
        e.stopPropagation();
        hoveredElement = e.target;
        
        // Save and change cursor for visual feedback
        hoveredElement._originalCursor = hoveredElement.style.cursor;
        hoveredElement.style.cursor = "pointer";
        
        const doc = htmlPreviewFrame.contentDocument;
        if (!doc) return;
        
        const highlightDiv = doc.getElementById("athena-inspector-highlight");
        const labelSpan = doc.getElementById("athena-inspector-label");
        if (!highlightDiv || !labelSpan) return;

        const rect = hoveredElement.getBoundingClientRect();
        const scrollTop = doc.documentElement.scrollTop || doc.body.scrollTop;
        const scrollLeft = doc.documentElement.scrollLeft || doc.body.scrollLeft;

        highlightDiv.style.width = `${rect.width}px`;
        highlightDiv.style.height = `${rect.height}px`;
        highlightDiv.style.top = `${rect.top + scrollTop}px`;
        highlightDiv.style.left = `${rect.left + scrollLeft}px`;
        highlightDiv.style.display = "block";

        const tag = hoveredElement.tagName.toLowerCase();
        const id = hoveredElement.id ? `#${hoveredElement.id}` : "";
        const classes = hoveredElement.className && typeof hoveredElement.className === "string" 
            ? `.${hoveredElement.className.trim().split(/\s+/)[0]}` 
            : "";
        labelSpan.textContent = `${tag}${id}${classes}`;
    }

    function onIframeMouseOut(e) {
        if (!isCommentMode || activeTool !== "inspect") return;
        
        if (hoveredElement) {
            hoveredElement.style.cursor = hoveredElement._originalCursor || "";
        }
        
        const doc = htmlPreviewFrame.contentDocument;
        if (!doc) return;
        
        const highlightDiv = doc.getElementById("athena-inspector-highlight");
        if (highlightDiv) {
            highlightDiv.style.display = "none";
        }
        hoveredElement = null;
    }

    function onIframeClick(e) {
        if (!isCommentMode || activeTool !== "inspect") return;
        
        e.preventDefault();
        e.stopPropagation();

        if (!hoveredElement) return;

        const tag = hoveredElement.tagName.toLowerCase();
        const textContent = hoveredElement.textContent.trim().substring(0, 40).replace(/[\n\r]+/g, " ");

        const doc = htmlPreviewFrame.contentDocument;
        if (doc) {
            const highlightDiv = doc.getElementById("athena-inspector-highlight");
            if (highlightDiv) highlightDiv.style.display = "none";
        }

        const iframeRect = htmlPreviewFrame.getBoundingClientRect();
        const elemRect = hoveredElement.getBoundingClientRect();

        const xPercent = ((elemRect.left + elemRect.width / 2) / iframeRect.width) * 100;
        const yPercent = ((elemRect.top + elemRect.height / 2) / iframeRect.height) * 100;

        temporaryCommentData = {
            x: xPercent,
            y: yPercent,
            width: (elemRect.width / iframeRect.width) * 100,
            height: (elemRect.height / iframeRect.height) * 100,
            drawing_data: "",
            tool: "inspect",
            color: "#00f0ff",
            tagName: tag,
            tagText: textContent
        };

        // Générer des suggestions contextuelles intelligentes
        let suggestions = [];
        if (["button", "a"].includes(tag) || (tag === "input" && ["submit", "button"].includes(hoveredElement.type))) {
            suggestions = [
                "Changer la couleur du bouton",
                "Ajouter un effet de survol (lueur/zoom)",
                "Agrandir ce bouton",
                "Modifier le texte de ce bouton"
            ];
        } else if (["img", "svg", "video"].includes(tag)) {
            suggestions = [
                "Remplacer cette image",
                "Ajouter des coins arrondis",
                "Passer l'image en noir et blanc",
                "Ajuster la taille / dimensions"
            ];
        } else if (["h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "strong", "em", "li"].includes(tag)) {
            suggestions = [
                "Modifier ce texte",
                "Changer la police / couleur du texte",
                "Centrer ce bloc de texte",
                "Augmenter la taille du texte"
            ];
        } else {
            suggestions = [
                "Ajouter une ombre portée (card shadow)",
                "Changer la couleur de fond de cette zone",
                "Rendre cette zone entièrement responsive",
                "Ajouter une animation d'entrée"
            ];
        }

        bubbleSuggestionsList.innerHTML = "";
        suggestions.forEach(sug => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "bubble-chip";
            btn.textContent = sug;
            btn.addEventListener("click", () => {
                submitVisualCommentWithText(sug);
            });
            bubbleSuggestionsList.appendChild(btn);
        });

        bubbleTargetElement.textContent = `<${tag}>`;
        bubbleCustomInput.value = "";
        
        contextMenuBubble.style.display = "flex";
        commentPopup.style.display = "none";
        
        const container = contextMenuBubble.parentElement;
        const maxLeft = container.clientWidth - contextMenuBubble.clientWidth - 20;
        const maxTop = container.clientHeight - contextMenuBubble.clientHeight - 20;
        
        const left = elemRect.left + elemRect.width / 2;
        const top = elemRect.top + elemRect.height / 2;
        
        let popupLeft = Math.min(left + 15, maxLeft);
        let popupTop = Math.min(top + 15, maxTop);
        
        contextMenuBubble.style.left = `${Math.max(15, popupLeft)}px`;
        contextMenuBubble.style.top = `${Math.max(15, popupTop)}px`;
        contextMenuBubble.style.right = "auto";
        bubbleCustomInput.focus();
    }

    function onIframeLinkClick(e) {
        const a = e.target.closest("a");
        if (a) {
            const href = a.getAttribute("href");
            if (href && href.startsWith("#") && href !== "#") {
                return;
            }
            e.preventDefault();
            e.stopPropagation();
            showToast("ℹ️ Navigation désactivée dans l'aperçu.");
        }
    }

    function showToast(message) {
        let toast = document.getElementById("athena-global-toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "athena-global-toast";
            toast.className = "athena-toast";
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.classList.add("show");
        
        clearTimeout(toast._timeout);
        toast._timeout = setTimeout(() => {
            toast.classList.remove("show");
        }, 3000);
    }

    function updateOverlayPointerEvents() {
        if (!annotationOverlay) return;
        if (isCommentMode && activeTool === "inspect") {
            annotationOverlay.style.pointerEvents = "none";
            setupIframeInspector();
        } else {
            annotationOverlay.style.pointerEvents = "auto";
            try {
                const doc = htmlPreviewFrame?.contentDocument;
                if (doc) {
                    const highlightDiv = doc.getElementById("athena-inspector-highlight");
                    if (highlightDiv) highlightDiv.style.display = "none";
                }
            } catch (e) {}
        }
    }

    function clearDrawing() {
        [drawingCanvas, pythonDrawingCanvas].forEach(canvas => {
            if (canvas) {
                const ctx = canvas.getContext("2d");
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        });
    }

    function toggleCommentMode(forceState) {
        isCommentMode = forceState !== undefined ? forceState : !isCommentMode;
        btnCommentMode.classList.toggle("active", isCommentMode);
        
        if (isCommentMode) {
            annotationToolbar.style.display = "flex";
            commentsSidebar.style.display = "flex";
            
            const ver = currentProjectData.versions[currentVersionIndex];
            if (ver && ver.type === "python") {
                pythonAnnotationOverlay.style.display = "block";
                annotationOverlay.style.display = "none";
            } else {
                annotationOverlay.style.display = "block";
                pythonAnnotationOverlay.style.display = "none";
            }
            
            setTimeout(resizeCanvases, 100);
            updateCursorClass();
            updateOverlayPointerEvents();
        } else {
            annotationToolbar.style.display = "none";
            annotationOverlay.style.display = "none";
            pythonAnnotationOverlay.style.display = "none";
            commentPopup.style.display = "none";
            if (contextMenuBubble) contextMenuBubble.style.display = "none";
            
            // Clear iframe highlight
            try {
                const doc = htmlPreviewFrame?.contentDocument;
                if (doc) {
                    const highlightDiv = doc.getElementById("athena-inspector-highlight");
                    if (highlightDiv) highlightDiv.style.display = "none";
                }
            } catch (e) {}
            
            const ver = currentProjectData?.versions[currentVersionIndex];
            if (ver && ver.comments && ver.comments.length > 0) {
                commentsSidebar.style.display = "flex";
            } else {
                commentsSidebar.style.display = "none";
            }
            clearDrawing();
            updateOverlayPointerEvents();
        }
    }

    function updateCursorClass() {
        const { overlay } = getActiveCanvas();
        if (!overlay) return;
        
        if (activeTool === "brush") {
            overlay.classList.add("cursor-brush");
        } else {
            overlay.classList.remove("cursor-brush");
        }
    }

    // Bind canvas event listeners
    [drawingCanvas, pythonDrawingCanvas].forEach(canvas => {
        if (!canvas) return;
        canvas.addEventListener("mousedown", handleCanvasMouseDown);
        canvas.addEventListener("mousemove", handleCanvasMouseMove);
        canvas.addEventListener("mouseup", handleCanvasMouseUp);
        canvas.addEventListener("click", handleCanvasClick);
    });

    btnCommentMode.addEventListener("click", () => toggleCommentMode());
    btnClosePopup.addEventListener("click", () => {
        commentPopup.style.display = "none";
        clearDrawing();
    });
    btnCloseBubble?.addEventListener("click", () => {
        contextMenuBubble.style.display = "none";
        clearDrawing();
    });
    btnSubmitComment.addEventListener("click", submitVisualComment);
    btnSubmitBubble?.addEventListener("click", () => {
        const text = bubbleCustomInput.value.trim();
        if (text) submitVisualCommentWithText(text);
    });
    bubbleCustomInput?.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            const text = bubbleCustomInput.value.trim();
            if (text) submitVisualCommentWithText(text);
        }
    });
    btnClearDrawing.addEventListener("click", clearDrawing);

    // Toolbar Tool Selection
    const toolBtns = document.querySelectorAll(".tool-btn");
    toolBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            toolBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeTool = btn.getAttribute("data-tool");
            updateCursorClass();
            updateOverlayPointerEvents();
        });
    });

    // Toolbar Color Selection
    const colorPills = document.querySelectorAll(".color-pill");
    colorPills.forEach(pill => {
        pill.addEventListener("click", () => {
            colorPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            activeColor = pill.getAttribute("data-color");
        });
    });

    // Submit Visual Comment
    async function submitVisualComment() {
        const text = commentTextInput.value.trim();
        if (!text || !temporaryCommentData) return;
        submitVisualCommentWithText(text);
    }

    async function submitVisualCommentWithText(text) {
        if (!text || !temporaryCommentData) return;
        
        const currentVersion = currentProjectData.versions[currentVersionIndex];
        const versionNum = currentVersion.version;
        
        commentPopup.style.display = "none";
        if (contextMenuBubble) contextMenuBubble.style.display = "none";
        
        try {
            const resp = await fetch(`/api/athenadesign/projects/${currentProjectId}/versions/${versionNum}/comments`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: text,
                    x: temporaryCommentData.x,
                    y: temporaryCommentData.y,
                    width: temporaryCommentData.width,
                    height: temporaryCommentData.height,
                    tool: temporaryCommentData.tool,
                    color: temporaryCommentData.color,
                    drawing_data: temporaryCommentData.drawing_data,
                    tag_name: temporaryCommentData.tagName || "",
                    tag_text: temporaryCommentData.tagText || ""
                })
            });
            
            const comment = await resp.json();
            
            if (!currentVersion.comments) {
                currentVersion.comments = [];
            }
            currentVersion.comments.push(comment);
            
            clearDrawing();
            renderVersionCommentsAndPins();
            
            // AI Visual Context injection
            let regionDesc = `[Modification ciblée`;
            if (comment.tool === "inspect") {
                regionDesc += ` sur l'élément <${comment.tag_name || 'html'}> contenant "${comment.tag_text || ''}"]`;
            } else if (comment.tool === "point") {
                regionDesc += ` à l'emplacement x=${Math.round(comment.x)}%, y=${Math.round(comment.y)}%]`;
            } else {
                regionDesc += ` sur la zone x=${Math.round(comment.x)}%, y=${Math.round(comment.y)}%, largeur=${Math.round(comment.width)}%, hauteur=${Math.round(comment.height)}%]`;
            }
            
            const aiPrompt = `${regionDesc} : "${comment.text}"`;
            
            toggleCommentMode(false);
            appendMessage("user", aiPrompt);
            
            appStatus.textContent = "Génération...";
            appStatus.className = "status-badge generating";
            promptInput.disabled = true;
            
            const payload = {
                project_id: currentProjectId,
                prompt: aiPrompt,
                provider: aiProviderSelect.value,
                api_key: apiKeyInput.value,
                model_name: modelNameInput.value
            };
            
            const chatResp = await fetch("/api/athenadesign/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            
            const data = await chatResp.json();
            currentProjectData.history = data.history;
            currentProjectData.versions.push(data.version);

            appendMessage("assistant", data.version.explanation);
            loadVersion(currentProjectData.versions.length - 1);
            showGenerationUsage(data.version);
            appStatus.className = "status-badge success";
            
            await loadProjects();
        } catch (e) {
            console.error("Error saving comment or calling AI", e);
            appendSystemMessage("⚠️ Une erreur est survenue lors de la communication.");
        } finally {
            promptInput.disabled = false;
        }
    }

    // Render Version Comments and Pins
    function renderVersionCommentsAndPins() {
        commentPinsContainer.innerHTML = "";
        pythonCommentPinsContainer.innerHTML = "";
        versionCommentsList.innerHTML = "";
        
        if (!currentProjectData || !currentProjectData.versions || currentVersionIndex === null) {
            return;
        }
        
        const ver = currentProjectData.versions[currentVersionIndex];
        const comments = ver.comments || [];
        
        if (comments.length === 0) {
            versionCommentsList.innerHTML = '<div class="comment-sidebar-empty">Aucun commentaire sur cette version.</div>';
            return;
        }
        
        const activePinsContainer = ver.type === "python" ? pythonCommentPinsContainer : commentPinsContainer;
        
        comments.forEach((c, idx) => {
            const num = idx + 1;
            
            const pin = document.createElement("div");
            pin.className = "comment-marker";
            pin.style.left = `${c.x}%`;
            pin.style.top = `${c.y}%`;
            pin.style.backgroundColor = c.color;
            pin.textContent = num;
            pin.setAttribute("data-comment-id", c.id);
            
            pin.addEventListener("mouseenter", () => {
                const card = document.getElementById(`comment-card-${c.id}`);
                if (card) card.style.borderColor = c.color;
            });
            pin.addEventListener("mouseleave", () => {
                const card = document.getElementById(`comment-card-${c.id}`);
                if (card) card.style.borderColor = "var(--panel-border)";
            });
            
            activePinsContainer.appendChild(pin);
            
            const card = document.createElement("div");
            card.id = `comment-card-${c.id}`;
            card.className = "comment-card";
            card.style.setProperty("--accent-danger", c.color);
            
            let toolBadge = c.tool.toUpperCase();
            if (c.tool === "inspect") {
                toolBadge = c.tag_name ? `&lt;${c.tag_name.toLowerCase()}&gt;` : "INSPECT";
            }
            card.innerHTML = `
                <div class="comment-card-header">
                    <span class="comment-card-index" style="color: ${c.color}">Épingle #${num} (${toolBadge})</span>
                </div>
                <div class="comment-card-text">${c.text}</div>
            `;
            
            card.addEventListener("mouseenter", () => {
                pin.style.transform = "translate(-50%, -50%) scale(1.25)";
            });
            card.addEventListener("mouseleave", () => {
                pin.style.transform = "translate(-50%, -50%) scale(1)";
            });
            
            versionCommentsList.appendChild(card);
        });
        
        safeCreateIcons();
    }

    // --- PROJECT & CHAT CONTROLS ---

    async function loadProjects() {
        try {
            const resp = await fetch("/api/athenadesign/projects");
            const projects = await resp.json();
            
            projectsList.innerHTML = "";
            if (projects.length === 0) {
                projectsList.innerHTML = '<div class="project-item empty">Aucun projet</div>';
                return;
            }
            
            projects.forEach(p => {
                const item = document.createElement("div");
                item.className = `project-item ${p.id === currentProjectId ? 'active' : ''}`;
                item.style.display = "flex";
                item.style.alignItems = "center";
                item.style.gap = "6px";
                item.innerHTML = `
                    <div class="project-info" style="flex:1;min-width:0;cursor:pointer;">
                        <div class="project-name">${p.name}</div>
                        <div class="project-meta">${p.versions_count} versions</div>
                    </div>
                    <button class="project-delete-btn" title="Supprimer ce projet" style="background:none;border:none;color:#ff5c5c;cursor:pointer;font-size:0.95rem;padding:2px 6px;opacity:0.65;flex:none;">🗑️</button>
                `;
                item.querySelector(".project-info").addEventListener("click", () => selectProject(p.id));
                item.querySelector(".project-delete-btn").addEventListener("click", async (e) => {
                    e.stopPropagation();
                    if (!confirm(`Supprimer définitivement le projet « ${p.name} » et ses fichiers ?`)) return;
                    try {
                        const r = await fetch(`/api/athenadesign/projects/${encodeURIComponent(p.id)}?remove_files=true`, { method: "DELETE" });
                        if (!r.ok) { alert("Échec de la suppression du projet."); return; }
                        if (p.id === currentProjectId) currentProjectId = null;
                        await loadProjects();
                    } catch (err) { alert("Erreur lors de la suppression."); }
                });
                projectsList.appendChild(item);
            });
        } catch (e) {
            console.error("Error loading projects", e);
        }
    }

    async function createNewProject() {
        const name = `Projet ${Math.floor(1000 + Math.random() * 9000)}`;
        try {
            const resp = await fetch("/api/athenadesign/projects/new", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name })
            });
            const project = await resp.json();
            currentProjectId = project.id;
            
            currentProjectData = project;
            currentVersionIndex = null;
            currentProjectTitle.textContent = project.name;
            
            chatMessages.innerHTML = "";
            appendSystemMessage("Nouveau projet créé ! Décrivez le design que vous souhaitez réaliser.");
            resetCanvas();
            
            await loadProjects();
        } catch (e) {
            console.error("Error creating project", e);
        }
    }

    btnNewProject.addEventListener("click", createNewProject);

    // #9 — Importer un DOSSIER complet (sous-dossiers inclus) dans le projet ouvert.
    // Les fichiers atterrissent dans le workspace du projet, PARTAGÉ avec la partie Code (#5).
    const btnImportFolder = document.getElementById("btn-import-folder");
    const importFolderInput = document.getElementById("import-folder-input");
    if (btnImportFolder && importFolderInput) {
        btnImportFolder.addEventListener("click", () => {
            if (!currentProjectId) {
                appendSystemMessage && appendSystemMessage("Ouvre ou crée un projet avant d'importer un dossier.");
                return;
            }
            importFolderInput.value = "";
            importFolderInput.click();
        });
        importFolderInput.addEventListener("change", async () => {
            const files = Array.from(importFolderInput.files || []);
            if (!files.length || !currentProjectId) return;
            appendSystemMessage && appendSystemMessage(`Import de ${files.length} fichier(s) en cours…`);
            const fd = new FormData();
            files.forEach(f => {
                fd.append("files", f, f.name);
                fd.append("paths", f.webkitRelativePath || f.name);
            });
            try {
                const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/upload`, { method: "POST", body: fd });
                if (!r.ok) {
                    const e = await r.json().catch(() => ({}));
                    appendSystemMessage && appendSystemMessage("Échec de l'import : " + (e.detail || r.status));
                    return;
                }
                const res = await r.json();
                appendSystemMessage && appendSystemMessage(
                    `Dossier importé : ${res.uploaded} fichier(s)${res.skipped ? `, ${res.skipped} ignoré(s)` : ""}. Fichiers partagés avec la partie Code.`);
            } catch (err) {
                appendSystemMessage && appendSystemMessage("Erreur réseau pendant l'import : " + err);
            } finally {
                importFolderInput.value = "";
            }
        });
    }

    async function selectProject(projectId) {
        try {
            currentProjectId = projectId;
            const resp = await fetch(`/api/athenadesign/projects/${projectId}`);
            const project = await resp.json();
            currentProjectData = project;
            if (designSystemInput) {
                 designSystemInput.value = project.design_system || "";
                 parseTextToDs(project.design_system);
             }
            const _dsDetails = document.getElementById("design-system-group");
            if (_dsDetails) _dsDetails.open = !!(project.design_system || "").trim();
            clearAttachments();

            currentProjectTitle.textContent = project.name;
            
            document.querySelectorAll(".project-item").forEach(item => {
                item.classList.remove("active");
            });
            
            chatMessages.innerHTML = "";
            if (project.history.length === 0) {
                appendSystemMessage("Projet vide. Décrivez ce que vous souhaitez créer !");
            } else {
                project.history.forEach(msg => {
                    appendMessage(msg.role, msg.content);
                });
            }
            
            if (project.versions && project.versions.length > 0) {
                loadVersion(project.versions.length - 1);
            } else {
                // Pas de version Design : si le projet (souvent créé/édité côté Code) a une page
                // web dans son workspace PARTAGÉ (#5), on l'affiche en aperçu. Sinon canvas vide.
                let shown = false;
                try {
                    const er = await fetch(`/api/athenadesign/projects/${projectId}/workspace-entry`);
                    if (er.ok) {
                        const ej = await er.json();
                        if (ej && ej.entry) { showWorkspacePreview(projectId, ej.entry); shown = true; }
                    }
                } catch (e) { /* silencieux */ }
                if (!shown) resetCanvas();
            }

            // Bascule « Code de base / Design » (visible quand le projet a À LA FOIS un code
            // de base à la racine et une sortie Design). Mode actif déduit de ce qu'on affiche.
            await refreshSourceToggle(projectId, (project.versions && project.versions.length > 0) ? "design" : null);

            await loadProjects();
        } catch (e) {
            console.error("Error loading project", e);
        }
    }

    let activeViewport = "desktop"; // desktop, tablet, mobile

    function applyViewport(viewport) {
        activeViewport = viewport;
        
        // Remove current classes
        previewFrameContainer.classList.remove("responsive-desktop", "responsive-tablet", "responsive-mobile");
        
        // Add new class
        previewFrameContainer.classList.add(`responsive-${viewport}`);
        
        // Update button states
        respBtns.forEach(btn => {
            const vp = btn.getAttribute("data-viewport");
            btn.classList.toggle("active", vp === viewport);
        });
        
        // Scale preview to fit container if needed
        scalePreviewViewport();
        
        // Resize canvases to fit new size
        setTimeout(() => {
            resizeCanvases();
            scalePreviewViewport();
        }, 250);
    }

    function scalePreviewViewport() {
        const wrapper = document.querySelector(".preview-viewport-wrapper");
        if (!wrapper || !previewFrameContainer) return;
        
        const wrapperWidth = wrapper.clientWidth - 48; // padding
        const wrapperHeight = wrapper.clientHeight - 48;
        
        let targetWidth = 0;
        let targetHeight = 0;
        
        if (activeViewport === "tablet") {
            targetWidth = 768;
            targetHeight = wrapperHeight * 0.95;
        } else if (activeViewport === "mobile") {
            targetWidth = 375;
            targetHeight = wrapperHeight * 0.95;
        } else {
            // Desktop: no scaling
            previewFrameContainer.style.transform = "none";
            return;
        }
        
        const scaleX = wrapperWidth / targetWidth;
        const scaleY = wrapperHeight / targetHeight;
        const scale = Math.min(1, scaleX, scaleY);
        
        if (scale < 1) {
            previewFrameContainer.style.transform = `scale(${scale})`;
            previewFrameContainer.style.transformOrigin = "center center";
        } else {
            previewFrameContainer.style.transform = "none";
        }
    }

    window.addEventListener("resize", scalePreviewViewport);

    // Enveloppe un composant React (JSX) dans une page autonome (React+ReactDOM+Babel+Tailwind
    // via CDN) pour l'aperçu live. Équivalent de generator.react_scaffold côté serveur.
    function buildReactPreview(code) {
        const body = (code || "")
            // Imports ES retirés (React/hooks/Tailwind sont déjà globaux) — gère le MULTI-LIGNE
            // (`import {\n a,\n b\n} from 'react'`) que l'ancien strip ligne-à-ligne ratait,
            // laissant un `import` survivant → « import declarations may only appear at top level ».
            .replace(/import\b[\s\S]*?from\s*['"][^'"]+['"];?/g, "")
            .replace(/import\s*['"][^'"]+['"];?/g, "")
            .replace(/^\s*export\s+default\s+/gm, "")
            .replace(/^\s*export\s+/gm, "")
            // Le modèle ajoute PARFOIS lui-même le montage (malgré la consigne) ou le reprend du
            // code de base → on retire tout échafaudage/montage existant AVANT d'ajouter le nôtre,
            // sinon double déclaration `_C` / double render → erreur de compilation.
            .replace(/^\s*const\s+_C\s*=.*$/gm, "")
            .replace(/^.*ReactDOM\s*\.\s*createRoot[^\n]*$/gm, "")
            .replace(/^\s*ReactDOM\s*\.\s*render[^\n]*$/gm, "")
            .replace(/^\s*\w+\s*\.\s*render\s*\(\s*<\s*App[^\n]*$/gm, "");
        // Code utilisateur complet (prélude hooks + composant + montage). On NE l'exécute PAS
        // via <script type="text/babel"> (qui, en cas d'erreur de syntaxe, laisse un écran BLANC
        // muet) : on le compile via Babel.transform dans un TRY/CATCH explicite → toute erreur
        // (compilation OU exécution) s'affiche dans l'iframe ET remonte au parent (overlay auto-fix).
        const userScript =
            'const {useState,useEffect,useRef,useMemo,useCallback,useReducer,useContext,Fragment}=React;\n'
            + body
            + '\nconst _C=(typeof App!=="undefined"?App:(typeof Component!=="undefined"?Component:'
            + 'function(){return React.createElement("div",{style:{padding:24}},"Aucun composant App trouvé.");}));\n'
            + 'ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(_C));\n';
        // Stocké dans un <script type="text/plain"> (non exécuté) ; on neutralise un </script> littéral.
        const safeUser = userScript.replace(/<\/script/gi, '<\\/script');
        return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            + '<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"><\/script>'
            + '<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"><\/script>'
            + '<script src="https://unpkg.com/@babel/standalone/babel.min.js"><\/script>'
            + '<script src="https://cdn.tailwindcss.com"><\/script>'
            + '<style>body{margin:0;font-family:Inter,system-ui,sans-serif}'
            + '#__err{display:none;padding:24px;color:#e11d48;background:#161616;white-space:pre-wrap;'
            + 'font:13px/1.6 ui-monospace,Menlo,Consolas,monospace}<\/style></head>'
            + '<body><div id="root"></div><pre id="__err"></pre>'
            + '<script type="text/plain" id="__src">' + safeUser + '<\/script>'
            + '<script>(function(){'
            + 'function showErr(msg){var e=document.getElementById("__err");if(e){e.style.display="block";'
            + 'e.textContent="\\u26a0\\ufe0f Aperçu React — "+msg;}'
            + 'try{window.parent.postMessage({type:"iframe-log",level:"stderr",message:msg},"*");}catch(_){}}'
            + 'window.addEventListener("DOMContentLoaded",function(){'
            + 'if(typeof Babel==="undefined"){showErr("Babel non chargé (réseau ?).");return;}'
            + 'var src=document.getElementById("__src").textContent;var compiled;'
            + 'try{compiled=Babel.transform(src,{presets:[["react",{runtime:"classic"}]]}).code;}'
            + 'catch(err){showErr("Erreur de compilation : "+((err&&err.message)||err));return;}'
            + 'try{var s=document.createElement("script");s.textContent=compiled;document.body.appendChild(s);}'
            + 'catch(err){showErr("Erreur d\'exécution : "+((err&&err.message)||err));}'
            + '});})();<\/script>'
            + '</body></html>';
    }

    // Enveloppe un diagramme Mermaid dans une page autonome (mermaid.js via CDN). Code échappé
    // (vit dans <pre>) ; mermaid lit le textContent déséchappé. Équivalent serveur : mermaid_scaffold.
    function buildMermaidPreview(code) {
        const esc = (code || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            + '<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"><\/script>'
            + '<style>body{margin:0;padding:24px;display:flex;justify-content:center;'
            + 'font-family:Inter,system-ui,sans-serif;background:#fff}.mermaid{max-width:100%}<\/style></head>'
            + '<body><pre class="mermaid">' + esc + '</pre>'
            + '<script>try{mermaid.initialize({startOnLoad:true,theme:"default"});}catch(e){}<\/script>'
            + '</body></html>';
    }

    // HTML d'aperçu selon le type d'artefact web.
    function buildWebPreview(ver) {
        if (ver.type === "react") return buildReactPreview(ver.code);
        if (ver.type === "mermaid") return buildMermaidPreview(ver.code);
        return ver.code;
    }
    const WEB_TYPES = ["html", "react", "mermaid"];

    function injectConsoleBridge(htmlCode) {
        let injection = `
<script>
(function() {
    // Bruits CDN bénins (pas des erreurs) : on les ignore pour ne pas polluer ni déclencher
    // l'overlay d'erreur (ex. l'avertissement "production" de Tailwind CDN dans un aperçu).
    const NOISE = ['cdn.tailwindcss.com should not be used in production'];
    const sendLog = (type, msg) => {
        if (NOISE.some(n => (msg || '').indexOf(n) !== -1)) return;
        window.parent.postMessage({ type: 'iframe-log', level: type, message: msg }, '*');
    };
    const wrap = (level, orig) => function(...args) {
        const msg = args.map(x => {
            if (typeof x === 'object') {
                try { return JSON.stringify(x); } catch(e) { return String(x); }
            }
            return String(x);
        }).join(' ');
        // SEULE une vraie erreur (console.error / window.onerror) → 'stderr' (déclenche l'overlay
        // « corriger »). Les warnings restent informatifs ('stdout') et ne bloquent pas l'aperçu.
        sendLog(level === 'error' ? 'stderr' : 'stdout', msg);
        if (orig) orig.apply(console, args);
    };
    console.log = wrap('log', console.log);
    console.info = wrap('info', console.info);
    console.warn = wrap('warn', console.warn);
    console.error = wrap('error', console.error);
    window.addEventListener('error', e => {
        sendLog('stderr', e.message + ' (' + e.filename + ':' + e.lineno + ':' + e.colno + ')');
    });
})();
</script>
`;
        // Filet de sécurité Lucide : si le design utilise des icônes <i data-lucide="…">
        // mais NE charge PAS la librairie, on l'injecte (CDN) + init — sinon icônes invisibles.
        const usesLucide = /data-lucide\s*=/i.test(htmlCode);
        const loadsLucide = /lucide(@|\.min|\.js|\/lucide)|createIcons\s*\(/i.test(htmlCode);
        if (usesLucide && !loadsLucide) {
            injection += `
<script src="https://unpkg.com/lucide@latest"></script>
<script>window.addEventListener('DOMContentLoaded',function(){try{lucide.createIcons();}catch(e){}});</script>
`;
        }

        // Filet de sécurité Tailwind CSS
        const usesTailwind = /class\s*=\s*['"][^'"]*(?:bg-|text-|flex|grid|p-|m-|w-|h-|hover:)[^'"]*['"]/i.test(htmlCode);
        const loadsTailwind = /tailwindcss|cdn\.tailwindcss/i.test(htmlCode);
        if (usesTailwind && !loadsTailwind) {
            injection += `
<script src="https://cdn.tailwindcss.com"></script>
`;
        }
        if (htmlCode.includes('<head>')) {
            return htmlCode.replace('<head>', '<head>' + injection);
        } else if (htmlCode.includes('<body>')) {
            return htmlCode.replace('<body>', '<body>' + injection);
        } else {
            return injection + htmlCode;
        }
    }

    // Responsive Buttons Click listeners
    respBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const vp = btn.getAttribute("data-viewport");
            applyViewport(vp);
        });
    });

    // Refresh Preview Button listener
    btnRefreshPreview.addEventListener("click", () => {
        if (currentWorkspacePreview) {
            // Mode workspace : recharge la page depuis le dossier (cache-bust).
            const { projectId, entry } = currentWorkspacePreview;
            htmlPreviewFrame.src = `/api/athenadesign/projects/${projectId}/workspace/${entry}?t=${Date.now()}`;
            appendConsoleLine("system", "[Aperçu] Rechargement depuis le workspace...");
            return;
        }
        if (currentVersionIndex !== null && currentProjectData) {
            const ver = currentProjectData.versions[currentVersionIndex];
            if (ver && WEB_TYPES.includes(ver.type)) {
                htmlPreviewFrame.srcdoc = injectConsoleBridge(buildWebPreview(ver));
                appendConsoleLine("system", "[Aperçu] Rechargement de l'iframe...");
            }
        }
    });

    // Open External Button listener
    btnOpenExternal.addEventListener("click", () => {
        if (currentWorkspacePreview) {
            const { projectId, entry } = currentWorkspacePreview;
            window.open(`/api/athenadesign/projects/${projectId}/workspace/${entry}`, "_blank");
            return;
        }
        if (currentProjectId && currentVersionIndex !== null && currentProjectData) {
            const ver = currentProjectData.versions[currentVersionIndex];
            if (ver && WEB_TYPES.includes(ver.type)) {
                const url = `/api/athenadesign/projects/${currentProjectId}/versions/${ver.version}/raw`;
                window.open(url, "_blank");
            }
        }
    });

    // Bascule de source : voir le CODE DE BASE (racine, intact) vs la sortie DESIGN.
    document.getElementById("btn-src-base")?.addEventListener("click", () => {
        if (!currentProjectId || !currentSources.base) return;
        showWorkspacePreview(currentProjectId, currentSources.base);
        setSourceToggleActive("base");
    });
    document.getElementById("btn-src-design")?.addEventListener("click", () => {
        if (!currentProjectId) return;
        if (currentProjectData && currentProjectData.versions && currentProjectData.versions.length > 0) {
            loadVersion(currentProjectData.versions.length - 1);
        } else if (currentSources.design) {
            showWorkspacePreview(currentProjectId, currentSources.design);
        }
        setSourceToggleActive("design");
    });

    // Bridge to forward messages from the HTML preview iframe
    window.addEventListener("message", (e) => {
        if (e.data && e.data.type === "iframe-log") {
            const level = e.data.level; // "stdout" or "stderr"
            appendConsoleLine(level, `[Aperçu] ${e.data.message}`);
            if (level === "stderr" && previewErrorOverlay && previewErrorMessage) {
                previewErrorMessage.textContent = e.data.message;
                previewErrorOverlay.style.display = "flex";
                if (typeof lucide !== 'undefined') lucide.createIcons();
            }
        } else if (e.data && e.data.type === "athena:refresh-projects") {
            // La liste des projets est partagée avec la partie Code : l'app hôte demande
            // un rafraîchissement à l'ouverture de l'onglet Design (projets créés ailleurs).
            try { loadProjects(); } catch (_) {}
        }
    });

    btnCloseError?.addEventListener("click", () => {
        if (previewErrorOverlay) previewErrorOverlay.style.display = "none";
    });

    btnAutofixError?.addEventListener("click", async () => {
        if (!currentProjectId) return;
        const errorMessage = previewErrorMessage.textContent;
        if (previewErrorOverlay) previewErrorOverlay.style.display = "none";
        
        appStatus.textContent = "Auto-correction...";
        appStatus.className = "status-badge generating";
        
        try {
            const resp = await fetch("/api/athenadesign/autofix", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_id: currentProjectId,
                    error_message: errorMessage,
                    provider: aiProviderSelect.value,
                    api_key: apiKeyInput.value,
                    model_name: modelNameInput.value
                })
            });
            const data = await resp.json();
            if (data.fixed && data.latest_version) {
                currentProjectData.versions.push(data.latest_version);
                loadVersion(currentProjectData.versions.length - 1);
                showToast("✨ Code corrigé avec succès !");
            } else {
                showToast("⚠️ Échec de l'auto-correction.");
            }
        } catch (err) {
            console.error("Autofix failed:", err);
            showToast("⚠️ Erreur réseau de l'auto-correction.");
        } finally {
            appStatus.textContent = "Prêt";
            appStatus.className = "status-badge ready";
        }
    });

    // #5 — Aperçu d'un projet via les FICHIERS de son workspace (partagé avec le Code),
    // quand il n'a pas de « version » Design. L'iframe charge la page par URL (src) pour
    // que les assets relatifs (CSS/JS/images) se résolvent dans le dossier du projet.
    function showWorkspacePreview(projectId, entry) {
        if (previewErrorOverlay) previewErrorOverlay.style.display = "none";
        currentWorkspacePreview = { projectId, entry };
        currentVersionIndex = null;
        const url = `/api/athenadesign/projects/${projectId}/workspace/${entry}`;
        canvasEmptyState.style.display = "none";
        pythonPreviewContainer.style.display = "none";
        previewFrameContainer.style.display = "block";
        htmlPreviewFrame.style.display = "block";
        btnRunPython.style.display = "none";
        btnRefreshPreview.style.display = "flex";
        btnOpenExternal.style.display = "flex";
        responsiveToolbar.style.display = "flex";
        if (btnExportPdf) btnExportPdf.style.display = "flex";
        if (adjustToolbar) adjustToolbar.style.display = "flex";
        applyViewport(activeViewport);
        htmlPreviewFrame.removeAttribute("srcdoc");
        htmlPreviewFrame.src = url;
        // Charge aussi le code de la page dans l'éditeur (lecture).
        fetch(url).then(r => r.ok ? r.text() : "").then(t => { if (t) setEditorValue(t, "html"); }).catch(() => {});
        switchTab("preview");
    }

    // Bascule « Code de base / Design » : récupère les deux sources du projet et n'affiche
    // le sélecteur que si les DEUX coexistent (sinon il n'y a rien à comparer).
    async function refreshSourceToggle(projectId, activeMode) {
        currentSources = { base: null, design: null };
        try {
            const r = await fetch(`/api/athenadesign/projects/${projectId}/sources`);
            if (r.ok) currentSources = await r.json();
        } catch (e) { /* silencieux */ }
        const toggle = document.getElementById("source-toggle");
        const hasBoth = !!(currentSources.base && currentSources.design);
        if (toggle) toggle.style.display = hasBoth ? "flex" : "none";
        if (!hasBoth) return;
        setSourceToggleActive(activeMode || (currentWorkspacePreview ? "base" : "design"));
    }

    function setSourceToggleActive(mode) {
        const map = { base: document.getElementById("btn-src-base"), design: document.getElementById("btn-src-design") };
        Object.entries(map).forEach(([k, el]) => {
            if (!el) return;
            const on = (k === mode);
            el.style.opacity = on ? "1" : "0.5";
            el.style.fontWeight = on ? "700" : "400";
        });
    }

    function resetCanvas() {
        currentWorkspacePreview = null;
        const _st = document.getElementById("source-toggle");
        if (_st) _st.style.display = "none";
        htmlPreviewFrame.style.display = "none";
        previewFrameContainer.style.display = "none";
        pythonPreviewContainer.style.display = "none";
        canvasEmptyState.style.display = "flex";
        btnRunPython.style.display = "none";
        
        btnRefreshPreview.style.display = "none";
        btnOpenExternal.style.display = "none";
        responsiveToolbar.style.display = "none";
        
        setEditorValue("", "html");
        versionsTimeline.innerHTML = '<div class="timeline-empty">Aucune version générée pour le moment</div>';
        commentsSidebar.style.display = "none";
        clearDrawing();
    }

    function appendMessage(role, text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = `message ${role}`;
        
        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.innerHTML = `<i data-lucide="${role === 'user' ? 'user' : 'bot'}"></i>`;
        
        const content = document.createElement("div");
        content.className = "msg-content";
        content.innerHTML = formatMessageMarkdown(text);
        
        msgDiv.appendChild(avatar);
        msgDiv.appendChild(content);
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        safeCreateIcons();
    }
    
    function appendSystemMessage(text) {
        appendMessage("system", text);
    }

    // Affiche la consommation de tokens d'une génération (statut + message discret).
    function showGenerationUsage(version) {
        const u = version && version.usage;
        if (u && (u.total_tokens || u.prompt_tokens || u.completion_tokens)) {
            const tot = u.total_tokens || ((u.prompt_tokens || 0) + (u.completion_tokens || 0));
            if (appStatus) appStatus.textContent = `Prêt · ${tot} tokens`;
            appendSystemMessage(`🔢 ${tot} tokens (↑${u.prompt_tokens || 0} entrée · ↓${u.completion_tokens || 0} sortie)`);
        } else if (appStatus) {
            appStatus.textContent = "Prêt";
        }
    }
    
    function formatMessageMarkdown(text) {
        text = text || "";
        let html = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.*?)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>");
            
        if (html.includes("- ")) {
            const lines = html.split("<br>");
            let inList = false;
            for (let i = 0; i < lines.length; i++) {
                if (lines[i].trim().startsWith("- ")) {
                    let content = lines[i].trim().substring(2);
                    if (!inList) {
                        lines[i] = "<ul><li>" + content + "</li>";
                        inList = true;
                    } else {
                        lines[i] = "<li>" + content + "</li>";
                    }
                } else {
                    if (inList) {
                        lines[i] = "</ul>" + lines[i];
                        inList = false;
                    }
                }
            }
            if (inList) html += "</ul>";
            html = lines.join("<br>").replace(/<\/ul><br>/g, "</ul>").replace(/<br><ul>/g, "<ul>");
        }
        return html;
    }

    function loadVersion(index) {
        if (!currentProjectData || !currentProjectData.versions || index >= currentProjectData.versions.length) return;
        
        if (previewErrorOverlay) previewErrorOverlay.style.display = "none";
        
        currentVersionIndex = index;
        currentWorkspacePreview = null;
        const ver = currentProjectData.versions[index];

        canvasEmptyState.style.display = "none";
        
        const lang = ver.type === "python" ? "python"
            : (ver.type === "react" ? "javascript" : (ver.type === "mermaid" ? "markdown" : "html"));
        setEditorValue(ver.code, lang);

        if (WEB_TYPES.includes(ver.type)) {
            pythonPreviewContainer.style.display = "none";
            previewFrameContainer.style.display = "block";
            htmlPreviewFrame.style.display = "block";
            btnRunPython.style.display = "none";

            // Show new preview utility buttons
            btnRefreshPreview.style.display = "flex";
            btnOpenExternal.style.display = "flex";
            responsiveToolbar.style.display = "flex";

            // Apply current responsive viewport
            applyViewport(activeViewport);

            // React → on enveloppe le composant dans une page (React/Babel/Tailwind via CDN).
            htmlPreviewFrame.srcdoc = injectConsoleBridge(buildWebPreview(ver));
            if (btnExportPdf) btnExportPdf.style.display = "flex";
            if (adjustToolbar) adjustToolbar.style.display = "flex";
            switchTab("preview");
        } else if (ver.type === "python") {
            if (btnExportPdf) btnExportPdf.style.display = "none";
            if (adjustToolbar) adjustToolbar.style.display = "none";
            htmlPreviewFrame.style.display = "none";
            previewFrameContainer.style.display = "none";
            pythonPreviewContainer.style.display = "flex";
            btnRunPython.style.display = "flex";
            
            // Hide new preview utility buttons
            btnRefreshPreview.style.display = "none";
            btnOpenExternal.style.display = "none";
            responsiveToolbar.style.display = "none";
            
            pythonPromptRun.style.display = "flex";
            pythonPlotsWrapper.style.display = "none";
            plotsContainer.innerHTML = "";
            pythonExecuting.style.display = "none";
            
            switchTab("preview");
            runPythonCode();
        }
        
        // Render comments
        renderVersionCommentsAndPins();
        renderVersionTweaks(ver);
        renderSuggestions(ver);
        
        if (ver.comments && ver.comments.length > 0) {
            commentsSidebar.style.display = "flex";
        } else if (!isCommentMode) {
            commentsSidebar.style.display = "none";
        }
        
        renderTimeline();
        
        // Adjust Canvas bounding sizes
        setTimeout(resizeCanvases, 200);
    }

    function switchTab(tabName) {
        tabBtns.forEach(btn => {
            if (btn.getAttribute("data-tab") === tabName) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
        tabContents.forEach(c => {
            if (c.id === `tab-${tabName}`) {
                c.classList.add("active");
            } else {
                c.classList.remove("active");
            }
        });
    }

    function renderTimeline() {
        if (!currentProjectData || !currentProjectData.versions || currentProjectData.versions.length === 0) {
            versionsTimeline.innerHTML = '<div class="timeline-empty">Aucune version générée pour le moment</div>';
            return;
        }
        
        versionsTimeline.innerHTML = "";
        for (let i = currentProjectData.versions.length - 1; i >= 0; i--) {
            const v = currentProjectData.versions[i];
            const node = document.createElement("div");
            node.className = `timeline-node ${i === currentVersionIndex ? 'active' : ''}`;
            
            const card = document.createElement("div");
            card.className = `timeline-card ${i === currentVersionIndex ? 'active' : ''}`;
            const explanation = v.explanation || "";
            card.innerHTML = `
                <div class="timeline-card-header">
                    <span class="timeline-version-tag">Version ${v.version} (${v.type.toUpperCase()})</span>
                </div>
                <div class="timeline-prompt">"${v.prompt}"</div>
                <div class="timeline-desc">${explanation.substring(0, 80)}${explanation.length > 80 ? '...' : ''}</div>
            `;
            
            card.addEventListener("click", () => loadVersion(i));
            node.appendChild(card);
            versionsTimeline.appendChild(node);
        }
    }

    // Chat form sending
    // Entrée = ENVOYER le prompt ; Ctrl/Cmd/Maj+Entrée = saut de ligne (cohérent avec le chat).
    promptInput.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        if (e.ctrlKey || e.metaKey) {
            // Ctrl/Cmd(+Maj)+Entrée = saut de ligne (non inséré par défaut dans un textarea).
            e.preventDefault();
            const s = promptInput.selectionStart, en = promptInput.selectionEnd, v = promptInput.value;
            promptInput.value = v.slice(0, s) + "\n" + v.slice(en);
            promptInput.selectionStart = promptInput.selectionEnd = s + 1;
        } else if (!e.shiftKey) {
            // Entrée seule = ENVOYER (Maj+Entrée garde le saut de ligne natif).
            e.preventDefault();
            if (typeof chatForm.requestSubmit === "function") chatForm.requestSubmit();
            else chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
        }
    });

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const promptText = promptInput.value.trim();
        if (!promptText) return;
        
        appendMessage("user", promptText);
        promptInput.value = "";
        
        appStatus.textContent = "Génération...";
        appStatus.className = "status-badge generating";
        promptInput.disabled = true;
        
        const payload = {
            project_id: currentProjectId,
            prompt: promptText,
            provider: aiProviderSelect.value,
            api_key: apiKeyInput.value,
            model_name: modelNameInput.value,
            attachments: pendingAttachments.slice()
        };

        try {
            const resp = await fetch("/api/athenadesign/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            clearAttachments();
            
            if (!resp.ok) throw new Error("Server error");
            const data = await resp.json();
            
            if (!currentProjectId) {
                currentProjectId = data.project_id;
            }
            
            currentProjectData = {
                id: currentProjectId,
                name: currentProjectData ? currentProjectData.name : `Projet ${currentProjectId.substring(0, 4)}`,
                history: data.history,
                versions: currentProjectData ? [...currentProjectData.versions, data.version] : [data.version]
            };
            
            appendMessage("assistant", data.version.explanation);
            loadVersion(currentProjectData.versions.length - 1);
            showGenerationUsage(data.version);
            appStatus.className = "status-badge success";

            await loadProjects();
        } catch (err) {
            console.error(err);
            appendSystemMessage("⚠️ Une erreur est survenue lors de la communication.");
            appStatus.textContent = "Erreur";
            appStatus.className = "status-badge";
        } finally {
            promptInput.disabled = false;
            promptInput.focus();
        }
    });

    // Run Python Code sandboxing
    async function runPythonCode() {
        if (!currentProjectId || !currentCode) return;
        
        pythonPromptRun.style.display = "none";
        pythonExecuting.style.display = "flex";
        pythonPlotsWrapper.style.display = "none";
        plotsContainer.innerHTML = "";
        
        switchTab("console");
        appendConsoleLine("system", `>>> [Démarrage de l'exécution Python dans la sandbox: ${currentProjectId}]`);
        
        try {
            const resp = await fetch("/api/athenadesign/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_id: currentProjectId,
                    code: currentCode
                })
            });
            
            const result = await resp.json();
            
            if (result.stdout) {
                appendConsoleLine("stdout", result.stdout);
            }
            if (result.stderr) {
                appendConsoleLine("stderr", result.stderr);
            }
            
            appendConsoleLine("system", `>>> [Exécution terminée en ${result.execution_time}s - Code retour: ${result.success ? 'Succès (0)' : 'Échec'}]`);
            
            pythonExecuting.style.display = "none";
            plotsContainer.innerHTML = "";

            // AUTO-CORRECTION : si l'exécution a échoué, on demande au serveur de corriger
            // (boucle bornée : renvoie l'erreur au modèle → ré-exécute).
            if (!result.success) {
                appendConsoleLine("system", ">>> [Auto-correction en cours…]");
                try {
                    const fr = await fetch("/api/athenadesign/autofix", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ project_id: currentProjectId })
                    });
                    const fx = await fr.json();
                    if (fx.fixed) {
                        appendConsoleLine("system", `>>> [Auto-correction réussie en ${fx.attempts} essai(s) — version ${fx.versions_count}]`);
                        await selectProject(currentProjectId);
                        loadVersion(currentProjectData.versions.length - 1);
                    } else {
                        appendConsoleLine("stderr", `>>> [Auto-correction : non résolu après ${fx.attempts || 0} essai(s)]`);
                    }
                } catch (e) {
                    appendConsoleLine("stderr", "[Auto-correction] " + e.message);
                }
                return;
            }

            const hasPlots = (result.plots && result.plots.length > 0) || (result.interactive_plots && result.interactive_plots.length > 0);
            const hasOtherFiles = (result.other_files && result.other_files.length > 0);
            
            if (hasPlots || hasOtherFiles) {
                pythonPlotsWrapper.style.display = "block";
                
                if (result.plots) {
                    result.plots.forEach(plotFile => {
                        const wrap = document.createElement("div");
                        wrap.className = "plot-image-wrapper";
                        const img = document.createElement("img");
                        img.alt = "Matplotlib Plot";
                        adFileBlobUrl(currentProjectId, plotFile)
                            .then(u => { img.src = u; })
                            .catch(() => { img.alt = "Erreur de chargement du graphique"; });
                        wrap.appendChild(img);
                        plotsContainer.appendChild(wrap);
                    });
                }

                if (result.interactive_plots) {
                    result.interactive_plots.forEach(plotlyFile => {
                        const wrap = document.createElement("div");
                        wrap.className = "plotly-iframe-wrapper";
                        const ifr = document.createElement("iframe");
                        adFileBlobUrl(currentProjectId, plotlyFile)
                            .then(u => { ifr.src = u; })
                            .catch(() => {});
                        wrap.appendChild(ifr);
                        plotsContainer.appendChild(wrap);
                    });
                }

                if (hasOtherFiles) {
                    const filesHeader = document.createElement("div");
                    filesHeader.className = "other-files-header";
                    filesHeader.innerHTML = `<h3><i data-lucide="file-text"></i> Fichiers générés</h3>`;
                    plotsContainer.appendChild(filesHeader);
                    
                    const filesGrid = document.createElement("div");
                    filesGrid.className = "other-files-grid";
                    
                    result.other_files.forEach(file => {
                        const fileCard = document.createElement("div");
                        fileCard.className = "file-download-card";
                        
                        let iconName = "file";
                        if (file.name.endsWith(".pptx") || file.name.endsWith(".ppt")) {
                            iconName = "presentation";
                        } else if (file.name.endsWith(".csv") || file.name.endsWith(".xlsx")) {
                            iconName = "table";
                        } else if (file.name.endsWith(".pdf")) {
                            iconName = "file-text";
                        }
                        
                        const sizeKB = (file.size / 1024).toFixed(1);

                        fileCard.innerHTML = `
                            <div class="file-icon"><i data-lucide="${iconName}"></i></div>
                            <div class="file-info">
                                <div class="file-name" title="${file.name}">${file.name}</div>
                                <div class="file-size">${sizeKB} KB</div>
                            </div>
                            <button type="button" class="file-download-btn" title="Télécharger">
                                <i data-lucide="download"></i>
                            </button>
                        `;
                        // Téléchargement via fetch authentifié → blob (l'<a download> natif ne
                        // porte pas le Bearer).
                        const _pid = currentProjectId, _name = file.name;
                        fileCard.querySelector(".file-download-btn").addEventListener("click", async () => {
                            try {
                                const url = await adFileBlobUrl(_pid, _name);
                                const a = document.createElement("a");
                                a.href = url; a.download = _name;
                                document.body.appendChild(a); a.click(); a.remove();
                                setTimeout(() => URL.revokeObjectURL(url), 10000);
                            } catch (e) { appendConsoleLine("stderr", "[Téléchargement] échec : " + e.message); }
                        });
                        filesGrid.appendChild(fileCard);
                    });
                    plotsContainer.appendChild(filesGrid);
                }
                
                safeCreateIcons();
                switchTab("preview");
                setTimeout(resizeCanvases, 200);
            } else {
                plotsContainer.innerHTML = `
                    <div class="no-execution-msg">
                        <i data-lucide="check-circle" style="color: var(--accent-success); font-size: 2.5rem; margin-bottom: 8px;"></i>
                        <h3>Script exécuté avec succès</h3>
                        <p>Aucun tracé graphique n'a été produit. Consultez l'onglet Console pour voir le texte de sortie.</p>
                    </div>
                `;
                safeCreateIcons();
            }
        } catch (e) {
            console.error("Execution error", e);
            pythonExecuting.style.display = "none";
            appendConsoleLine("stderr", `Erreur réseau backend: ${e.message}`);
        }
    }

    btnRunPython.addEventListener("click", runPythonCode);

    function appendConsoleLine(type, text) {
        const line = document.createElement("div");
        line.className = `console-line ${type}`;
        line.textContent = text;
        consoleOutput.appendChild(line);
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    btnClearConsole.addEventListener("click", () => {
        consoleOutput.innerHTML = '<div class="console-line system">Console effacée.</div>';
    });

    // Copy Code & Download
    btnCopy.addEventListener("click", () => {
        if (!currentCode) return;
        navigator.clipboard.writeText(currentCode).then(() => {
            const origHTML = btnCopy.innerHTML;
            btnCopy.innerHTML = '<i data-lucide="check" style="color: var(--accent-success)"></i>';
            safeCreateIcons();
            setTimeout(() => {
                btnCopy.innerHTML = origHTML;
                safeCreateIcons();
            }, 1500);
        });
    });

    btnDownload.addEventListener("click", () => {
        if (!currentCode) return;
        const extension = currentLanguage === "python" ? "py" : "html";
        const filename = `athenadesign_export.${extension}`;
        
        const blob = new Blob([currentCode], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    });

    btnHandoff.addEventListener("click", () => {
        if (!currentProjectId || currentVersionIndex === null) {
            showToast("⚠️ Aucun projet ou version sélectionnée.");
            return;
        }
        const versionNum = currentVersionIndex + 1;
        const url = `/api/athenadesign/projects/${currentProjectId}/versions/${versionNum}/handoff`;
        
        const a = document.createElement("a");
        a.href = url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });

    // Tweaks Panel interactions
    btnCloseTweaks?.addEventListener("click", () => {
        tweaksSidebar?.classList.add("collapsed");
        if (btnOpenTweaks) btnOpenTweaks.style.display = "flex";
    });

    btnOpenTweaks?.addEventListener("click", () => {
        tweaksSidebar?.classList.remove("collapsed");
        if (btnOpenTweaks) btnOpenTweaks.style.display = "none";
    });

    function applyAllCurrentTweaks() {
        if (!currentProjectData) return;
        const ver = currentProjectData.versions[currentVersionIndex];
        if (!ver || !ver.tweaks || ver.tweaks.length === 0) return;
        
        const doc = htmlPreviewFrame.contentDocument;
        if (!doc) return;
        
        ver.tweaks.forEach(tweak => {
            const input = document.getElementById(`tweak-input-${tweak.name}`);
            if (input) {
                let value = input.value;
                if (tweak.type === 'slider') {
                    const unitMatch = tweak.values.match(/([a-zA-Z%]+)$/);
                    const unit = unitMatch ? unitMatch[1] : '';
                    value = value + unit;
                } else if (tweak.type === 'toggle') {
                    const valuesList = tweak.values ? tweak.values.split(',') : [];
                    if (valuesList.length >= 2) {
                        value = input.checked ? valuesList[0] : valuesList[1];
                    } else {
                        value = input.checked ? '1' : '0';
                    }
                }
                doc.documentElement.style.setProperty(tweak.name, value);
            }
        });
    }

    function renderVersionTweaks(version) {
        if (!tweaksControlsList) return;
        tweaksControlsList.innerHTML = "";
        
        if (!version.tweaks || version.tweaks.length === 0) {
            tweaksControlsList.innerHTML = '<div class="no-tweaks-msg">Aucun réglage dynamique pour cette version.</div>';
            if (tweaksSidebar) tweaksSidebar.style.display = "none";
            if (btnOpenTweaks) btnOpenTweaks.style.display = "none";
            return;
        }
        
        // Show Sidebar
        if (tweaksSidebar) {
            tweaksSidebar.style.display = "flex";
            tweaksSidebar.classList.remove("collapsed");
        }
        if (btnOpenTweaks) btnOpenTweaks.style.display = "none";
        
        version.tweaks.forEach(tweak => {
            const group = document.createElement("div");
            group.className = "tweak-control-group";
            
            const label = document.createElement("label");
            label.className = "tweak-label";
            label.textContent = tweak.label;
            group.appendChild(label);
            
            const wrapper = document.createElement("div");
            wrapper.className = "tweak-input-wrapper";
            
            if (tweak.type === "color") {
                const input = document.createElement("input");
                input.type = "color";
                input.className = "tweak-color-input";
                input.id = `tweak-input-${tweak.name}`;
                input.value = tweak.default || "#6366f1";
                input.addEventListener("input", () => {
                    const doc = htmlPreviewFrame.contentDocument;
                    if (doc) {
                        doc.documentElement.style.setProperty(tweak.name, input.value);
                    }
                });
                wrapper.appendChild(input);
                
            } else if (tweak.type === "slider") {
                const values = tweak.values.split(",");
                const minRaw = values[0] || "0";
                const maxRaw = values[1] || "100";
                
                const minNum = parseFloat(minRaw) || 0;
                const maxNum = parseFloat(maxRaw) || 100;
                const unitMatch = minRaw.match(/([a-zA-Z%]+)$/) || maxRaw.match(/([a-zA-Z%]+)$/);
                const unit = unitMatch ? unitMatch[1] : "";
                
                const valNum = parseFloat(tweak.default) || minNum;
                
                const input = document.createElement("input");
                input.type = "range";
                input.className = "tweak-slider-input";
                input.id = `tweak-input-${tweak.name}`;
                input.min = minNum;
                input.max = maxNum;
                input.value = valNum;
                
                const valSpan = document.createElement("span");
                valSpan.className = "tweak-slider-val";
                valSpan.textContent = `${valNum}${unit}`;
                
                input.addEventListener("input", () => {
                    const doc = htmlPreviewFrame.contentDocument;
                    if (doc) {
                        doc.documentElement.style.setProperty(tweak.name, `${input.value}${unit}`);
                    }
                    valSpan.textContent = `${input.value}${unit}`;
                });
                
                wrapper.appendChild(input);
                wrapper.appendChild(valSpan);
                
            } else if (tweak.type === "toggle") {
                const switchLabel = document.createElement("label");
                switchLabel.className = "tweak-toggle-switch";
                
                const input = document.createElement("input");
                input.type = "checkbox";
                input.id = `tweak-input-${tweak.name}`;
                input.checked = tweak.default === "true" || tweak.default === "1" || tweak.default === true;
                
                const slider = document.createElement("span");
                slider.className = "tweak-toggle-slider";
                
                switchLabel.appendChild(input);
                switchLabel.appendChild(slider);
                
                input.addEventListener("change", () => {
                    const doc = htmlPreviewFrame.contentDocument;
                    if (doc) {
                        const valuesList = tweak.values ? tweak.values.split(",") : [];
                        let value = input.checked ? "1" : "0";
                        if (valuesList.length >= 2) {
                            value = input.checked ? valuesList[0] : valuesList[1];
                        }
                        doc.documentElement.style.setProperty(tweak.name, value);
                    }
                });
                
                wrapper.appendChild(switchLabel);
                
            } else if (tweak.type === "select") {
                const select = document.createElement("select");
                select.className = "tweak-select";
                select.id = `tweak-input-${tweak.name}`;
                
                const options = tweak.values.split(",");
                options.forEach(opt => {
                    const optTrim = opt.trim();
                    const optionEl = document.createElement("option");
                    optionEl.value = optTrim;
                    optionEl.textContent = optTrim;
                    if (optTrim === tweak.default) {
                        optionEl.selected = true;
                    }
                    select.appendChild(optionEl);
                });
                
                select.addEventListener("change", () => {
                    const doc = htmlPreviewFrame.contentDocument;
                    if (doc) {
                        doc.documentElement.style.setProperty(tweak.name, select.value);
                    }
                });
                
                wrapper.appendChild(select);
            }
            
            group.appendChild(wrapper);
            tweaksControlsList.appendChild(group);
        });

        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function renderSuggestions(version) {
        if (!suggestionsChips) return;
        suggestionsChips.innerHTML = "";
        
        if (!version.suggestions || version.suggestions.length === 0) {
            suggestionsChips.style.display = "none";
            if (starterChips) starterChips.style.display = "flex";
            return;
        }
        
        if (starterChips) starterChips.style.display = "none";
        suggestionsChips.style.display = "flex";
        
        version.suggestions.forEach(sug => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "starter-chip";
            btn.style.background = "linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(79, 70, 229, 0.15) 100%)";
            btn.style.border = "1px solid rgba(99, 102, 241, 0.3)";
            btn.style.color = "#a5b4fc";
            
            btn.innerHTML = `<i data-lucide="sparkles" style="width:13px;height:13px;display:inline-block;margin-right:4px;vertical-align:middle;"></i><span>${sug}</span>`;
            
            btn.addEventListener("click", () => {
                if (promptInput) {
                    promptInput.value = sug;
                    if (typeof chatForm.requestSubmit === "function") chatForm.requestSubmit();
                    else chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
                }
            });
            suggestionsChips.appendChild(btn);
        });
        
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    // Startup Init
    loadProjects().then(() => {
        fetch("/api/athenadesign/projects")
            .then(res => res.json())
            .then(projects => {
                if (projects.length > 0) {
                    selectProject(projects[0].id);
                } else {
                    fetch("/api/athenadesign/projects/new", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ name: "Mon Premier Projet" })
                    })
                    .then(res => res.json())
                    .then(project => {
                        currentProjectId = project.id;
                        selectProject(project.id);
                    });
                }
            });
    });
});
