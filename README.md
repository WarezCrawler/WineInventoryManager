# WineInventoryManager

A small, self-contained wine stock and invoicing app: Python plus a single SQLite file, no server. It replaces a Microsoft Access application that has been in use for over ten years.

**Status:** groundwork, with the data migration done. Built: the database first start with numbered migrations (`winedb/db.py`), settings in `settings.json`, a table browser, the one-time import from the Access file (button in the app, checked against the source: every cell, row counts and column totals), delivered as a Windows program (`build.ps1`). Not built yet: the main menu, stock changes and invoices; see [docs/Functionality.md](docs/Functionality.md).

## Documentation

- [Functionality list](docs/Functionality.md): the main functions, what is done and what is planned.
- [Design and implementation plan](docs/Vinlager_Python_SQLite_Design.md): scope of v1 (main menu, stock changes, invoice input), data model, business rules taken from the Access code, screens, build steps and backlog.

## Principles

- **Self-contained:** one program and one SQLite file the app creates itself on first start.
- **Logic in Python, data in the database:** the database holds tables and identity keys only.
- **Data model kept 1:1 with Access in v1**, with English table and column names (mapping in `migrate/column_map.py`).

## Data stays out of this repository

This repository is public. The business data (customers, invoices, bank details) and the database file are never committed: `.gitignore` excludes database files, `*.csv` and `*.accdb`, and the CI check fails if such a file is tracked. Tests use synthetic data only.

## The program

Build it once (Windows, needs Python 3.10+ installed):

```
.\build.ps1
```

This creates `dist\WineInventoryManager\WineInventoryManager.exe`. Double-click it: the program opens in its own window and lists the tables on the left; click a table to see its rows. Closing the window ends the program. The whole `dist\WineInventoryManager` folder is the program: copy or move it as a folder.

The **database is created on the first start** in a `data` folder next to the `.exe` (`data\wine_inventory.db`). App settings (the invoice texts and the PDF folder) are in `settings.json` next to the `data` folder, not in the database; a backup is the `data` folder plus that file. The database stays there when you replace the program with a newer build, and a newer program upgrades it automatically (with a backup copy first). Back it up by copying the file while the program is closed. The **"Import from Access database"** button reads an Access file (`.accdb`) directly (no Access or driver needed), checks the result with an independent audit, and only then fills the empty database. It works once, into an empty database. Use a copy of the Access file; it is only read. The same import as a command: `python -m migrate.load_csv <csv_dir> <new.db>` (for an export that is already CSV).

For development, run from source instead: `python -m pip install -r requirements.txt`, then `python -m winedb` (`--mode browser` opens it in the browser instead of a window, `--mode server --port 8080` only serves). `WINE_DB_PATH` points the database elsewhere.

## Contributing

`main` is protected. All changes go through a pull request that is **squash-merged**, and the `test` check must pass.

```
python -m pip install pytest
python -m pytest
```
