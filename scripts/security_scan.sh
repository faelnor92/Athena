#!/usr/bin/env bash
# Scan de sécurité d'Athena (local + CI).
#
# Deux niveaux :
#   - INFORMATIF (n'échoue jamais le build) : pip-audit (CVE des deps, souvent transitives/
#     non corrigeables) + bandit COMPLET (toutes sévérités).
#   - BLOQUANT (code de sortie ≠ 0) : bandit HIGH sévérité + HIGH confiance, secrets versionnés,
#     .env suivi par git. → seuil de qualité sans bruit sur les CVE transitives.
#
# Usage : bash scripts/security_scan.sh
# Outils : pip install pip-audit bandit   (outillage dev/CI, non requis au runtime).
set -u
cd "$(dirname "$0")/.." || exit 1
block_rc=0   # seules ces alertes font échouer le build

echo "== [informatif] pip-audit (vulnérabilités des dépendances) =="
if python3 -m pip_audit --version >/dev/null 2>&1; then
    python3 -m pip_audit -r requirements.txt || echo "  (CVE signalées ci-dessus — informatif, non bloquant)"
elif command -v pip-audit >/dev/null 2>&1; then
    pip-audit -r requirements.txt || echo "  (CVE signalées ci-dessus — informatif, non bloquant)"
else
    echo "  pip-audit non installé → 'pip install pip-audit'."
fi

echo; echo "== [informatif] bandit (toutes sévérités) =="
if command -v bandit >/dev/null 2>&1; then
    bandit -q -r core routers tools server.py -x tests,tools/mcp-servers || true
    echo; echo "== [BLOQUANT] bandit HIGH sévérité + HIGH confiance =="
    bandit -q -r core routers tools server.py -x tests,tools/mcp-servers -lll -iii || {
        echo "  ❌ Problème de sécurité HIGH/HIGH détecté → corrige ou justifie (# nosec ciblé)."; block_rc=1; }
else
    echo "  bandit non installé → 'pip install bandit'."
fi

echo; echo "== [BLOQUANT] secrets potentiellement versionnés =="
if git rev-parse --git-dir >/dev/null 2>&1; then
    # On exclut les fichiers de test (fixtures = faux positifs) et les binaires.
    hits=$(git ls-files | grep -Evi '\.(png|jpg|jpeg|gif|ico|lock)$' | grep -Evi '(^|/)tests?/|test_|_test\.' | \
        xargs grep -nEI "(sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{30})" 2>/dev/null)
    if [ -n "$hits" ]; then echo "$hits"; echo "  ❌ secrets potentiels détectés !"; block_rc=1
    else echo "  OK : aucun secret littéral détecté dans les fichiers suivis."; fi
    if git ls-files --error-unmatch .env >/dev/null 2>&1; then echo "  ❌ .env est suivi par git !"; block_rc=1; fi
fi

echo; [ $block_rc -eq 0 ] && echo "✅ Scan : aucune alerte BLOQUANTE." || echo "❌ Scan : alerte(s) bloquante(s) ci-dessus."
exit $block_rc
