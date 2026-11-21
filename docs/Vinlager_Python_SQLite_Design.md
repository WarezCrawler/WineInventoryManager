# Vinlager – Python + SQLite: Design and Implementation Plan (v1)

This document describes how v1 of the new wine inventory app is built: the data model, the business rules taken from the Access app, the screens and the implementation steps. v1 replaces the Access app 1:1. Improvements to the data model come after v1 (§9).

The plan follows [access-analysis/Vinlager_Python_Rebuild_Plan.md](access-analysis/Vinlager_Python_Rebuild_Plan.md): a self-contained app, SQLite, all logic in Python, a one-time data import, and Access kept only as an archive. The database is **SQLite**, a single local file that the app creates itself. (An earlier draft of this document used MySQL by mistake.)

**Locations:**
- Project root: `A:\Development\WineInventoryManager` (this repo).
- Source: the decomposed Access app in `A:\Development\WineDB_py\WineDB_work`. It is read-only. All `export/...` and `scripts/...` paths in this document are relative to that folder.
- Source files used: `export/schema.txt`, `export/code/*.vba.txt`, `export/modules/*`, `export/queries_sql.txt`, `export/forms/*`, `export/csv/*`, `export/data_quality_report.txt` and `scripts/check_rabat.py`.

**Terms used in this document:**

| Term | Meaning |
|---|---|
| wine | One row in the `items` table. A few rows are products that are not wine; v1 keeps them as they are. |
| stock movement | One row in `stock_transactions`: a signed quantity that adds stock to a warehouse or removes it. |
| invoice line | One row in `invoice_lines`: a sale of one wine on one invoice. |
| on-hand stock | The quantity of a wine in a warehouse, calculated from stock movements and invoice lines (§5.3). |
| schema migration | A numbered `.sql` file in `winedb/migrations/` that creates or changes tables (§4.2). |
| Access import | The one-time load of the historical Access data into a new, empty database (§8 step 3). |

## 1. Scope

**In v1 (to build).** [Functionality.md](Functionality.md) shows which parts are built.
1. Main menu (replaces the Access form `fNavigation`).
2. Stock change screen (replaces `fVinlager_Change`).
3. Invoice screens: the invoice header (`fFaktura`) and the invoice lines (`fVinlager_Salg`), including closing an invoice.
4. Invoice preview on screen and invoice PDF (replaces the Access report `rFaktura`; moved into v1 by the owner, 2026-11-21).

**Not in v1:** the backlog in §9. v1 does not improve the data model: it copies the tables and columns 1:1.

## 2. Principles

- **Self-contained:** the app is one Python program and one SQLite file. It needs no server, and nothing must be installed except Python packages. The database file is **not in git**; the app creates it on first start (§4.2).
- **The database holds data and identity keys only.** It has the tables, primary keys with `AUTOINCREMENT`, indexes, `NOT NULL` and column defaults exactly as in Access. It has no foreign keys, triggers, views or procedures.
- **All logic is in Python:** price, VAT and discount calculation, on-hand stock, defaults, validation and workflow.
- **No foreign keys in v1, on purpose.** Access enforced none, and the data has orphan rows: 4 invoices point to customer 0 (invoice ids 6, 54, 59 and 108). Foreign keys would stop the 1:1 load.
- **Plain SQL, no ORM.** The app uses Python's built-in `sqlite3` with parameterised queries.
- **Language: British English** for the UI, the program code and the database structure (table, column and index names). The data is never translated: values such as `Rød`, `Alm`, `Tilbud`, `Frankrig` and the warehouse names stay exactly as they are in Access. Access object names (`fNavigation`, `tVinlager`) appear in this document only as references to the source.
- **The UI is separate from the logic.** The UI only calls functions in `stock.py` and `invoices.py`, so the UI toolkit can be replaced without changes to the logic.

## 3. Stack decisions

| Concern | Choice | Note |
|---|---|---|
| Database | SQLite (single file), standard-library `sqlite3` | No server and no driver to install. |
| Text comparison | `COLLATE NOCASE` on the text columns that are compared or searched | As in Access, `alm` equals `Alm`. SQLite folds case for ASCII letters only, so `ø` and `Ø` are different inside SQL. Searches that need them to match are done in Python (`casefold`). |
| UI | **NiceGUI** (pure Python, runs in the browser or in its own window) | The table browser already uses it. **Open:** the alternative is PySide6 (native window, more code). Decide before step 5; steps 1–4 do not depend on the UI. |
| Configuration | Environment variable `WINE_DB_PATH` (optional); default `data/wine_inventory.db` next to the program. App settings are in `settings.json` (decision 13 in §10); `WINE_SETTINGS_PATH` overrides its location. | No credentials and no `.env` file. |
| Tests | pytest | |

## 4. Data model (1:1 copy)

**Type mapping from Access to SQLite:**

