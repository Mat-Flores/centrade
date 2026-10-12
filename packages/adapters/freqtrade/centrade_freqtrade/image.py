"""Image du moteur, épinglée par tag et par digest (ADR 0008). Jamais `stable` ni `latest`."""

FREQTRADE_IMAGE = "freqtradeorg/freqtrade"
FREQTRADE_TAG = "2026.9"
# Digest de l'index multi-architecture (amd64 et arm64), relevé le 2026-10-11.
FREQTRADE_DIGEST = "sha256:989aff5636d8f0213ed44fe334c3314a194a51c0c755d16866960247aafd2eae"
FREQTRADE_REF = f"{FREQTRADE_IMAGE}:{FREQTRADE_TAG}@{FREQTRADE_DIGEST}"

# Réservation par instance, d'après la mesure du 2026-10-11 (docs/capacite.md) : 276 Mio en régime
# établi, CPU moyen autour de 1 %. 768 Mio = 2,8 fois la mesure (plus de paires, plus de bougies).
# Changer ces valeurs change la ligne `engines` (réservation, admission), pas l'empreinte actuelle.
ENGINE_MEMORY_BYTES = 768 * 1024**2
ENGINE_NANO_CPUS = 500_000_000  # 0,5 CPU : plafond, pas une moyenne
