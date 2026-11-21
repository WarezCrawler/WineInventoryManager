# Vinlager – Python Rebuild Plan

Decisions and plan for replacing the Access app. Companion to:
- [Vinlager_DB_Design.md](Vinlager_DB_Design.md) – what the Access app is.
- [Vinlager_Decompilation_Handoff.md](Vinlager_Decompilation_Handoff.md) – extra findings and what to extract from Access.

Status: planning. Nothing is built yet. Items marked **open** depend on the Access export.

## 1. Goals and constraints

- A **very small wine business**: one user at a time, about 3,000 rows today.
- **Self-contained**, like the Access file: one data file plus one program, no server, no install.
- **Move away from Access completely.** The `.accdb` is only a one-time source for extraction and migration, afterwards a read-only archive. No Access driver, ODBC or Office dependency in the new app.
- **Database holds data only.** All application logic lives in Python, so features and fixes ship as a new program version without copying or touching the database.
- **Power BI** is used on top for analytics (§7).
- First version equals current functionality. No extra features.

## 2. Decisions

| Concern | Decision | Reason |
|---|---|---|
| Database | **SQLite**, single `.db` file | Fits the workload (small, transactional, single-user), built into Python, one-file backup. DuckDB rejected: built for analytics, poor at many small writes. Postgres only if several users need concurrent access. |
| UI | Local web UI (Flask or FastAPI + HTMX, or NiceGUI) on localhost, or PySide6 if a native look is wanted | Fast to build forms and lists, no hosting. **Open: choose before UI work starts.** |
| Invoice PDF | ReportLab | Pure Python, exact layout, no system libraries. |
| Packaging | PyInstaller, delivered as a Windows exe | Double-click to run, no Python needed on the user's machine. |
| Data file location | User-chosen folder, separate from the program | Program updates never touch the data. |
| Settings | `settings` table (as in Access) plus a default PDF folder under the user's Documents | Replaces the hard-coded Dropbox path. |
| Backups | Automatic dated copy of the `.db` on exit and before every migration | Replaces manual file copying. |
| Data access | Plain `sqlite3`, SQL files in the repo, no ORM at first | Smallest thing that works. |
| Integrity | `PRAGMA foreign_keys=ON` on every connection | SQLite does not enforce FKs by default. |

## 3. What lives where

**In the database (data rules only):** tables, primary and foreign keys, `NOT NULL`, `UNIQUE`, simple `CHECK`s, lookup tables, and the reporting views (§6). No triggers and no stored logic.

**In Python:** invoice totals and the `Rabat`/VAT maths, copy invoice, close and re-open, stock rules and warnings, PDF output, mail list, Excel export, imports.

Price snapshots on sale lines (sale price, cost price, VAT rate at time of sale) are **history, not logic**, and stay stored. Derived totals (`SamletPris`, `SamletPris_mMoms`, `SamletCostPris`) are either computed in Python and saved at write time so history stays fixed, or derived in a view. **Open:** decide after the `Rabat` rules are confirmed.

## 4. Patching without copying the database

1. The data file is separate from the program, so an update replaces only the program.
2. The schema has a version in `PRAGMA user_version`; the repo holds numbered migration scripts (`001_init.sql`, `002_….sql`).
3. On startup the app compares versions, takes an automatic backup, and runs pending migrations in a single transaction. A failure rolls back and leaves the data unchanged.
4. All reporting views are dropped and recreated on every start, from SQL files in the repo, so changing a view needs no data change.
5. An older program refuses to open a newer database, with a clear message.
6. An `app_info` table records the program version that last wrote to the file.

A structure change is one new migration file. A logic change is only a new program version.

## 5. One-time migration tool (Access → SQLite)

A separate tool in the repo (`migrate/`), run as `python -m migrate source.accdb target.db`. **Not part of the app.** Retired after go-live.

**Sources (same pipeline):**
1. Direct read of the `.accdb` with the pure-Python `access-parser` library. This already read all 9 data tables of the actual file in this project. It is third-party and best effort: it cannot read the system tables, and it showed æøå as `�` in output, so verify before trusting it.
2. CSV files (UTF-8) from the Access export (see the handoff doc, B1 item 10), as a fallback and cross-check.

**Steps:**
1. **Extract** each table into plain rows.
2. **Transform** with every rule in one place, as small, tested functions that log their decisions:
   - rename columns to clean ASCII names (`Vin_Årgang` → `vintage`, `By` → `city`, `Delete` → `is_deleted`, `Id` → proper names);
   - normalise case variants (`alm`/`Alm`, `rød`/`Rød`, `standard`/`Standard`);
   - move non-wine products ("Vinkasse 6 hvid/rød", "Vinsmagning", "DK") into a product-type column;
   - lookup tables for price type, wine type, size and country;
   - decide on known issues (below);
   - recompute totals with the new Python logic.