| Access type | SQLite type | Note |
|---|---|---|
| AutoNumber | `INTEGER PRIMARY KEY AUTOINCREMENT` | Ids are never used again, and the Access import can insert the original ids. |
| Long, Integer | `INTEGER` | |
| Text, Memo | `TEXT` | The Access length limits are not enforced. |
| Yes/No | `INTEGER` 0/1 | |
| Date/Time | `TEXT` in ISO form `YYYY-MM-DD HH:MM:SS` | This is the exact format of the CSV export, and it sorts correctly. |
| Double, Single | `REAL` (8 bytes) | Exported values such as `120.7575` load unchanged. |

**Table and column names are in English:** snake_case, ASCII only, no reserved words. Tables have descriptive names such as `items`, `invoice_header` and `invoice_lines`. Only the names change. Data values (`Standard`, `Alm`, `Rød`, country names, settings keys such as `<fakt_adr>`) load as they are. §4.1 shows the full mapping with the Access names. The same mapping is in `migrate/column_map.py` (`TABLE_MAP` and `COLUMN_MAP`), which is the single source for the names. The table definitions are in `winedb/migrations/001_init.sql`, and a test checks that their tables and columns are equal to the mapping.

```sql
CREATE TABLE warehouses (
  warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT,
  warehouse_name TEXT, comment TEXT);

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_name TEXT NOT NULL COLLATE NOCASE, first_name TEXT, last_name TEXT,
  city TEXT, postal_code INTEGER DEFAULT 0, address TEXT, phone TEXT,
  is_hidden INTEGER DEFAULT 0, email TEXT, on_mailing_list INTEGER DEFAULT 0,
  comment TEXT);

CREATE TABLE items (
  item_id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_code TEXT NOT NULL COLLATE NOCASE, name TEXT NOT NULL COLLATE NOCASE, vintage INTEGER NOT NULL,
  country TEXT, producer TEXT, region TEXT,
  item_type TEXT COLLATE NOCASE, bottle_size TEXT COLLATE NOCASE, drink_by_year INTEGER, mature_year INTEGER,
  is_discontinued INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0, comment TEXT);
CREATE UNIQUE INDEX item_code ON items (item_code);

CREATE TABLE invoice_header (
  invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER DEFAULT 0, is_closed INTEGER DEFAULT 0, comment TEXT,
  warehouse_id INTEGER, invoice_date TEXT, hide_subtotals INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0);
CREATE INDEX invoice_header_warehouse_id ON invoice_header (warehouse_id);

CREATE TABLE stock_transactions (
  stock_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT, item_id INTEGER NOT NULL, quantity INTEGER DEFAULT 0, comment TEXT,
  warehouse_id INTEGER NOT NULL);
CREATE INDEX stock_transactions_warehouse_id ON stock_transactions (warehouse_id);

CREATE TABLE invoice_lines (
  sales_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL, created_at TEXT, quantity INTEGER DEFAULT 0, comment TEXT,
  invoice_id INTEGER NOT NULL, sales_price REAL DEFAULT 0, amount_ex_vat REAL DEFAULT 0,
  amount_incl_vat REAL DEFAULT 0, price_type TEXT COLLATE NOCASE, cost_price REAL DEFAULT 0,
  amount_cost REAL DEFAULT 0, vat_rate REAL DEFAULT 0, warehouse_id INTEGER NOT NULL,
  discount REAL NOT NULL DEFAULT 0);
CREATE INDEX invoice_lines_warehouse_id ON invoice_lines (warehouse_id);

CREATE TABLE prices_cost (
  cost_price_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, price_type TEXT COLLATE NOCASE,
  cost_price REAL, test_delete INTEGER);

CREATE TABLE prices_sales (
  sales_price_id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL, price_type TEXT COLLATE NOCASE,
  sales_price REAL, vat_rate REAL NOT NULL DEFAULT 0.25);
```

These statements are the content of the first schema migration, `001_init.sql` (§4.2).

### 4.1 Column mapping (Access → SQLite)

The machine-readable version is `migrate/column_map.py` (`COLUMN_MAP[table][old_name] = new_name`). It was checked against the CSV headers and `schema.txt`: it covers every column, and no column is missing. The CSV columns are in the same order as the mapping, so the Access import can rename each column by its header.

