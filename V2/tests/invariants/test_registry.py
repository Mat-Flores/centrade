"""docs/invariants.md covers I1-I14 and S1-S14, with milestones and tests (SPEC §0.13, §14)."""

import re
from pathlib import Path

DOC = (Path(__file__).resolve().parents[2] / "docs" / "invariants.md").read_text(encoding="utf-8")

JALON_INVARIANTS = {
    **dict.fromkeys((1, 8, 14), "M1"),
    **dict.fromkeys((2, 3, 9, 10, 12), "M2"),
    **dict.fromkeys((4, 5, 6, 7), "M3"),
    13: "M4",
    11: "M7",
}
JALON_SCENARIOS = {
    **dict.fromkeys((9, 10), "M1"),
    **dict.fromkeys((1, 5, 7, 8), "M2"),
    **dict.fromkeys((2, 3, 4, 6, 11, 12), "M3"),
    13: "M4",
    14: "M7",
}


def _section(n: int) -> str:
    """Text of the `### In` section up to the next heading; empty if absent."""
    m = re.search(rf"^### I{n}\b.*?(?=^#{{2,3}} |\Z)", DOC, re.M | re.S)
    return m.group(0) if m else ""


def test_registry_covers_i1_to_i14() -> None:
    assert sorted(JALON_INVARIANTS) == list(range(1, 15))
    for n, jalon in JALON_INVARIANTS.items():
        section = _section(n)
        assert section, f"I{n} absent de docs/invariants.md"
        assert re.search(rf"Jalon\s*:\s*{jalon}\b", section), f"I{n} : jalon {jalon} manquant"
        assert re.search(rf"\btest_i{n:02d}_\w+", section), f"I{n} : aucun test_i{n:02d}_…"


def test_registry_covers_s1_to_s14() -> None:
    assert sorted(JALON_SCENARIOS) == list(range(1, 15))
    for n, jalon in JALON_SCENARIOS.items():
        row = re.search(rf"^\|\s*S{n}\s*\|\s*(M\d)\s*\|\s*`([^`]*)`", DOC, re.M)
        assert row, f"S{n} absent du tableau des scénarios, ou sans fichier prévu"
        assert row.group(1) == jalon, f"S{n} : jalon {row.group(1)} au lieu de {jalon}"
        assert row.group(2).startswith(f"tests/scenarios/test_s{n:02d}_"), f"S{n} : fichier prévu"
