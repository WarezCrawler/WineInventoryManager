# Vinlager – Python Rebuild Plan

This document records the decisions and the plan to replace the Access app with a Python app. Related documents:
- [Vinlager_DB_Design.md](Vinlager_DB_Design.md): what the Access app is.
- [Vinlager_Decompilation_Handoff.md](Vinlager_Decompilation_Handoff.md): extra findings, and what to export from Access.

> **Status:** this plan was written before the Access export and before the build started. The detailed design for v1 is now [Vinlager_Python_SQLite_Design.md](../Vinlager_Python_SQLite_Design.md). Where the two documents are different, the v1 design applies. The main differences:
> - v1 copies the Access tables 1:1. The Access import loads the data as it is, with no transform step (§5) and no clean-up. The clean-up comes after v1.
> - v1 has no foreign keys, because the Access data has orphan rows. `PRAGMA foreign_keys=ON` (§2) does not apply.
> - The settings are in `settings.json`, not in a `settings` table (§2).
> - The tables have English names (`items`, `customers`, `invoice_header`, `invoice_lines`, `stock_transactions`), not the names in §6.
> - The UI is NiceGUI.
> - The `Rabat` formula is known; see §5.1 of the v1 design.

## 1. Goals and limits

- The business is a **very small wine business**: one user at a time, and about 3,000 rows today.
- The app is **self-contained**, as the Access file is: one data file and one program, with no server and no installation.
- **The app moves away from Access completely.** The `.accdb` file is only a source for the one-time export and migration, and after that a read-only archive. The new app does not need an Access driver, ODBC or Office.
- **The database holds data only.** All application logic is in Python. So a new feature or a fix is a new program version, and nobody must copy or change the database.
- **Power BI** is used for analytics on top of the database (§7).
- The first version has the same functions as the Access app, and no new features.

## 2. Decisions

| Concern | Decision | Reason |
|---|---|---|
| Database | **SQLite**, one `.db` file | It fits the workload (small, transactional, one user), it is built into Python, and a backup is one file. DuckDB was rejected: it is made for analytics and is slow with many small writes. Use Postgres only if several users must work at the same time. |
| UI | A local web UI on localhost (Flask or FastAPI with HTMX, or NiceGUI), or PySide6 for a native look | Forms and lists are fast to build, and no hosting is needed. **Open: decide before the UI work starts.** |
| Invoice PDF | ReportLab | Pure Python, exact layout, and no system libraries. |
| Packaging | PyInstaller, delivered as a Windows `.exe` | The user double-clicks to start it, and the machine needs no Python. |
| Location of the data file | A folder that the user selects, separate from the program | Program updates never touch the data. |
| Settings | A `settings` table (as in Access), and a default PDF folder in the user's Documents folder | This replaces the hard-coded Dropbox path. |
| Backups | An automatic copy of the `.db` file, with the date in the name, when the app closes and before every migration | This replaces copying the file by hand. |
| Data access | Plain `sqlite3` and SQL files in the repo; no ORM at first | The smallest solution that works. |
| Integrity | `PRAGMA foreign_keys=ON` on every connection | SQLite does not enforce foreign keys by default. |

## 3. What goes where

**In the database (data rules only):** tables, primary and foreign keys, `NOT NULL`, `UNIQUE`, simple `CHECK` constraints, lookup tables and the reporting views (§6). No triggers and no stored logic.

**In Python:** the invoice totals and the `Rabat` and VAT arithmetic, copying, closing and reopening invoices, stock rules and warnings, PDF output, the mail list, the Excel export and the imports.

The prices on a sale line (sales price, cost price and VAT rate at the time of sale) are **history, not logic**, so the line keeps storing them. The totals (`SamletPris`, `SamletPris_mMoms`, `SamletCostPris`) have two options: Python calculates them and saves them when the line is written, so history stays fixed, or a view calculates them. **Open:** decide after the `Rabat` rules are confirmed.

## 4. Updates without copying the database

1. The data file is separate from the program, so an update replaces only the program.
2. The schema has a version number in `PRAGMA user_version`. The repo holds numbered migration scripts (`001_init.sql`, `002_….sql`).
3. At startup, the app compares the versions, makes a backup, and runs the new migrations in one transaction. If a migration fails, the transaction is rolled back and the data does not change.
4. At every start, the app deletes all reporting views and creates them again from SQL files in the repo. So a change to a view needs no change to the data.
5. An older program refuses to open a newer database, and shows a clear message.
6. An `app_info` table records the program version that last wrote to the file.

A change to the table structure is one new migration file. A change to the logic is only a new program version.

## 5. One-time migration tool (Access → SQLite)

The migration tool is a separate tool in the repo (`migrate/`). To run it: `python -m migrate source.accdb target.db`. **It is not part of the app,** and it is retired after go-live.

**Sources (both use the same steps):**
1. A direct read of the `.accdb` file with the pure-Python library `access-parser`. It already read all 9 data tables of the real file in this project. But it is a third-party library and works on a best-effort basis: it cannot read the system tables, and it showed æ, ø and å as `�`. Check its output before you trust it.
2. CSV files (UTF-8) from the Access export (see the handoff doc, B1 item 10), as a fallback and a cross-check.