| Table (Access → new) | Access column | New column | Meaning |
|---|---|---|---|
| tLagre → `warehouses` | Lager_ID / LagerNavn / Kommentar | warehouse_id / warehouse_name / comment | warehouse |
| tKunder → `customers` | Kunde_ID | customer_id | |
| | Kundenavn / Fornavn / Efternavn | customer_name / first_name / last_name | |
| | By / Post_nr / Adresse / Tlf | city / postal_code / address / phone | |
| | Skjul | is_hidden | not shown in customer pickers |
| | Mailadr / Maillist | email / on_mailing_list | |
| | Kommentar | comment | |
| tVinliste → `items` | Vin_ID / Vin_UID | item_id / item_code | unique short code |
| | Vin_Navn / Vin_Årgang | name / vintage | |
| | Vin_Land / Vin_Hus / Vin_Område | country / producer / region | `Hus` = wine house |
| | Vin_Type / Vin_Str | item_type / bottle_size | |
| | Vin_Udløb / Vin_Moden | drink_by_year / mature_year | |
| | Udgået / Private | is_discontinued / is_private | |
| | Vin_Kommentar | comment | |
| tFaktura → `invoice_header` | Fakt_ID / Kunde_ID / Lager_ID | invoice_id / customer_id / warehouse_id | |
| | Lukket | is_closed | |
| | FakturaDato / Kommentar | invoice_date / comment | |
| | HideSubTotals / Delete | hide_subtotals / is_deleted | `Delete` is a soft delete |
| tVinlager → `stock_transactions` | VinLager_ID | stock_line_id | |
| | Date_Create / Vin_ID / Lager_ID | created_at / item_id / warehouse_id | |
| | Quantity / Kommentar | quantity / comment | quantity is signed |
| tVinlager_Salg → `invoice_lines` | Vin_SalgID / Fakt_ID | sales_line_id / invoice_id | |
| | Vin_ID / Lager_ID / Date_Create | item_id / warehouse_id / created_at | |
| | Quantity / Kommentar | quantity / comment | |
| | SalgsPris | sales_price | unit price, VAT included |
| | SamletPris | amount_ex_vat | |
| | SamletPris_mMoms | amount_incl_vat | |
| | CostPris / SamletCostPris | cost_price / amount_cost | |
| | Momssats / PrisType | vat_rate / price_type | |
| | Rabat | discount | amount off the line, VAT included |
| tPrisliste_Cost → `prices_cost` | Id / Vin_ID | cost_price_id / item_id | |
| | PrisType / CostPris | price_type / cost_price | |
| | test_slet | test_delete | not used, kept 1:1 |
| tPrisliste_Salg → `prices_sales` | Id / Vin_ID | sales_price_id / item_id | |
| | PrisType / SalgsPris / Momssats | price_type / sales_price / vat_rate | |
| tSettings → `settings.json` (not a table, see decision 13 in §10) | Setting | invoice_address / invoice_bank_details / invoice_payment_terms / invoice_pdf_folder | from `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>`, `<fakt_savelocation>`. The Danish `Description` column is documentation and is not copied. |

**Notes:**
- Two names need care: `stock_transactions` (Access `tVinlager`) holds the stock movements (`stock_line_id`), and `invoice_lines` (Access `tVinlager_Salg`) holds the invoice lines (`sales_line_id`).
- `USysApplicationLog` is **not** imported. It holds 3 rows from an Access data macro that failed in 2013, and it is an Access system table.
- In Access, `created_at` has the default `Now()`. In the new app, Python sets it on every insert, because all logic stays in Python.
- `prices_cost.test_delete` is empty in all rows. It is kept only for the 1:1 copy.
- The Access setting `Required` becomes `NOT NULL`. The Access setting `Allow zero length` (empty text) has no SQLite equivalent and is not enforced.

### 4.2 First start: the app creates its own database

**Location:** the path in `WINE_DB_PATH`, or by default `data/wine_inventory.db` next to the program. The `data/` folder and all `*.db` and `*.sqlite*` files are in `.gitignore`.

**On every start,** `winedb.db.connect()` does these steps:
1. If the file does not exist, it creates the folder and the file. Then it applies every schema migration in `winedb/migrations/` in order (`001_init.sql` is §4). So the first start from a fresh clone gives an empty app that works.
2. If the file exists, it reads `PRAGMA user_version` and applies only the newer schema migrations, each in its own transaction. Before it upgrades a database that has rows, it copies the file to `<name>.bak-<timestamp>`.
3. If `user_version` is higher than the newest schema migration the program knows, the program is older than the database. It stops with a clear message and changes nothing.

After each schema migration, `connect()` sets `user_version` to the number of that migration. A schema change is one new numbered `.sql` file; a change to the logic needs no schema migration. This is also how the database gets patched, so nobody ever copies it by hand.

The empty database has no wines, customers or warehouses. The Access import (§8 step 3) loads the historical data into a new file, which it creates through the same `connect()`. It refuses to load into a database that already has rows.

**Connection settings:** the `sqlite3.Row` row factory. There are no foreign keys, so none are enforced. Only **one program instance at a time** may open the file, and the file must be on a local disk, not in a shared or synced folder.

## 5. Business logic from the Access code

All business logic is in Python; the database has none. Every rule below comes from the VBA code or the Access queries. None of it is guessed.

### 5.1 Line amounts (`fVinlager_Salg.CalcFullPrice`)
```
amount_incl_vat = round(sales_price * quantity - discount, 2)     # VAT included
amount_ex_vat   = round(amount_incl_vat / (1 + vat_rate), 2)     # VAT excluded
amount_cost     = round(cost_price * quantity, 2)
```
`sales_price` is the unit price with VAT included. `discount` is an amount off the whole line, also with VAT included. A NULL value counts as 0, as with the VBA function `Nz`. **Verified: these formulas give the stored values for all 665 historical invoice lines, with 0 mismatches** (`scripts/check_rabat.py`).

