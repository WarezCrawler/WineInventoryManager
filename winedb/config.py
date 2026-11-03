import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Folder the data lives next to: the .exe's folder when packaged, the project folder otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def db_path() -> Path:
    """Database file: WINE_DB_PATH if set, otherwise data/wine_inventory.db next to the program."""
    env = os.environ.get("WINE_DB_PATH")
    if env:
        return Path(env)
    return app_dir() / "data" / "wine_inventory.db"