**Steps:**
1. **Extract** each table into plain rows.
2. **Transform** the rows. All rules are in one place, as small tested functions that log their decisions:
   - Rename the columns to clean ASCII names (`Vin_Årgang` → `vintage`, `By` → `city`, `Delete` → `is_deleted`, `Id` → a name that tells what it is).
   - Make the case variants the same (`alm`/`Alm`, `rød`/`Rød`, `standard`/`Standard`).
   - Move the products that are not wine ("Vinkasse 6 hvid/rød", "Vinsmagning", "DK") into a product type column.
   - Make lookup tables for price type, wine type, size and country.
   - Apply the decisions on the known issues (table below).
   - Calculate the totals again with the new Python logic.
3. **Load** the rows into a new SQLite file made from the migration scripts, in the order of the dependencies, with foreign keys on. If a row breaks a rule, the run stops and names the row.
4. **Check** the result automatically, and write a report with:
   - the row count of each table, in the source and in the target;
   - 665 sale lines, 143 invoices and Σ `SamletPris` = 326,572.40;
   - the totals of each invoice and the on-hand stock of each wine, old against new;
   - every row that the transform changed, dropped or flagged.

**Properties:** the tool always writes a new target file and never changes the source (it works on a copy). It has a dry-run mode, and it can run again after any rule change.

**Known data issues to decide in the transform:**

| Issue | Count | Decision needed |
|---|---|---|
| Invoice with customer `0` (not in `tKunder`) | 1 (open draft, invoice 6) | Drop it, or link it to a placeholder customer |
| Invoices with no warehouse | 3 | Use a default warehouse, or keep the warehouse optional |
| Invoices with no date | 3 | Probably the open drafts |
| Open invoices | 14 | Migrate them as open, or discard them |
| Invoices with no lines | 8 | Keep them or drop them |
| Soft-deleted invoice | 1 | Drop it (the reports already hide it) |
| Negative `tVinlager.Quantity` (stock adjustments) | 341 of 863 | Make it a type of stock movement |
| Combinations of wine and warehouse with negative on-hand stock | 15 of 283 | Flag them in the report, and decide whether to correct them |
| Sale lines with a quantity of 0 or less | 13 | Returns? Keep them and flag them |
| Wines with no sales price / no cost price | 28 / 6 | Keep them, and flag them |
| Wines with more than one cost price row | 18 | Define which row is the current one |
| Duplicate customers / customers with no email | 2 / 2 | Examine them by hand |

## 6. Outline of the target schema (draft; confirm after the export)

**Tables** (clean names; English or Danish is **open**): `wine`, `customer`, `warehouse`, `invoice`, `invoice_line`, `stock_movement`, `cost_price`, `sale_price`, `setting`, `app_info`, and the lookup tables `price_type`, `wine_type`, `wine_size` and `country`.

**Meanings already known from the data:**
- On an `invoice_line`, the sales price **includes VAT** and the line total **does not include VAT**. The total with VAT = the total without VAT × (1 + VAT rate). This is true on all 665 lines.
- On-hand stock = Σ stock movements (including negative adjustments) − Σ invoice line quantities, for each wine and warehouse.
- The "hidden", "discontinued" and "private" flags on customers and wines become explicit flags, each with one clear meaning.

**Reporting views** (created again at each start; Power BI uses them):
- `fact_sales_line`: one row for each sale line, with quantity, revenue with and without VAT, cost, margin and discount.
- `fact_stock_movement`: receipts and adjustments.
- `stock_on_hand`: calculated.
- Dimensions: wine, customer, warehouse, invoice and date.

## 7. Power BI

- Power BI has no built-in connector for SQLite. Connect through the **SQLite ODBC driver (64-bit)** in Import mode, and refresh by hand in Power BI Desktop. This is sufficient for this size of data.
- Automatic refresh in the cloud needs an on-premises gateway with the same driver. If that is important, consider Postgres again: it has a built-in connector and DirectQuery.
- Power BI reads only the reporting views, never the tables, so the VAT and discount logic is defined in one place.
- When a database exists, the Power BI modelling tools can build the model.

## 8. Build order

1. Run the Access export on the work computer (handoff doc, Part B), and bring the output back.
2. Complete the schema and the migration scripts, and decide every **open** item above.
3. Build the migration tool and run it. Correct the transform rules until the check passes. This tests the schema before any UI exists.
4. Rebuild invoicing first, because it has the highest risk (`Rabat` and VAT arithmetic, PDF layout). Test it against historical invoices.
5. Build wines, customers, price lists, stock movements and settings.
6. Build the mail list, the Excel export, the reporting views and the Power BI model.
7. Package the app (PyInstaller), and add the backup when the app closes and the migration runner at startup. Then do a parallel run with a few real invoices in both systems, and retire the Access file.

## 9. Risks

- **How `Rabat` works is unknown.** The recovered data and the VAT checks do not show it, so it must come from the VBA or form code in Access. Until then, the margin and revenue figures can be wrong. If the export is not done, find the formula from the 665 historical lines and verify it; this has more risk.
- **The offline parser is a third-party library.** Cross-check its output against the CSV export.
- **The file contains personal and bank data** (customers, settings). Keep the `.accdb` file, the CSV files and the migrated `.db` file out of all public repos.
- **An older program version could open a newer database.** The version check prevents this (§4, item 5).
- **Some business meanings are not documented:** the price types `0P`, `EP` and `Rabat`, and the cost type `rå`. Ask the owner. (The "stock receipts with a future date" were explained later: the filter makes an empty grid for mass registration.)