### 5.2 Prices on an invoice line
- **Default cost price** (`GetCostPrisStandard`): the `cost_price` of the first `prices_cost` row for the wine with `price_type = 'Standard'`. "First" means the lowest `cost_price_id`. If there is no such row, the default is `0`. The user can also pick another cost row for the wine, or type a value.
- **Sales price:** the user picks one of the wine's `prices_sales` rows. This copies `sales_price`, `vat_rate` and `price_type` onto the invoice line. If the user types a price instead, the app sets `price_type = ''` (no price list row is selected) and keeps `vat_rate`.
- The invoice line stores a **copy** of the price, the VAT rate and the cost. Later changes to the price lists never change existing invoice lines.

### 5.3 On-hand stock (`TotalVinQ`, view `uVinlager`)
`on_hand(item_id, warehouse_id) = SUM(stock_transactions.quantity) − SUM(invoice_lines.quantity)`, over all rows for that wine and warehouse.

A stock movement with a negative quantity removes or corrects stock; 341 of the 863 stock movements are negative. Python calculates on-hand stock with two `SUM` queries, in `stock.on_hand()`, which is the only place that knows the formula.

**Difference from Access:** the calculation leaves out the invoice lines of soft-deleted invoices (`is_deleted = 1`), because calculations must leave out flagged invoices. Access counted them (`TotalVinQ` sums `uVinlager`, which does not filter on `Delete`). In the January 2015 export, the one soft-deleted invoice (149) has no lines, so the results are the same. Lines whose invoice row does not exist still count, as in Access. Access never stopped a sale or removal that made stock negative, so v1 does not either.

### 5.4 Invoice rules
- **Open invoice:** an invoice with `is_closed = 0`. Invoice lines can be added or changed only on open invoices. (The Access line form uses the query `qVinlager_Salg`, which filters on `is_closed <> True`.) To close an invoice, the app sets `invoice_header.is_closed = 1`. Reopening a closed invoice is a separate screen in the backlog (§9).
- **Defaults for a new invoice line:**
  - `invoice_id`: the selected invoice.
  - `warehouse_id`: the invoice's `warehouse_id` (`GetDefaultLagerID`). This column is `NOT NULL` on invoice lines, so if the invoice has no warehouse, the user must pick one. 3 invoices have no warehouse.
  - `created_at`: now.
  - `quantity` and `discount`: 0.
- **Invoice header fields:**
  - `customer_id`, set with a customer picker. The picker lists customers with `is_hidden = 0` in name order, and has a "contains" search on the name.
  - The default warehouse (`warehouse_id`), `invoice_date`, `comment`, `hide_subtotals`, `is_closed` and `is_deleted`.
  - The customer's address, postal code, city and phone are shown read-only.
- **Delete flag (`is_deleted`):** this is a soft delete; no row is removed. When the user sets the flag, the app shows the Access warning *"Be aware that this invoice will be suppressed, and must have zero quantity and amounts"* (the original text is kept). The exports (`uVinlager_Excel`) leave out flagged invoices.
- **Invoice number:** the invoice number is the `invoice_id` (auto-increment). Python reads the new id from the insert (`lastrowid`), which is always exact. The Access code used `DMax`, which could return the invoice number of another user.

### 5.5 Stock change rules (`fVinlager_Change`)
A stock change inserts one stock movement into `stock_transactions` with these fields: `item_id`, `warehouse_id`, `quantity` (signed: a positive value adds stock, a negative value removes it), `comment` and `created_at` (default now).

For the selected wine and warehouse, the screen shows the wine's name, vintage, producer, country, bottle size, type and the on-hand stock (`TotalVinQ`). The screen cannot delete existing stock movements; Access also did not allow it.

## 6. Screens

### 6.1 Main menu (from `fNavigation`)
The title is "Wine Inventory Manager". On the left is the list of **open invoices** (`is_closed <> 1`), newest first, with the invoice number, customer number and customer name. All text in the app is British English, so the buttons have English captions; the table shows the Access caption for reference:

| Button | Access caption | In v1 |
|---|---|---|
| Open invoice (opens the invoice lines of the selected invoice) | Åben Faktura | **yes** |
| Invoice details (opens the header of the selected invoice; if no invoice is selected, a new one) | Åben faktura egenskaber | **yes** |
| Stock change (new entry) | Open Vinlager tilgange/afgange | **yes** |
| Mass stock registration (§6.2.1) | Import vinlager tilgange/afgange | **yes** |
| Generate invoice (preview and PDF, step 9) | Generer Faktura | **yes** (shown disabled until step 9) |
| Maintain customers, Customer list, Reopen closed invoice, Wine list, Sales price list, Cost price list, Warehouses, Stock report, Advanced settings, Export mailing list | Vedligehold Kundedata, List Kunder, Gen­åben lukkede faktura, Vinliste, Prisliste Salg, Prisliste Cost, Open Lager Stamdata, Vis lagerrapport, Show advanced settings, Mail Liste Export | shown disabled (backlog) |
| Quit | Quit | yes |

