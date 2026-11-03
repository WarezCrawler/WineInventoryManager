# WineInventoryManager

A small, self-contained wine stock and invoicing app: Python plus a single SQLite file, no server. It replaces a Microsoft Access application that has been in use for over ten years.

**Status:** design phase. The data migration mapping exists (`migrate/column_map.py`); the app itself is not built yet.

## Documentation

- [Design and implementation plan](docs/Vinlager_Python_SQLite_Design.md): scope of v1 (main menu, stock changes, invoice input), data model, business rules taken from the Access code, screens, build steps and backlog.

## Principles

- **Self-contained:** one program and one SQLite file the app creates itself on first start.
- **Logic in Python, data in the database:** the database holds tables and identity keys only.
- **Data model kept 1:1 with Access in v1**, with English column names (mapping in `migrate/column_map.py`).

## Data stays out of this repository

This repository is public. The business data (customers, invoices, bank details) and the database file are never committed: `.gitignore` excludes database files, `*.csv` and `*.accdb`, and the CI check fails if such a file is tracked. Tests use synthetic data only.

## Contributing

`main` is protected. All changes go through a pull request that is **squash-merged**, and the `test` check must pass.

```
python -m pip install pytest
python -m pytest
```
