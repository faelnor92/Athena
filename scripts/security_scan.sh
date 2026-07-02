#!/usr/bin/env bash
# Scan de sécurité d'Athena (local + CI).
#
# Deux niveaux :
#   - INFORMATIF (n'échoue jamais le build) : CVE de deps SANS correctif publié (rien
#     d'actionnable) + bandit COMPLET (toutes sévérités).
#   - BLOQUANT (code de sortie ≠ 0) : CVE de deps AVEC correctif disponible (un bump
#     suffit → l'ignorer est un choix, pas un oubli), bandit HIGH sévérité + HIGH
#     confiance, secrets versionnés, .env suivi par git.
#
# Usage : bash scripts/security_scan.sh
# Outils : pip install pip-audit bandit   (outillage dev/CI, non requis au runtime).
set -u
cd "$(dirname "$0")/.." || exit 1
block_rc=0   # seules ces alertes font échouer le build

echo "== pip-audit (CVE des dépendances) : BLOQUANT si un correctif existe =="
PIP_AUDIT=""
if python3 -m pip_audit --version >/dev/null 2>&1; then PIP_AUDIT="python3 -m pip_audit"
elif command -v pip-audit >/dev/null 2>&1; then PIP_AUDIT="pip-audit"; fi
if [ -n "$PIP_AUDIT" ]; then
    # Un seul passage (résolution des deps lente) : sortie JSON, tri en python.
    # pip_audit sort ≠ 0 dès qu'une CVE existe → on capture sans échouer ici.
    audit_json=$($PIP_AUDIT -r requirements.txt -f json 2>/dev/null || true)
    if [ -n "$audit_json" ]; then
        echo "$audit_json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
deps = data.get("dependencies", data) if isinstance(data, dict) else data
fixable, info = [], []
for dep in deps:
    for v in dep.get("vulns", []):
        line = "  %s %s : %s" % (dep.get("name"), dep.get("version"), v.get("id"))
        fixes = ", ".join(v.get("fix_versions") or [])
        if fixes:
            fixable.append(line + " -> corrige en " + fixes)
        else:
            info.append(line + " (aucun correctif publie - informatif)")
for l in info: print(l)
if fixable:
    print("  [X] CVE avec correctif disponible (bump requis, ou ignore justifie) :")
    for l in fixable: print(l)
    sys.exit(1)
print("  OK : aucune CVE corrigeable dans les dependances.")
' || block_rc=1
    else
        echo "  (pip-audit n'a rien renvoyé — résolution impossible ? informatif)"
    fi
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