In Access, the open-invoice list uses an **inner join to the customers**, so the 4 draft invoices with customer `0` do not show. The new app uses a **left join** (the default of decision 2 in §10) and shows "(no customer)", so the user can finish or delete these drafts.

Two more details of the list:
- A soft-deleted invoice that is not closed stays in the list, marked in the column "Deleted", so that the user can find it and remove the flag.
- The logo is not in the public repo. The app shows `logo.png` in the header only if that file is next to the program.

### 6.2 Stock change screen
The user fills in the fields in this order:
1. Wine: search by the start of the `item_code` (as on the invoice lines screen) or by name. The list shows the name, vintage, type and bottle size.
2. Warehouse.
3. Signed quantity.
4. Comment.
5. Date (default now).

These are the fields of the Access form; version 1 adds none (decision 14 in §10). The wine picker starts each row with the wine code (`item_code`, Access `Vin_UID`), for example "Code SAbSe_RA09 – Seleccion Personal 2009 (Rød, Alm)". It lists the wines that Access listed, with one difference (owner decision, 2026-11-21): a discontinued wine whose stock over all warehouses is 0 is hidden. A discontinued wine with stock (also negative stock) stays, marked "(discontinued)", after the active wines, so that its stock can still be corrected. The rule is `stock.wines_for_stock_change()`. Mass registration (§6.2.1) accepts every wine.

Then the user clicks **Save** or **Cancel**. While the user types, the screen shows the on-hand stock now and after the change. Below the fields, it shows the 20 latest stock movements for the selected wine and warehouse.

#### 6.2.1 Mass stock registration

In Access, the button "Import vinlager tilgange/afgange" opened the query `qVinlager_Change_Import` as an editable grid: `SELECT Lager_ID, Vin_ID, Quantity, Kommentar FROM tVinlager WHERE Date_Create > Now()`. The filter makes the grid open empty (no row has a future date), and the user pastes many stock changes at once, usually from Excel. Each new row gets the date from the table default `Now()`. So it is a mass registration, not a file import.

The new screen does the same, with the same table and fields. It is an editable **grid**, as the Access datasheet was:
1. **Columns:** line, warehouse, wine, quantity, comment, and a read-only check column that shows the result of each row after a check: "OK" or its problems. The warehouse and wine cells hold the id or code, and show the name next to it ("1 – Vinotrentino", "SAbSe_RA09 – Seleccion Personal 2009").
   **Lists in the cells:** double-click, Enter or F2 on a warehouse or wine cell opens a dropdown list; typing a character opens the normal text editor instead, so a code or id can still be typed. The wine list is the list of the stock change screen (discontinued wines without stock are hidden). AG Grid's searchable list is an Enterprise feature, so the free list is used: it is sorted by code, without a search box.
2. **Paste from Excel:** the user selects a cell and pastes (Ctrl+V). The copied cells fill the grid from that cell down and to the right, and the grid grows when it needs more rows. A heading row is skipped when the paste starts in the warehouse column. Cells after the comment column are left out, and the screen says how many. The user can also type in the cells. As in an Access datasheet, the last row is always a new, empty row: the grid starts with only that row, grows by exactly the rows that are pasted, and gets the next new row as soon as the user types into the new row. Empty rows are ignored.
   AG Grid's own paste of many cells is an Enterprise feature, so the page catches the paste in the browser: text with a tab or a line break goes to the server with the row and column of the selected cell (`stock_mass.PASTE_JS`).
3. **Wine:** the wine id (as in Access) or the wine code. A whole number that is a wine id gives that wine. Other text is looked up as a code, with upper and lower case the same. A number that is the id of one wine and the code of another wine is refused as ambiguous.
4. **Check** fills in the result columns of every row.
5. **Save all** is possible only after a check without problems, and only while no cell has changed since. It saves **all rows or none**, in one transaction. All rows get the same date: now. After the save, the grid is empty again.

The data functions are `mass_entry.paste_into()`, `mass_entry.check_rows()` and `stock.add_movements()`.

### 6.3 Invoice header screen
The fields are those in §5.4. The buttons are Save, Close invoice (sets `is_closed`) and Open lines. A new invoice must have a customer; the screen does not offer the Access default of customer `0`.

### 6.4 Invoice lines screen
- **Top:** invoice number, customer, date and the `is_closed` toggle ("Close invoice?"; Access: "Luk faktura?").
- **Grid:** the invoice lines of the invoice, with wine, quantity, unit price, discount, price type, VAT rate, and the totals with and without VAT.
- **Entry panel:** wine search (type the start of the `item_code`, then pick), `quantity`, sales price picker and manual price, `discount`, VAT rate, cost price picker, `comment`, warehouse, and the on-hand stock in that warehouse. All three line amounts update while the user types, with the formulas in §5.1.
- **Buttons:** Save, Undo, Delete line, New line.
- **Below the grid:** the invoice totals without VAT and with VAT.

## 7. Code layout

