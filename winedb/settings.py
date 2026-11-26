"""App configuration in settings.json, in the data folder, not in the database.
The database holds master data and transactions only.

All user data is in one folder, the data folder (config.data_dir()): the database, settings.json, the logo
and, by default, the invoice PDFs. The build keeps the whole folder (build.ps1), and a backup is a copy of it.

Keys:
  invoice_address, invoice_bank_details, invoice_payment_terms   text printed on invoices (English names of the
                                                                 Access tSettings entries)
  invoice_pdf_folder   folder where invoice PDFs are saved; empty = the folder "invoices" in the data folder
  logo_file            the company logo, a .png or .svg file; a name alone is looked up in the data folder
  header_colour        the background colour of the heading bar on every screen, as #RRGGBB or #RGB (for
                       example the background of the logo); empty = the standard blue. Read at start.
"""
import json
import os
import re
import shutil
from pathlib import Path

from winedb.config import app_dir, data_dir

KEYS = ("invoice_address", "invoice_bank_details", "invoice_payment_terms", "invoice_pdf_folder", "logo_file",
        "header_colour")
LOGO_TYPES = (".png", ".svg")


def settings_path() -> Path:
    """settings.json: WINE_SETTINGS_PATH if set, otherwise in the data folder."""
    env = os.environ.get("WINE_SETTINGS_PATH")
    return Path(env) if env else data_dir() / "settings.json"


def load_settings(path: Path | str | None = None) -> dict[str, str]:
    """All known keys; a missing file gives empty values. Unknown keys in the file are kept."""
    path = Path(path) if path is not None else settings_path()
    values = {k: "" for k in KEYS}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"{path} must contain a JSON object")
        values.update({k: ("" if v is None else str(v)) for k, v in data.items()})
    return values


def save_settings(values: dict[str, str], path: Path | str | None = None) -> None:
    """Write the file in one step (a crash cannot leave half a file)."""
    path = Path(path) if path is not None else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def has_values(path: Path | str | None = None) -> bool:
    path = Path(path) if path is not None else settings_path()
    return path.exists() and any(v for v in load_settings(path).values())


def logo_path(settings: dict) -> Path | None:
    """The logo file from the setting `logo_file`, or None if it is not set, does not exist or is not a .png
    or .svg file. A name without a folder is looked up in the data folder."""
    name = (settings.get("logo_file") or "").strip().strip('"')
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        path = data_dir() / path
    return path if path.suffix.lower() in LOGO_TYPES and path.is_file() else None


def header_colours(settings: dict) -> tuple[str, str] | None:
    """(background, text) of the heading bar from the setting `header_colour`, or None for the standard colours
    (not set, or not a colour in the form #RRGGBB or #RGB). The text is dark on a light background and white
    on a dark one, so it can always be read."""
    value = (settings.get("header_colour") or "").strip()
    if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", value):
        return None
    digits = value[1:] if len(value) == 7 else "".join(c * 2 for c in value[1:])
    red, green, blue = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    light = 0.299 * red + 0.587 * green + 0.114 * blue > 150          # perceived brightness, 0 to 255
    return f"#{digits.upper()}", ("#333333" if light else "#FFFFFF")


def move_old_files() -> list[str]:
    """Move the files that earlier versions kept next to the program into the data folder (once, at start):
    settings.json, and logo.png, which then becomes the setting `logo_file`. A file is moved only if the data
    folder does not have it yet, so nothing is overwritten. Returns what was moved."""
    moved = []
    old_settings, new_settings = app_dir() / "settings.json", settings_path()
    if old_settings.is_file() and not new_settings.exists() and not os.environ.get("WINE_SETTINGS_PATH"):
        new_settings.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(old_settings, new_settings)
        moved.append(f"{old_settings} -> {new_settings}")
    old_logo, new_logo = app_dir() / "logo.png", data_dir() / "logo.png"
    if old_logo.is_file() and not new_logo.exists():
        new_logo.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(old_logo, new_logo)
        moved.append(f"{old_logo} -> {new_logo}")
        values = load_settings()
        if not values["logo_file"]:
            save_settings({**values, "logo_file": "logo.png"})
    return moved