3. **Load** into a fresh SQLite file created from the migration scripts, in dependency order, with foreign keys on. A violating row stops the run and names the row.
4. **Reconcile** automatically, with a report:
   - row counts per table, source against target;
   - 665 sale lines, 143 invoices, Σ `SamletPris` = 326,572.40;
   - per-invoice totals and per-wine stock on hand, old against new;
   - every row the transform changed, dropped or flagged.

**Properties:** always writes a new target file; never modifies the source (work on a copy); has a dry-run mode; re-runnable after any rule change.

**Known data issues to decide in the transform:**

| Issue | Count | Decision needed |
|---|---|---|
| Invoice with customer `0` (not in `tKunder`) | 1 (open draft, invoice 6) | Drop, or map to a placeholder customer |
| Invoices with no warehouse | 3 | Default warehouse or leave optional |
| Invoices with no date | 3 | Probably the open drafts |
| Open invoices | 14 | Migrate as open, or discard |
| Invoices with no lines | 8 | Keep or drop |
| Soft-deleted invoice | 1 | Drop (it is already hidden in reports) |
| Negative `tVinlager.Quantity` (stock adjustments) | 341 of 863 | Model as a movement type |
| Wine/warehouse combos negative on hand | 15 of 283 | Flag in the report; decide whether to correct |
| Sale lines with qty ≤ 0 | 13 | Returns? Keep and flag |
| Wines without sale / cost price | 28 / 6 | Keep, flag |
| Wines with several cost-price rows | 18 | Define which one is current |
| Customer duplicates / no email | 2 / 2 | Review manually |

## 6. Target schema outline (draft, confirm after export)

Tables (clean names, English or Danish: **open**): `wine`, `customer`, `warehouse`, `invoice`, `invoice_line`, `stock_movement`, `cost_price`, `sale_price`, `setting`, `app_info`, plus lookups (`price_type`, `wine_type`, `wine_size`, `country`).

Key semantics already established from the data:
- `invoice_line` sale price is **VAT-inclusive**; line total is **ex-VAT**; the inclusive total = ex-VAT × (1 + VAT rate). This held on all 665 lines.
- Stock on hand = Σ stock movements (including negative adjustments) − Σ invoice-line quantity, per wine and warehouse.
- Customer and wine "hidden / discontinued / private" become explicit flags, with consistent meaning.

Reporting views (recreated on start; used by Power BI):
- `fact_sales_line` – one row per sale line: quantity, revenue ex/incl VAT, cost, margin, discount.
- `fact_stock_movement` – receipts and adjustments.
- `stock_on_hand` – derived.
- Dimensions: wine, customer, warehouse, invoice, date.

## 7. Power BI

- SQLite has no native Power BI connector. Connect via the **SQLite ODBC driver (64-bit)**, Import mode, manual refresh in Power BI Desktop. Fine at this size.
- Automatic cloud refresh would need an on-premises gateway with the same driver. If that matters, reconsider Postgres, which has a native connector and DirectQuery.
- Power BI reads only the reporting views, never the raw tables, so VAT and discount logic is defined once.
- The model can be authored with the Power BI modeling tools once a database exists.

## 8. Build order

1. Run the Access export on the work computer (handoff doc, part B) and bring the output back.
2. Finalise schema and migration scripts; fill in every **open** item above.
3. Build the migration tool and run it; fix transform rules until the reconciliation passes. This validates the schema before any UI exists.
4. Rebuild invoicing first (highest risk: `Rabat`/VAT maths and PDF layout), with tests against historical invoices.
5. Wines, customers, price lists, stock movements, settings.
6. Mail list, Excel export, reporting views, Power BI model.
7. Packaging (PyInstaller), backup on exit, startup migration runner, parallel run with a few real invoices in both systems, then retire the Access file.

## 9. Risks

- **`Rabat` handling is unknown.** It is not in the recovered data or the VAT-inclusive checks. It must come from the Access VBA/form code. Until then margin and revenue figures may be wrong. If the export is skipped, derive it from the 665 historical lines and verify, which is riskier.
- **The offline parser is third-party.** Cross-check against the CSV export.
- **Personal and bank data** is in the file (customers, `settings`). Keep the `.accdb`, CSVs and migrated `.db` out of any public repo.
- **An old program version opening a newer database** is blocked by the version check (§4, item 5).
- **Business meaning not documented:** price types `0P`, `EP`, `Rabat`, cost type `rå`, future-dated stock receipts. Ask the owner.
