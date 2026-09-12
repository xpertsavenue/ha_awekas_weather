"""Constants for the AWEKAS Weather integration."""

DOMAIN = "awekas"

# CONF_LANGUAGE = "language"
DEFAULT_SCAN_INTERVAL = 30  # 5 Minuten Standard-Intervall in Sekunden

# Sprachen basierend auf der AWEKAS API Dokumentation
LANGUAGES = [
    {"value": "de", "label": "Deutsch (de)"},
    {"value": "en", "label": "English (en)"},
    {"value": "fr", "label": "Français (fr)"},
    {"value": "es", "label": "Español (es)"},
    {"value": "nl", "label": "Nederlands (nl)"},
    {"value": "it", "label": "Italiano (it)"},
    {"value": "pl", "label": "Polski (pl)"},
]
