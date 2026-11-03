# WineInventoryManager

A small, self-contained wine stock and invoicing app: Python plus a single SQLite file, no server. It replaces a Microsoft Access application that has been in use for over ten years.

**Status:** groundwork. The database first start is built (`winedb/db.py`: the app creates its own SQLite file and upgrades it with numbered migration scripts); the only screen so far is a table browser.

## Documentation

- [Design and implementation plan](docs/Vinlager_Python_SQLite_Design.md): scope of v1 (main menu, stock changes, invoice input), data model, business rules taken from the Access code, screens, build steps and backlog.

## Principles

- **Self-contained:** one program and one SQLite file the app creates itself on first start.
- **Logic in Python, data in the database:** the database holds tables and identity keys only.
- **Data model kept 1:1 with Access in v1**, with English column names (mapping in `migrate/column_map.py`).

## Data stays out of this repository

This repository is public. The business data (customers, invoices, bank details) and the database file are never committed: `.gitignore` excludes database files, `*.csv` and `*.accdb`, and the CI check fails if such a file is tracked. Tests use synthetic data only.

## Run

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m winedb
```

The first start creates the database (`data/wine_inventory.db`, or the path in `WINE_DB_PATH`). The app opens in your browser at http://127.0.0.1:8080 and lists the tables on the left; click a table to see its rows. Use `--no-browser` to skip opening the browser and `--port` to change the port. The "Import from Access database" button is a placeholder.

## Contributing

`main` is protected. All changes go through a pull request that is **squash-merged**, and the `test` check must pass.

```
python -m pip install pytest
python -m pytest
```
