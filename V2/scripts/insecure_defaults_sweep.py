"""Repli de `insecure-defaults:audit` quand l'outil Workflow manque dans la session.

Reproduit la première étape du pipeline du plugin : un `grep -rE` par catégorie, avec les
motifs du plugin lui-même. Ne conclut rien : chaque ligne est un candidat, à juger contre la
fiche `<catégorie>.md` du plugin (règles « Report when » / « Skip when »).

Usage : uv run python scripts/insecure_defaults_sweep.py [chemin ...]
"""

import json
import subprocess
import sys
from pathlib import Path

EXCLUDE = (".git", ".venv", "node_modules", "dist", "docs", "secrets", "tests", ".pnpm-store")


def main() -> int:
    caches = sorted(Path.home().glob(".claude/plugins/cache/trailofbits/insecure-defaults/*"))
    if not caches:
        print("plugin insecure-defaults introuvable : rien n'a été balayé", file=sys.stderr)
        return 2
    scopes = sys.argv[1:] or ["."]
    for seed_file in sorted((caches[-1] / "references").glob("*.json")):
        category = json.loads(seed_file.read_text(encoding="utf-8"))
        cmd = ["grep", "-rnIE", *(f"--exclude-dir={d}" for d in EXCLUDE)]
        for seed in category["seeds"]:
            cmd += ["-e", seed]
        # Liste d'arguments, sans shell : les motifs et les chemins ne sont pas interprétés.
        hits = subprocess.run(  # noqa: S603
            [*cmd, "--", *scopes], capture_output=True, text=True, check=False
        )
        if hits.returncode > 1:  # 1 = aucun candidat ; au-delà, grep a échoué
            print(hits.stderr, file=sys.stderr)
            return 2
        lines = hits.stdout.splitlines()
        print(f"## {category['title']} — {len(lines)} candidat(s), fiche {seed_file.stem}.md")
        for line in lines:
            print(f"  {line[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
