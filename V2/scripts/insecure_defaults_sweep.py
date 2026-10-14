"""Fallback for `insecure-defaults:audit` when the Workflow tool is missing from the session.

Reproduces the first step of the plugin's pipeline: one `grep -rE` per category, with the
plugin's own patterns. Concludes nothing: each line is a candidate, to be judged against the
plugin's `<category>.md` sheet ("Report when" / "Skip when" rules).

Usage: uv run python scripts/insecure_defaults_sweep.py [path ...]
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
        # Argument list, no shell: patterns and paths are not interpreted.
        hits = subprocess.run(  # noqa: S603
            [*cmd, "--", *scopes], capture_output=True, text=True, check=False
        )
        if hits.returncode > 1:  # 1 = no candidate; beyond that, grep failed
            print(hits.stderr, file=sys.stderr)
            return 2
        lines = hits.stdout.splitlines()
        print(f"## {category['title']} — {len(lines)} candidat(s), fiche {seed_file.stem}.md")
        for line in lines:
            print(f"  {line[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
