import os
from pathlib import Path


def db_path() -> Path:
    """Database file: WINE_DB_PATH if set, otherwise data/wine_inventory.db next to the program."""
    env = os.environ.get("WINE_DB_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "wine_inventory.db"
