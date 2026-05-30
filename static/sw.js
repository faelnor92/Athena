// Service worker minimal pour rendre Jarvis installable (PWA).
// Stratégie réseau d'abord (pas de cache agressif : évite une UI/API périmée).
const CACHE = "jarvis-shell-v1";
const SHELL = ["/", "/index.html", "/app.js", "/style.css", "/manifest.json"];

self.addEventListener("install", (e) => {
    self.skipWaiting();
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})));
});

self.addEventListener("activate", (e) => {
    e.waitUntil(
        caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    );
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    const req = e.request;
    // Ne jamais mettre en cache l'API : toujours réseau.
    if (req.method !== "GET" || new URL(req.url).pathname.startsWith("/api/")) {
        return;
    }
    // Réseau d'abord, repli cache hors-ligne pour le shell.
    e.respondWith(
        fetch(req).then((res) => {
            if (res && res.ok && SHELL.includes(new URL(req.url).pathname)) {
                const copy = res.clone();
                caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return res;
        }).catch(() => caches.match(req))
    );
});
