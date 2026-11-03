"""App configuration in settings.json (next to the data folder), not in the database.
The database holds master data and transactions only.

Keys (English names of the Access tSettings entries):
  invoice_address, invoice_bank_details, invoice_payment_terms   text printed on invoices (defaults for new invoices)
  invoice_pdf_folder                                             folder where invoice PDFs are saved (machine-specific)
"""
import json
import os
from pathlib import Path

from winedb.config import app_dir

KEYS = ("invoice_address", "invoice_bank_details", "invoice_payment_terms", "invoice_pdf_folder")


def settings_path() -> Path:
    """settings.json: WINE_SETTINGS_PATH if set, otherwise next to the program (like the data folder)."""
    env = os.environ.get("WINE_SETTINGS_PATH")
    return Path(env) if env else app_dir() / "settings.json"


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