```
WineInventoryManager/   # project root
  docs/                # this document
  data/                # SQLite file, created on first start, git-ignored
  winedb/
    config.py        # database path (WINE_DB_PATH or default)
    db.py            # connect() = create-if-missing + schema migrations (§4.2). A transaction() helper comes
                     #   with the first write function (step 4 or later); it is not built yet
    settings.py      # settings.json (decision 13)
    migrations/      # 001_init.sql (§4), then 002_..., numbered
    logic.py         # pure functions without database access: line_amounts(), default_cost()
    stock.py         # on_hand(), add_movement(), recent_movements()
    invoices.py      # open_invoices(), get/save_header(), lines(), save_line(), close()
    browse.py        # read-only table content for the table browser (no UI imports)
    ui/              # the whole front-end, and the only place that imports NiceGUI/pywebview:
                     #   app.py (table browser, import dialog), later menu, stock_change, invoice_header,
                     #   invoice_lines and labels.py (user-friendly column names). tests/test_architecture.py
                     #   fails if any other code imports the UI libraries or if the back-end imports winedb.ui
  migrate/
    column_map.py    # Access -> English table and column names (§4.1)
    load_csv.py      # Access import: CSV -> SQLite; verify.py then compares the result with the source
  tests/
```

## 8. Implementation steps

Do the steps in order. Each step has a check; the step is complete when the check passes.

1. **Skeleton.** **Done.** Repo, venv, `pytest`, NiceGUI, and `config.py` with the database path.
   *Check:* `pytest` runs, and no database exists yet.
2. **Schema and first start (§4.2).** **Done.** `001_init.sql` from §4, and `db.connect()`, which creates a missing database and handles `user_version`.
   *Check:* after you delete `data/` and start the app, the file exists with all 8 tables and `user_version = 1`. A second start changes nothing. A database with `user_version = 99` is refused. The column names are equal to `COLUMN_MAP`, and the types and nullability match `schema.txt`.
3. **Access import and check against the source (`migrate/load_csv.py`, `migrate/verify.py`).** **Done.** The import reads the 9 CSV files (UTF-8 with BOM) from `export/csv/`. The "Import from Access database" button in the app reads the `.accdb` file directly instead, and gets the same data. The import does these steps:
   - It renames each header with `COLUMN_MAP` (§4.1). It fails if a CSV file has a column that the map does not know, or if the map has a column that the CSV file does not have.
   - It converts the booleans `True`/`False` to 1/0.
   - It stores an empty cell as `NULL`. The CSV format cannot show the difference between an empty text and NULL, so text fields lose that difference.
   - It inserts the rows with their original ids, so all keys stay the same. `AUTOINCREMENT` continues after the highest id (SQLite keeps it in `sqlite_sequence`; a test insert checks it).
   - It creates the target database through `connect()` and refuses a target that has rows. To run the import again, delete the target file first.

   *Check:* the row counts are 143 / 176 / 3 / 240 / 442 / 4 / 863 / 665 / 228. The sum of `amount_ex_vat` is 326,572.40. The highest `invoice_id` is 150. There are 129 closed and 14 open invoices, and 341 stock movements with a negative quantity.
4. **Logic and golden test.** **Done.** `logic.line_amounts()` (§5.1) and `stock.on_hand()` (§5.3). The golden tests are in `tests/test_golden.py`; they run only when `WINE_CSV_DIR` points to the CSV export.
   *Check:* pytest calculates all 665 invoice lines again from the database and gets the stored totals, with 0 mismatches. The on-hand stock for all 283 combinations of wine and warehouse matches the calculation from the CSV files. 15 of them are negative, as in the data quality report.
5. **UI shell and main menu.** **Done.** The main menu is `winedb/ui/menu.py`, and the table browser moved to `/tables`. The buttons for steps 6–8 show a message until those screens exist. The NiceGUI app, the main menu with the list of open invoices and the buttons (§6.1), and the disabled backlog buttons.
   *Check:* the list shows the 14 open invoices (10 if the inner join is kept).
6. **Stock change screen** (§6.2).
   *Check:* a stock change of +6 and then one of −2 change the on-hand stock by +4. They write two rows to `stock_transactions` with the correct `created_at`.
7. **Invoice header screen** (§5.4, §6.3).
   *Check:* create an invoice, change it, set the delete flag and close it. The row in `invoice_header` is the same as Access would store it.
8. **Invoice lines screen** (§5.2, §6.4).
   *Check:* enter three historical invoices again: one with a `discount`, one with 0% VAT and one with a negative quantity. The new invoice lines have the same values as the stored ones. Closed invoices are read-only.
9. **Invoice preview and PDF** (decision 12 in §10, replaces `rFaktura`). The preview on screen and the PDF use the line and total calculation of §5.1. The PDF is made directly with ReportLab and saved to the PDF folder from `settings.json`. The texts (address, bank details, payment terms) come from `settings.json` when the PDF is made; the saved PDF keeps them.
   *Check:* for each reference invoice in `export/reference_invoices/`, the new PDF shows the same lines, totals and texts.
