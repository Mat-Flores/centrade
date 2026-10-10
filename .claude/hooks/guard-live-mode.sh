#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit) — le live ne s'active que par la procédure de promotion (SPEC §4 F1).
set -euo pipefail
input="$(cat)"
file="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path") or "")' <<<"$input")"
content="$(python3 -c '
import json, sys
t = json.load(sys.stdin).get("tool_input", {})
parts = [t.get("content"), t.get("new_string")] + [e.get("new_string") for e in t.get("edits", [])]
print("\n".join(p for p in parts if p))' <<<"$input")"

case "$file" in */docs/*|*/tests/*|*.md) exit 0 ;; esac

if grep -Eqi '"?dry_run"?[[:space:]]*[:=][[:space:]]*(false|0)|TRADING_MODE[[:space:]]*=[[:space:]]*live|LIVE_ENABLED[[:space:]]*=[[:space:]]*(true|1)' <<<"$content"; then
  echo "Bloqué : activation d'un mode live dans ${file}. Le live passe par la checklist de promotion, jamais par une édition de fichier." >&2
  exit 2
fi
exit 0
