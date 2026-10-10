#!/usr/bin/env bash
# PreToolUse(Bash) — bloque les commandes à fort rayon d'impact (SPEC §17.5). Sortie 2 = blocage.
set -euo pipefail
cmd="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command") or "")')"
[ -z "$cmd" ] && exit 0

deny() { echo "Bloqué par le projet : $1" >&2; exit 2; }

grep -Eq '(^|[^a-z])rm +(-[a-zA-Z]*[rR]|--recursive)' <<<"$cmd" \
  && deny "suppression récursive. Supprimer des chemins précis, ou demander à l'opérateur."
grep -Eq 'git +push.*\b(main|master)\b|git +push.*(--force|--force-with-lease| -f( |$))' <<<"$cmd" \
  && deny "push sur la branche principale ou forcé. Utiliser une branche de jalon."
grep -Eq '(git +commit|git +push).*--no-verify' <<<"$cmd" \
  && deny "--no-verify contourne les hooks de qualité et gitleaks."
grep -Eq 'docker +(compose +down.*(-v|--volumes)|volume +(rm|prune)|system +prune)' <<<"$cmd" \
  && deny "destruction de volumes Docker (données Postgres/Timescale, secrets)."
grep -Eq '(curl|wget)[^|]*\|[[:space:]]*(sudo +)?(ba|z)?sh' <<<"$cmd" \
  && deny "exécution d'un script distant via pipe."
exit 0
