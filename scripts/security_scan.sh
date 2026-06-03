#!/usr/bin/env bash
# Scan de sécurité local d'Athena.
#  - pip-audit : vulnérabilités connues (CVE) des dépendances Python.
#  - bandit    : motifs de code à risque (si installé).
#  - secrets   : détection grossière de secrets versionnés par erreur.
#
# Usage : bash scripts/security_scan.sh
# Outils : pip install pip-audit bandit   (non requis au runtime — outillage dev/CI).
set -u
cd "$(dirname "$0")/.." || exit 1
rc=0

echo "== pip-audit (vulnérabilités des dépendances) =="
if python3 -m pip_audit --version >/dev/null 2>&1; then
    python3 -m pip_audit -r requirements.txt || rc=1
elif command -v pip-audit >/dev/null 2>&1; then
    pip-audit -r requirements.txt || rc=1
else
    echo "  pip-audit non installé → 'pip install pip-audit' (étape recommandée en CI)."
fi

echo; echo "== bandit (analyse statique de sécurité) =="
if command -v bandit >/dev/null 2>&1; then
    bandit -q -r core routers tools server.py -x tests || rc=1
else
    echo "  bandit non installé → 'pip install bandit' (optionnel)."
fi

echo; echo "== secrets potentiellement versionnés =="
if git rev-parse --git-dir >/dev/null 2>&1; then
    # On exclut les fichiers de test (fixtures = faux positifs) et les binaires.
    hits=$(git ls-files | grep -Evi '\.(png|jpg|jpeg|gif|ico|lock)$' | grep -Evi '(^|/)tests?/|test_|_test\.' | \
        xargs grep -nEI "(sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{30})" 2>/dev/null)
    if [ -n "$hits" ]; then echo "$hits"; echo "  ⚠️ secrets potentiels détectés !"; rc=1
    else echo "  OK : aucun secret littéral détecté dans les fichiers suivis."; fi
    if git ls-files --error-unmatch .env >/dev/null 2>&1; then echo "  ⚠️ .env est suivi par git !"; rc=1; fi
fi

echo; [ $rc -eq 0 ] && echo "✅ Scan terminé sans alerte bloquante." || echo "❌ Scan : des points à examiner ci-dessus."
exit $rc
