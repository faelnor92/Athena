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

    // Application State
    let currentProjectId = null;
    let currentProjectData = null;
    let currentVersionIndex = null; // 0-indexed in currentProjectData.versions

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

    async function saveDesignSystem(useSource) {
        if (!currentProjectId) { appendSystemMessage && appendSystemMessage("Crée/ouvre un projet d'abord."); return; }
        const val = designSystemInput ? designSystemInput.value : "";
        const body = useSource ? { source: val } : { design_system: val };
        try {
            const r = await fetch(`/api/athenadesign/projects/${currentProjectId}/design-system`, {
                method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
            });
            const d = await r.json();
            if (designSystemInput) designSystemInput.value = d.design_system || "";
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
                if (designSystemInput) designSystemInput.value = d.design_system || "";
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
    if (htmlPreviewFrame) htmlPreviewFrame.addEventListener("load", applyAdjustments);

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
        } else {
            annotationToolbar.style.display = "none";
            annotationOverlay.style.display = "none";
            pythonAnnotationOverlay.style.display = "none";
            commentPopup.style.display = "none";
            
            const ver = currentProjectData?.versions[currentVersionIndex];
            if (ver && ver.comments && ver.comments.length > 0) {
                commentsSidebar.style.display = "flex";
            } else {
                commentsSidebar.style.display = "none";
            }
            clearDrawing();
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
    btnSubmitComment.addEventListener("click", submitVisualComment);
    btnClearDrawing.addEventListener("click", clearDrawing);

    // Toolbar Tool Selection
    const toolBtns = document.querySelectorAll(".tool-btn");
    toolBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            toolBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            activeTool = btn.getAttribute("data-tool");
            updateCursorClass();
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
        
        const currentVersion = currentProjectData.versions[currentVersionIndex];
        const versionNum = currentVersion.version;
        
        commentPopup.style.display = "none";
        
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
                    drawing_data: temporaryCommentData.drawing_data
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
            if (comment.tool === "point") {
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
            
            appStatus.textContent = "Prêt";
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
            card.innerHTML = `
                <div class="comment-card-header">
                    <span class="comment-card-index" style="color: ${c.color}">Épingle #${num} (${c.tool.toUpperCase()})</span>
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
                item.innerHTML = `
                    <div class="project-name">${p.name}</div>
                    <div class="project-meta">${p.versions_count} versions</div>
                `;
                item.addEventListener("click", () => selectProject(p.id));
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

    async function selectProject(projectId) {
        try {
            currentProjectId = projectId;
            const resp = await fetch(`/api/athenadesign/projects/${projectId}`);
            const project = await resp.json();
            currentProjectData = project;
            if (designSystemInput) designSystemInput.value = project.design_system || "";
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
                resetCanvas();
            }
            
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
        
        // Resize canvases to fit new size
        setTimeout(resizeCanvases, 250);
    }

    // Enveloppe un composant React (JSX) dans une page autonome (React+ReactDOM+Babel+Tailwind
    // via CDN) pour l'aperçu live. Équivalent de generator.react_scaffold côté serveur.
    function buildReactPreview(code) {
        const body = (code || "")
            .replace(/^\s*import[^\n]*\n/gm, "")
            .replace(/^\s*export\s+default\s+/gm, "")
            .replace(/^\s*export\s+/gm, "");
        return '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
            + '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            + '<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"><\/script>'
            + '<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"><\/script>'
            + '<script src="https://unpkg.com/@babel/standalone/babel.min.js"><\/script>'
            + '<script src="https://cdn.tailwindcss.com"><\/script>'
            + '<style>body{margin:0;font-family:Inter,system-ui,sans-serif}<\/style></head>'
            + '<body><div id="root"></div>'
            + '<script type="text/babel" data-presets="react">\n'
            + 'const {useState,useEffect,useRef,useMemo,useCallback,useReducer,useContext,Fragment}=React;\n'
            + body
            + '\nconst _C=(typeof App!=="undefined"?App:(typeof Component!=="undefined"?Component:'
            + 'function(){return React.createElement("div",{style:{padding:24}},"Aucun composant App trouvé.");}));\n'
            + 'ReactDOM.createRoot(document.getElementById("root")).render(React.createElement(_C));\n'
            + '<\/script></body></html>';
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
    const sendLog = (type, msg) => {
        window.parent.postMessage({ type: 'iframe-log', level: type, message: msg }, '*');
    };
    const wrap = (level, orig) => function(...args) {
        const msg = args.map(x => {
            if (typeof x === 'object') {
                try { return JSON.stringify(x); } catch(e) { return String(x); }
            }
            return String(x);
        }).join(' ');
        sendLog(level === 'error' || level === 'warn' ? 'stderr' : 'stdout', msg);
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
        if (currentProjectId && currentVersionIndex !== null && currentProjectData) {
            const ver = currentProjectData.versions[currentVersionIndex];
            if (ver && WEB_TYPES.includes(ver.type)) {
                const url = `/api/athenadesign/projects/${currentProjectId}/versions/${ver.version}/raw`;
                window.open(url, "_blank");
            }
        }
    });

    // Bridge to forward messages from the HTML preview iframe
    window.addEventListener("message", (e) => {
        if (e.data && e.data.type === "iframe-log") {
            const level = e.data.level; // "stdout" or "stderr"
            appendConsoleLine(level, `[Aperçu] ${e.data.message}`);
        }
    });

    function resetCanvas() {
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
    
    function formatMessageMarkdown(text) {
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
        
        currentVersionIndex = index;
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
            card.innerHTML = `
                <div class="timeline-card-header">
                    <span class="timeline-version-tag">Version ${v.version} (${v.type.toUpperCase()})</span>
                </div>
                <div class="timeline-prompt">"${v.prompt}"</div>
                <div class="timeline-desc">${v.explanation.substring(0, 80)}${v.explanation.length > 80 ? '...' : ''}</div>
            `;
            
            card.addEventListener("click", () => loadVersion(i));
            node.appendChild(card);
            versionsTimeline.appendChild(node);
        }
    }

    // Chat form sending
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
            
            appStatus.textContent = "Prêt";
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
