// VERROU AUTH PRÉ-RENDU (chargé en SYNCHRONE dans <head>, donc bloquant comme
// l'ancien script inline) : si aucune session, on force l'overlay de login AVANT
// la première peinture. Externalisé pour la CSP stricte (script-src sans
// 'unsafe-inline').
try {
    if (!localStorage.getItem("athena_session_token")) {
        document.documentElement.classList.add("needs-login");
    }
} catch (e) { /* stockage inaccessible (mode privé strict) : l'app gère au runtime */ }
