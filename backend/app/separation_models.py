"""Catalogue of separation models offered to the user. Pure data: no torch import here."""

MODELS: dict[str, dict] = {
    "htdemucs": {
        "label": "HTDemucs — cepat",
        "description": "4 stem (bass, drums, vocals, other). Pilihan default yang paling ringan.",
        "demucs_name": "htdemucs",
        "stems": ["bass", "drums", "vocals", "other", "no_bass"],
        "relative_cost": 1.0,
    },
    "htdemucs_ft_bass": {
        "label": "HTDemucs-FT Bass — bass paling bersih",
        "description": "Hanya model spesialis bass dari HTDemucs-FT. Hasil: bass + backing track tanpa bass.",
        "demucs_name": "htdemucs_ft",
        "only_source": "bass",
        "stems": ["bass", "no_bass"],
        "relative_cost": 1.0,
    },
    "htdemucs_ft": {
        "label": "HTDemucs-FT — kualitas terbaik, lambat",
        "description": "4 model spesialis, kualitas tertinggi untuk semua stem. Sekitar 4x lebih lama.",
        "demucs_name": "htdemucs_ft",
        "stems": ["bass", "drums", "vocals", "other", "no_bass"],
        "relative_cost": 4.0,
    },
}

DEFAULT_MODEL = "htdemucs"

STEM_LABELS = {
    "bass": "Bass",
    "drums": "Drums",
    "vocals": "Vocal",
    "other": "Lainnya",
    "no_bass": "Backing track (tanpa bass)",
}

# Tiny untrained Demucs shipped inside the package: lets automated tests run the REAL
# worker pipeline without downloading weights. Never enabled in production.
import os as _os

if _os.environ.get("NBS_ENABLE_TEST_MODEL") == "1":
    MODELS["test_unittest"] = {
        "label": "TEST ONLY — demucs_unittest (untrained)", "description": "Automated tests only.",
        "demucs_name": "demucs_unittest", "stems": ["bass", "drums", "vocals", "other", "no_bass"], "relative_cost": 0.1,
    }
