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


def data_dir() -> Path:
    """The folder with all user data: the database, settings.json, the logo and, by default, the invoice PDFs.
    It is the folder of the database (so WINE_DB_PATH moves all of it). The build keeps it (build.ps1); a
    backup is a copy of this folder."""
    return db_path().parent
