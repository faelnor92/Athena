// Amorce de l'éditeur OnlyOffice (oo_editor.html). Externalisé pour la CSP
// stricte (script-src sans 'unsafe-inline'). L'api.js du Document Server est
// autorisée par _csp_with_onlyoffice (server.py) qui ajoute son origine à la CSP.
    (function () {
        const params = new URLSearchParams(location.search);
        const path = params.get("path") || "";
        const mode = params.get("mode") || "edit";
        const msg = document.getElementById("msg");
        const token = localStorage.getItem("athena_session_token") || "";

        function fail(html) {
            msg.style.display = "flex";
            msg.innerHTML = '<div class="box err"><h2>Éditeur indisponible</h2>' + html + '</div>';
        }
        if (!path) { fail("Aucun fichier indiqué."); return; }

        const headers = {};
        if (token && token !== "no-auth-required") headers["Authorization"] = "Bearer " + token;

        fetch("/api/redaction/onlyoffice/config?path=" + encodeURIComponent(path) + "&mode=" + encodeURIComponent(mode),
              { headers })
        .then(r => r.json().then(d => ({ ok: r.ok, d })))
        .then(({ ok, d }) => {
            if (!ok) throw new Error(d.detail || "config refusée");
            const dsUrl = (d.ds_url || "").replace(/\/$/, "");
            const s = document.createElement("script");
            s.src = dsUrl + "/web-apps/apps/api/documents/api.js";
            s.onerror = () => fail("Le script de l'éditeur (<code>api.js</code>) est injoignable.<br>"
                + "Vérifie l'URL du Document Server : <code>" + dsUrl + "</code>");
            s.onload = () => {
                try {
                    msg.style.display = "none";
                    d.config.width = "100%"; d.config.height = "100%";
                    let ready = false;
                    const docUrl = (d.config.document && d.config.document.url) || "";
                    let host = docUrl;
                    try { host = new URL(docUrl).origin; } catch (e) {}
                    d.config.events = {
                        onError: (e) => fail("Erreur OnlyOffice : <code>" + JSON.stringify(e && e.data) + "</code>"
                            + "<br>Souvent : le Document Server n'arrive pas à TÉLÉCHARGER le fichier depuis Athena "
                            + "(règle « URL d'Athena vue par OnlyOffice ») ou le secret JWT ne correspond pas."),
                        onDocumentReady: () => { ready = true; document.title = (d.config.document && d.config.document.title) || "Éditeur"; }
                    };
                    new window.DocsAPI.DocEditor("placeholder", d.config);
                    // Diagnostic : si le document ne s'affiche pas en ~22 s, le DS ne joint pas Athena.
                    setTimeout(() => {
                        if (ready) return;
                        fail("Le Document Server n'arrive pas à charger le fichier (il reste sur le squelette).<br><br>"
                            + "Il essaie de le télécharger ici :<br><code>" + host + "</code><br><br>"
                            + "➡️ Cette adresse doit être joignable <b>DEPUIS la machine où tourne OnlyOffice</b>. "
                            + "Teste depuis cette machine : <code>curl -I " + host + "</code><br>"
                            + "Si ça échoue, corrige « URL d'Athena vue par OnlyOffice » (onglet Écriture → ⚙️) "
                            + "avec l'IP LAN d'Athena (ex. <code>http://192.168.1.X:8000</code>), pas localhost ni l'URL Cloudflare.");
                    }, 22000);
                } catch (e) { fail("Initialisation impossible : " + e.message); }
            };
            document.head.appendChild(s);
        })
        .catch(e => fail("Configuration impossible : " + e.message
            + "<br>Vérifie qu'OnlyOffice est configuré (onglet Écriture → ⚙️)."));
    })();