10. **End-to-end test and parallel run.** Use a copy of the database after the Access import. Enter the same new invoice and the same stock change in Access and in the new app, then compare the stored rows.

The numbers in the checks come from an old copy of the Access data (see "Old copy of the data" under Risks in §10).

## 9. Backlog (not in v1)

These functions of the Access app come after v1, in about this order of priority. The invoice PDF moved into v1 (step 9). Specification: `export/report_spec/rFaktura.spec.json`; reference PDFs: `export/reference_invoices/`.

1. **Reopen a closed invoice** (`fFaktura_genåben`).
2. **Copy an invoice** (`DBCopyFakt`). It copies the header with a new customer, today's date, and `is_closed`, `warehouse_id` and `hide_subtotals`. It copies the invoice lines with today's date.
3. **Customer maintenance** and **mail list export.** The export selects customers with `on_mailing_list = 1 AND is_hidden = 0 AND email <> ''`; 128 customers match.
4. **Wine list maintenance**, with the value lists for type (`Rød;Hvid;Rose;Desert;Mousserende`) and bottle size (`Alm;Halv;Magnum;Db. Mgm;50 cl.`). Note that the data uses `MGM` and `DMGM`.
5. **Price lists** for sales and cost.
6. **Warehouse** master data.
7. **Settings screen** for `settings.json`, including the PDF folder.
8. **Stock report** (`qVinliste`) and **customer list** (`rKundeListe`).
9. **Excel export** (`uVinlager_Excel`).
10. **Consistency check query.**

(The stock import, `qVinlager_Change_Import`, moved into version 1 as the mass stock registration, §6.2.1.)

### 9.1 Key strategy: identity keys now, business keys later

- **v1:** every relation uses the identity key (surrogate key), 1:1 with Access: `item_id`, `customer_id`, `warehouse_id`, `invoice_id` and the other id columns.
- **Direction:** each dimension will get a **business key that the users give and name themselves**, and relations will point to that key instead of the identity key. The dimensions are wine, customer and warehouse, and the free-text lookups such as `price_type`, `item_type` and `bottle_size`.
- **Example in the existing system:** `item_code` (`Vin_UID`) is such a business key. It was added later, it is unique, users type it to find a wine, and it has worked for more than 10 years. But the tables still relate through `item_id`, not through the code, and v1 keeps it that way. `price_type` is in practice a business key too (free text, used in comparisons), but it is not a real dimension.
- **Rules for v1 that keep the later change small:**
  1. Keep `item_code` unique (a `UNIQUE INDEX` enforces it) and show it next to the name in wine pickers and lists.
  2. Find a wine from a typed code in **one** function (`find_item_by_code`). Never hard-code identity values, and never assume that ids are consecutive or have a meaning.
  3. Keep each relation lookup (the joins on `item_id`, `customer_id` and `warehouse_id`) in the data functions in `stock.py` and `invoices.py`, not in the UI.
- **How to make the change later:** write one numbered schema migration per dimension (§4.2), with these steps:
  1. Add the business key column.
  2. Fill it, and check that it is unique and never empty.
  3. Add the unique index.
  4. Add the new key column to the child tables, and fill it with a join on the old id.
  5. Rebuild the tables without the old column.

  The golden tests (§8 step 4) must give the same results before and after the change.
- **Open (not for v1):** which dimensions get a business key, and what the key looks like (customer number? warehouse code?). Whether the business key becomes the primary key or stays a unique alternate key. What to do when users want to rename a code after history exists, because the history must still point to the same wine.

**After v1 is stable:** clean up the data model (foreign keys, lookup tables, one spelling for `alm`/`Alm`, products that are not wine but are stored as wines, stored totals), and add logins and a backup routine. Package the app as a single Windows `.exe` with PyInstaller; the database stays outside the `.exe` in the `data` folder.

## 10. Open decisions and risks

