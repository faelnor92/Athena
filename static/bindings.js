// Câblage des interactions du HTML statique + actions déléguées du HTML généré.
// Externalisé pour la CSP stricte : script-src sans 'unsafe-inline' interdit les
// attributs onclick/onsubmit/onkeydown — tout passe par addEventListener ici.
// Chargé APRÈS app.js/office.js (les fonctions appelées sont leurs globales).
(function () {
    function on(id, event, fn) {
        const el = document.getElementById(id);
        if (el) el.addEventListener(event, fn);
    }

    // --- Éléments statiques d'index.html ------------------------------------
    on("logo-home", "click", () => document.getElementById("tab-office")?.click());
    on("list-item-add-form", "submit", (e) => { e.preventDefault(); submitNewListItem(); });
    on("btn-agenda-google-pick", "click", () => document.getElementById("agenda-google-file")?.click());
    on("btn-nc-save", "click", () => saveNextcloudConfig());
    on("btn-nc-test", "click", () => testNextcloudConfig());
    on("btn-px-save", "click", () => saveProxmoxConfig());
    on("btn-px-test", "click", () => testProxmoxConfig());
    on("btn-ev-gen", "click", () => {
        const t = document.getElementById("ev-token");
        if (t) t.value = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
    });
    on("btn-ev-save", "click", () => saveEventsConfig());
    on("btn-ev-test", "click", () => testEvent());
    on("btn-ev-log", "click", () => loadRecentEvents());
    on("btn-login-submit", "click", () => submitLogin());
    on("btn-sso-login", "click", () => ssoLogin());
    on("link-register-toggle", "click", (e) => { e.preventDefault(); toggleRegister(); });
    on("btn-register-submit", "click", () => submitRegister());
    document.querySelectorAll(".login-enter-submit").forEach((el) =>
        el.addEventListener("keydown", (e) => { if (e.key === "Enter") submitLogin(); }));

    // --- Actions du HTML GÉNÉRÉ (innerHTML) : délégation par data-act -------
    // Les templates posent data-act (+ data-arg) au lieu d'onclick ; un seul
    // écouteur délégué route vers la fonction. Ajouter ici toute nouvelle action.
    const ACTIONS = {
        "open-artifact": (el) => openArtifact(parseInt(el.dataset.arg, 10)),
        "fork-conv": (el) => forkConversation(el.dataset.arg),
        "select-tree-node": (el) => selectTreeNode(el.dataset.arg),
        "delete-memory-fact": (el) => deleteMemoryFact(el.dataset.arg),
        "delete-agenda-event": (el) => deleteAgendaEvent(el.dataset.arg),
        "toggle-list-item": (el) => toggleListItem(el.dataset.arg),
        "delete-list-item": (el) => deleteListItem(el.dataset.arg),
        "install-mcp-server": (el) => installMarketplaceServer(el.dataset.arg),
    };
    document.addEventListener("click", (e) => {
        const el = e.target.closest("[data-act]");
        if (!el) return;
        const fn = ACTIONS[el.dataset.act];
        if (fn) { e.preventDefault(); fn(el); }
    });

    // Enregistrement du service worker (PWA installable).
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").catch(() => {});
        });
    }
})();
