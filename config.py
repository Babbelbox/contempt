"""
Configuratie voor de schaakengine-onderzoeksomgeving.
Pas ENGINE_PATHS aan naar de locaties van jouw engine-executables.
"""
from pathlib import Path

BASE_DIR = Path(__file__).parent

# =============================================================================
# CONTEMPT INSTELLING
# =============================================================================
# Contempt is in centipawns (honderdsten van een pion), NIET in procenten.
#
# Schaal:
#   0          = neutraal (engine speelt objectief)
#   24         = SF13-standaard (kwart pion bias, agressief genoeg voor de meeste gevallen)
#   50         = halve pion bias (duidelijk merkbaar speelstijlverschil)
#   100        = één pion bias (maximum, engine negeert remises bijna volledig)
#  -50         = engine accepteert remise eerder (handig als underdog)
#
# Positief → engine vermijdt remises, speelt voor winst ook in gelijke standen.
# Negatief → engine accepteert remise sneller.
#
# Alleen van toepassing op engines die Contempt ondersteunen: stockfish13, stockfish18c.
# =============================================================================

CONTEMPT = 24   # ← hier pas je de contempt aan (bereik: -100 tot 100)


# =============================================================================
# ENGINE-PADEN
# =============================================================================
ENGINE_PATHS = {
    "stockfish18c": BASE_DIR / "engines" / "stockfish18c.exe",  # SF 18 + Contempt patch (zelfgebouwd)
    "stockfish13":  BASE_DIR / "engines" / "stockfish13.exe",   # SF 13, originele Contempt
    "stockfish18":  BASE_DIR / "engines" / "stockfish18.exe",   # SF 18 origineel (geen Contempt)
    "stockfish":    BASE_DIR / "engines" / "stockfish.exe",     # SF 17 (geen Contempt)
    "berserk":      BASE_DIR / "engines" / "berserk.exe",
}

# =============================================================================
# STANDAARD UCI-OPTIES PER ENGINE
# =============================================================================
# Alleen opties die de engine daadwerkelijk ondersteunt worden toegepast.
# match.py controleert dit automatisch via engine.options.
ENGINE_OPTIONS = {
    "stockfish18c": {
        "Hash":     256,
        "Threads":  4,
        "Contempt": CONTEMPT,
    },
    "stockfish13": {
        "Hash":     256,
        "Threads":  4,
        "Contempt": CONTEMPT,
    },
    "stockfish18": {
        "Hash":    256,
        "Threads": 4,
    },
    "stockfish": {
        "Hash":    256,
        "Threads": 4,
    },
    "berserk": {
        "Hash":    128,
        "Threads": 4,
    },
}

# =============================================================================
# TIJDLIMIET PER ZET
# =============================================================================
# Kies één methode: nodes (reproduceerbaar) of time (reëler).
MOVE_LIMIT = {
    "nodes": 500_000,   # vaste aantal nodes per zet (reproduceerbaar)
    # "time": 1.0,      # seconden per zet (alternatief)
}

# =============================================================================
# PADEN
# =============================================================================
OPENINGS_FILE = BASE_DIR / "openings" / "eco_openings.epd"
GAMES_DIR     = Path(r"C:\Users\nickm\OneDrive\Bureaublad\Contempt\games")
RESULTS_DIR   = Path(r"C:\Users\nickm\OneDrive\Bureaublad\Contempt\results")