| # | Item | Default if not decided |
|---|---|---|
| 1 | UI toolkit: NiceGUI or PySide6 | NiceGUI (used from step 5) |
| 2 | Open-invoice list: inner join (as in Access) or left join (also shows the 4 drafts with customer 0) | Left join (used from step 5) |
| 3 | `invoice_date`: the Access form has no default. Fill in today's date, or leave it blank as in Access? | Fill in today, the user can change it |
| 4 | A wine can have more than one `Standard` cost row (not checked in the data) | Use the lowest `cost_price_id` and log a warning |
| 5 | Warn when a sale or removal makes the stock negative? Access never warned, and 15 combinations of wine and warehouse are already negative. | No warning in v1 |
| 6 | NULL or empty string for empty text fields on load | NULL |
| 7 | Access `Single` columns are stored as 8-byte `REAL` | `REAL` |
| 8 | Invoice date and `is_closed` when an invoice is closed (Access has no extra step) | Same as Access |
| 9 | Access stores "no value" in lookup columns in two ways: as `0` (`invoice_header.customer_id` in 4 rows, `invoice_lines.warehouse_id` in 2 rows of the snapshot) and as NULL (`invoice_header.warehouse_id` in 3 rows). The Access import keeps both as they are. Should one explicit step after the import change 0 to NULL, and report each change, so that NULL is the only "no value"? | Keep as loaded; decide before the first release |
| 10 | Access creates the invoice first and assigns the customer later; this is why some invoices have customer 0. The new app may change this process, so that the user picks the customer when the invoice is created. | Same as Access in v1; redesign later |
| 11 | **Decided: rows are never deleted.** If a delete function exists, it is a soft delete: it sets a flag and the row stays. Access could delete rows but never offered it in the UI, and only invoices had a flag (`invoice_header.is_deleted`). So v1 has no delete function except the invoice flag, and no flag columns on other tables. **Open:** the "Delete line" button in §6.4. Did the Access line form have it? How does a user correct a wrong invoice line? | Soft delete for invoices only. If another delete function is designed, add a flag with a new schema migration. |
| 12 | Invoice output. **In version 1, step 9 (owner, 2026-11-21).** **Decided:** the app shows the invoice in an on-screen **preview**, which does not have to look exactly like the PDF. **Proposed:** ReportLab (pure Python, works in the packaged `.exe`, no printing step) makes the PDF directly from the data. The app saves it to the PDF folder from `settings.json` and opens it in the default viewer. The preview and the PDF use the same line and total calculation (§5.1), so their amounts are always the same. The PDFs are checked against the reference PDFs in `export/reference_invoices/`. **Open:** when a user reopens and changes an invoice, should the app warn about the saved PDF or overwrite it? | ReportLab; make the PDF when the user asks for it, and save a copy named by invoice number |
| 13 | **Decided: the app configuration is in `settings.json`, not in the database.** The database holds only master data and transactions. `settings.json` is next to the `data` folder (`WINE_SETTINGS_PATH` overrides the location). It holds the four Access settings: `invoice_address`, `invoice_bank_details` and `invoice_payment_terms` (text printed on invoices) and `invoice_pdf_folder` (different on each machine). The Access import writes the file from `tSettings`, and the check against the source compares every value. **Planned after version 1** (with the invoice PDF): copy the three invoice texts onto each invoice record, so that each invoice keeps its own texts. Version 1 makes no schema change after `001`, so until then the file holds the texts for all invoices. A backup must therefore include the `data` folder and `settings.json`. | Done as described |
| 14 | **Changed 2026-11-21 (owner): moved to version 2.** Version 1 keeps data transformations to a minimum: no schema change after `001`. Version 1 stores only the Access fields; the cause of a stock change stays in the free-text comment, as in Access. The step 2b mapping from comment to type (`Design_Evaluation.md`) therefore also covers the rows entered with version 1. Originally decided: three new columns outside the 1:1 copy (`Design_Evaluation.md`, M14 and M15), because this data cannot be added later. (a) `stock_transactions.movement_type`: the cause of a stock change, which the user picks on the stock change screen (purchase, count, transfer, write-off, sample, other; "other" needs a comment). (b) `recorded_at` on `stock_transactions`, `invoice_header` and `invoice_lines`: the time when the program wrote the row. The program sets it, and nobody can edit it. (c) `invoice_header.closed_at`: the time when the invoice was closed, set at each close. All three are NULL on rows from Access, and are required only on new rows (validate on write). A numbered schema migration after `001` adds them. The Access import still loads into the 1:1 schema of version 1, and then the program upgrades the file. **Gap for version 2:** `connect()` always upgrades to the newest version, and the import refuses all versions except 1. When the first new migration comes, the import needs a way to stop at version 1, or the import must be retired first. | Version 2 (step 2b) |
| 15 | **Decided (owner, 2026-11-21): the data stays next to the program.** The database (`data\`) and `settings.json` stay in the program folder, as today; no separate data folder. `build.ps1` keeps both during a build. | Done as described |

**Risks:**
- **Old copy of the data:** the numbers and data facts in this document (row counts, sums, orphan rows, negative stock) come from an export whose last row is from January 2015. The live Access file is newer. The import and its check against the source do not depend on these numbers. But repeat the checks in §8 that quote them on a current copy before the release.
- **Rounding:** VBA `Round` rounds half to even. Python's `round` does the same and matched all 665 invoice lines. Keep the golden test: a change to `Decimal` or to another rounding rule would break the amounts without any error.
- **One user at a time:** only one program instance may use the SQLite file, and the file must be on a local disk. If a second instance tries to write, it gets the error "database is locked". Do not keep the file in a synced folder (Dropbox, OneDrive) while the app runs, because the sync can corrupt it. To back up, copy the file while the app is closed.
- **Case in text comparison:** `NOCASE` folds ASCII letters only. Inside SQL, `Ø` and `ø` are different, so the app compares in Python where Danish letters are important.
- **Personal and bank data** is in the CSV files and in `settings.json`. Keep them out of all shared repos (`settings.json` is in `.gitignore`).
- **Not verified:** the display behaviour of the Access forms (tab order, exact layout) is not copied. This document specifies only how the data behaves.
