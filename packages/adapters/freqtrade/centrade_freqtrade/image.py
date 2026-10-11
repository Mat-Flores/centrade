"""Image du moteur, épinglée par tag et par digest (ADR 0008). Jamais `stable` ni `latest`."""

FREQTRADE_IMAGE = "freqtradeorg/freqtrade"
FREQTRADE_TAG = "2026.9"
# Digest de l'index multi-architecture (amd64 et arm64), relevé le 2026-10-11.
FREQTRADE_DIGEST = "sha256:989aff5636d8f0213ed44fe334c3314a194a51c0c755d16866960247aafd2eae"
FREQTRADE_REF = f"{FREQTRADE_IMAGE}:{FREQTRADE_TAG}@{FREQTRADE_DIGEST}"

# Réservation par instance : valeurs prudentes, à mesurer au jalon M2 (lot I).
ENGINE_MEMORY_BYTES = 1024**3
ENGINE_NANO_CPUS = 500_000_000  # 0,5 CPU
