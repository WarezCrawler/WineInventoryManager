# Vinlager – Python + SQLite: Design and Implementation Plan (v1)

Follows `Vinlager_Python_Rebuild_Plan.md` (self-contained app, SQLite, logic in Python, one-time migration, Access only as archive). An earlier draft of this document used MySQL by mistake; the database is **SQLite**, a single local file the app creates itself.
Project root: `A:\Development\WineInventoryManager` (this repo). The Access decomposition is the read-only source in `A:\Development\WineDB_py\WineDB_work` (all `export/...` and `scripts/...` paths below are relative to that folder).
Sources: `export/schema.txt`, `export/code/*.vba.txt`, `export/modules/*`, `export/queries_sql.txt`, `export/forms/*`, `export/csv/*`, `export/data_quality_report.txt`, `scripts/check_rabat.py`.

## 1. Scope

**In v1 (built):**
1. Main menu (replacement for `fNavigation`).
2. Stock change input (replacement for `fVinlager_Change`).
3. Invoice input: header (`fFaktura`) and sale lines (`fVinlager_Salg`), including closing an invoice.

**Backlog (not built, listed in §9).** No data-model improvements in v1: tables and columns are copied 1:1.

## 2. Principles

- **Self-contained:** one Python program plus one SQLite file, no server, nothing to install besides Python packages. The database file is **not in git**; the app creates it on first start (§4.2).
- **Database = data and identity keys only.** Tables, PK/AUTOINCREMENT, indexes, NOT NULL and column defaults exactly as in Access. No FKs, triggers, views, procedures.
- **All logic in Python:** price/VAT/discount maths, stock on hand, defaults, validation, workflow.
- **No FKs in v1 on purpose.** Access enforced none, and the data has orphans (4 invoices point to customer 0: ids 6, 54, 59, 108). FKs would block the 1:1 load.
- **Plain SQL, no ORM.** Python's built-in `sqlite3` with parameterised queries.
- **UI separated from logic:** the UI only calls functions in `stock.py` / `invoice_header.py`, so the toolkit can be replaced.

## 3. Stack (decisions)

| Concern | Choice | Note |
|---|---|---|
| Database | SQLite (single file), standard-library `sqlite3` | No server, no driver to install. |
| Text comparison | `COLLATE NOCASE` on the text columns that are compared or searched | Like Access, `alm` = `Alm`. SQLite folds only ASCII case, so `ø` ≠ `Ø` inside SQL; searches that need it are done in Python (`casefold`). |
| UI | **NiceGUI** (pure Python, runs in the browser) | **Open:** alternative is PySide6 (native window, more code). Pick before step 5; steps 1–4 do not depend on it. |
| Config | Optional env var `WINE_DB_PATH`; default `data/wine_inventory.db` next to the program | No credentials, no `.env`. |
| Tests | pytest | |

## 4. Data model (1:1 copy)

Type mapping (SQLite): AutoNumber → `INTEGER PRIMARY KEY AUTOINCREMENT` (ids are never reused, and explicit ids can be inserted by the migration); Long/Integer → `INTEGER`; Text and Memo → `TEXT` (the Access length limits are not enforced); Yes/No → `INTEGER` 0/1; Date/Time → `TEXT` in ISO form `YYYY-MM-DD HH:MM:SS` (the exact format of the CSV export, and it sorts correctly); Double and Single → `REAL` (8-byte, so exported values like `120.7575` load unchanged).
**Tables and columns are renamed to English** (snake_case, ASCII, no reserved words; tables use descriptive English names such as `items`, `invoice_header`, `invoice_lines`; the Access name stays visible in §4.1 and `TABLE_MAP`). Only names change: data values (`Standard`, `Alm`, `Rød`, country names, settings keys like `<fakt_adr>`) are loaded as they are. The full mapping is in §4.1 and in `migrate/column_map.py`, which is the single source of truth for the DDL and the migration module.

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

### 4.1 Column mapping (Access → SQLite)

Machine-readable: `migrate/column_map.py` (`COLUMN_MAP[table][old_name] = new_name`). Checked against the CSV headers and `schema.txt`: every column is covered, none missing. The CSV column order equals the mapping order, so the migration can rename by header.

| Table (Access → new) | Access column | New column | Meaning |
|---|---|---|---|
| tLagre → `warehouses` | Lager_ID / LagerNavn / Kommentar | warehouse_id / warehouse_name / comment | warehouse |
| tKunder → `customers` | Kunde_ID | customer_id | |
| | Kundenavn / Fornavn / Efternavn | customer_name / first_name / last_name | |
| | By / Post_nr / Adresse / Tlf | city / postal_code / address / phone | |
| | Skjul | is_hidden | hidden from pickers |
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
| | Quantity / Kommentar | quantity / comment | signed |
| tVinlager_Salg → `invoice_lines` | Vin_SalgID / Fakt_ID | sales_line_id / invoice_id | |
| | Vin_ID / Lager_ID / Date_Create | item_id / warehouse_id / created_at | |
| | Quantity / Kommentar | quantity / comment | |
| | SalgsPris | sales_price | unit price, VAT included |
| | SamletPris | amount_ex_vat | |
| | SamletPris_mMoms | amount_incl_vat | |
| | CostPris / SamletCostPris | cost_price / amount_cost | |
| | Momssats / PrisType | vat_rate / price_type | |
| | Rabat | discount | VAT-included amount |
| tPrisliste_Cost → `prices_cost` | Id / Vin_ID | cost_price_id / item_id | |
| | PrisType / CostPris | price_type / cost_price | |
| | test_slet | test_delete | unused, kept 1:1 |
| tPrisliste_Salg → `prices_sales` | Id / Vin_ID | sales_price_id / item_id | |
| | PrisType / SalgsPris / Momssats | price_type / sales_price / vat_rate | |
| tSettings → `settings.json` (not a table, see decision 13) | Setting | invoice_address / invoice_bank_details / invoice_payment_terms / invoice_pdf_folder | `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>`, `<fakt_savelocation>`; the Danish Description column is documentation and is not carried over |

Not migrated: `USysApplicationLog`. Names to note: `stock_transactions` (Access `tVinlager`) is the stock movement table (`stock_line_id`) and `invoice_lines` (Access `tVinlager_Salg`) holds invoice sale lines (`sales_line_id`).

Notes:
- `USysApplicationLog` (3 rows from a failed 2013 Access data macro) is **not** migrated: it is an Access system artefact.
- `created_at` has an Access default of `Now()`. Python sets it explicitly on insert (logic stays in Python).
- `prices_cost.test_delete` is empty in all rows; kept for 1:1.
- Access `Required` is kept as `NOT NULL`; Access `Allow zero length` (empty text) has no SQLite equivalent and is not enforced.
- These statements are the content of the first migration `001_init.sql` (§4.2).

### 4.2 First start: the app creates its own database

- **Location:** `WINE_DB_PATH`, default `data/wine_inventory.db` next to the program. The `data/` folder and all `*.db` / `*.sqlite*` files are in `.gitignore`.
- **On every start** `winedb.db.connect()` does this:
  1. If the file does not exist: create the folder and the file, then apply every migration in `winedb/migrations/` in order (`001_init.sql` = §4). The first start therefore works from a fresh clone and gives an empty but working app.
  2. If it exists: read `PRAGMA user_version` and apply only the newer migrations, each in its own transaction. Before upgrading a non-empty database, copy the file to `<name>.bak-<timestamp>`.
  3. If `user_version` is higher than the newest migration the program knows (an older program opening a newer database), stop with a clear message and change nothing.
- `user_version` is set to the migration number after each successful migration. A schema change is one new numbered `.sql` file; a logic change needs no migration. This is also how the database is patched without ever copying it by hand.
- The empty database has no wines, customers or warehouses. Historical data is loaded by the one-time migration tool (§8 step 3) into a new file created by the same `connect()`; it refuses to load into a database that already has rows.
- Connection settings: `sqlite3.Row` row factory; no foreign keys defined, so none enforced. The file is meant to be opened by **one program instance at a time** and kept on a local disk (not a shared or synced folder).

## 5. Business logic specified from the Access code

All in Python, no DB logic. Everything below is taken from the VBA/queries, not guessed.

### 5.1 Line amounts (`fVinlager_Salg.CalcFullPrice`)
```
amount_incl_vat = round(sales_price * quantity - discount, 2)     # VAT-inclusive total
amount_ex_vat   = round(amount_incl_vat / (1 + vat_rate), 2)     # ex VAT
amount_cost     = round(cost_price * quantity, 2)
```
`sales_price` is the VAT-inclusive unit price and `discount` is a VAT-inclusive amount off the line. **Verified: this reproduces all 665 historical lines with 0 mismatches** (`scripts/check_rabat.py`). Null values count as 0 (VBA `Nz`).

### 5.2 Prices on a line
- **Cost price default** (`GetCostPrisStandard`): `cost_price` of the first `prices_cost` row (lowest `cost_price_id`) for the wine with `price_type = 'Standard'`; `0` if none. The user can also pick another cost row for the wine, or type the value.
- **Sales price:** the user picks one of the wine's `prices_sales` rows; this copies `sales_price`, `vat_rate` and `price_type` onto the line. Typing a price by hand sets `price_type = ''` (price list selection is cleared) and keeps `vat_rate`.
- The line stores a **snapshot** of price, VAT rate and cost; later price list changes never alter existing lines.

### 5.3 Stock on hand (`TotalVinQ`, view `uVinlager`)
`on_hand(item_id, warehouse_id) = SUM(stock_transactions.quantity) − SUM(invoice_lines.quantity)`, summed over all rows for that wine and warehouse. Negative `stock_transactions.quantity` rows are stock removals/corrections (341 of 863 rows). Computed in Python with two `SUM` queries. No stock guard exists in Access, so none in v1.

### 5.4 Invoice rules
- **Open invoice** = `is_closed = 0`. Lines can be added/edited only on open invoices (the Access line form is bound to `qVinlager_Salg`, which filters `is_closed <> True`). Closing = set `invoice_header.is_closed = 1`. Re-opening is a separate screen (backlog).
- **New line defaults:** `invoice_id` = chosen invoice, `warehouse_id` = the invoice's `warehouse_id` (`GetDefaultLagerID`), `created_at` = now, `quantity` 0, `discount` 0. `warehouse_id` is NOT NULL on lines, so if the invoice has no warehouse (3 do), the user must pick one.
- **Header:** `customer_id` (customer picker: customers with `is_hidden = 0`, ordered by name, plus a "contains" name search), default warehouse `warehouse_id`, `invoice_date`, `comment`, `hide_subtotals`, `is_closed`, `is_deleted`. Customer address, zip, city and phone are shown read-only.
- **Delete flag (`is_deleted`):** ticking it shows the Access warning *"Be aware that this invoice will be suppressed, and must have zero quantity and amounts"* (Danish original text kept). It is a soft delete; nothing is physically removed. Hidden in the exports (`uVinlager_Excel`).
- **Invoice number** = `invoice_id` (auto-increment). Python reads the new id from the insert (`lastrowid`); the Access code used `DMax`, which could return another user's invoice number. With SQLite `lastrowid` is exact.

### 5.5 Stock change rules (`fVinlager_Change`)
A stock change is an insert into `stock_transactions`: `item_id`, `warehouse_id`, `quantity` (signed, + adds, − removes), `comment`, `created_at` (default now). The form shows the wine's name, vintage, house, country, size, type and the current quantity for the chosen wine and warehouse (`TotalVinQ`). Existing movements are not deleted from this form (deletion disabled in Access).

## 6. Screens

### 6.1 Main menu (from `fNavigation`)
Title "Lagerstyring i særklasse" with the logo (`export/assets/VinotrentinoLogo.png`). Left: list of **open invoices** (`is_closed <> 1`, newest first: invoice no., customer no., customer name). Buttons, with the original captions:

| Button | v1 |
|---|---|
| Åben Faktura (opens lines for selected invoice) | **yes** |
| Åben faktura egenskaber (selected invoice header, or a new one if none selected) | **yes** |
| Open Vinlager tilgange/afgange (stock change, new entry) | **yes** |
| Vedligehold Kundedata, List Kunder, Gen­åben lukkede faktura, Generer Faktura, Vinliste, Prisliste Salg, Prisliste Cost, Open Lager Stamdata, Vis lagerrapport, Show advanced settings, Import vinlager tilgange/afgange, Mail Liste Export | shown disabled (backlog) |
| Quit | yes |

Access detail kept: the open-invoice list uses an **inner join to customers**, so the 4 drafts with customer `0` are invisible there. **Open decision:** use a LEFT JOIN and show "(ingen kunde)" so they can be finished or deleted (recommended), or keep the Access behaviour.

### 6.2 Stock change screen
Wine picker (search by `item_code` prefix as in the invoice form, or by name; list shows name, vintage, type, size) → warehouse → signed quantity → comment → date (default now) → **Save** / **Cancel**. Live: current quantity and quantity after the change. Below: the 20 latest movements for the chosen wine and warehouse.

### 6.3 Invoice header screen
Fields as in §5.4. Buttons: Save, Close invoice (sets `is_closed`), Open lines. New invoice requires a customer (the Access default of customer `0` is not offered).

### 6.4 Invoice lines screen
Top: invoice number, customer, date, `is_closed` toggle ("Luk faktura?"). Grid of the invoice's lines (wine, qty, unit price, discount, price type, VAT rate, totals ex/incl VAT) and an entry panel: wine find (UID prefix → pick), `quantity`, sales price picker + manual price, `discount`, VAT rate, cost price picker, `comment`, warehouse, current stock in that warehouse. All three totals update live using §5.1. Save, Undo, Delete line, New line. Invoice totals (sum ex VAT, sum incl VAT) shown under the grid.

## 7. Code layout

```
WineInventoryManager/   # project root
  docs/                # this document
  data/                # SQLite file, created on first start, git-ignored
  winedb/
    config.py        # database path (WINE_DB_PATH or default)
    db.py            # connect() = create-if-missing + migrations (§4.2), query(), execute(), transaction()
    migrations/      # 001_init.sql (§4), then 002_..., numbered
    logic.py         # pure functions: line_amounts(), default_cost(), (no DB access)
    stock.py         # on_hand(), add_movement(), recent_movements()
    invoices.py      # open_invoices(), get/save_header(), lines(), save_line(), close()
    ui/              # NiceGUI pages: menu, stock_change, invoice_header, invoice_lines
  migrate/
    column_map.py    # Access -> English table and column names (§4.1)
    load_csv.py      # CSV -> SQLite, then reconcile
  tests/
```

## 8. Implementation steps

Each step has an acceptance check; do them in order.

1. **Skeleton.** Repo, venv, `pytest`, NiceGUI; `config.py` (database path). *Check:* `pytest` runs; no database exists yet.
2. **Schema and first start (§4.2).** `001_init.sql` from §4 and `db.connect()` with create-if-missing and `user_version` handling. *Check:* deleting `data/` and starting the app creates the file with all 8 tables and `user_version = 1`; a second start changes nothing; a database with `user_version = 99` is refused; column names equal `COLUMN_MAP` and the types and nullability match `schema.txt`.
3. **Data load + reconciliation (`migrate/load_csv.py`).** Read the 9 CSVs (UTF-8 with BOM) from `export/csv/` and rename each header with `COLUMN_MAP` (§4.1; fail if a CSV has a column the map does not know, or the map has one the CSV lacks); booleans `True/False` → 1/0; empty cell → `NULL` (the CSV cannot tell empty from NULL, so text fields lose that distinction; document it); insert with the original ids so keys are preserved; `AUTOINCREMENT` continues after the max id (SQLite keeps it in `sqlite_sequence`; check with a test insert); the target is created through `connect()` and a non-empty target is refused. *Check:* row counts 143 / 176 / 3 / 240 / 442 / 4 / 863 / 665 / 228; Σ `amount_ex_vat` = 326,572.40; max `invoice_id` 150; 129 closed + 14 open invoices; 341 negative `stock_transactions` rows. Re-runnable by deleting the target file first.
4. **Logic + golden test.** `logic.line_amounts()` (§5.1) and `stock.on_hand()` (§5.3). *Check:* pytest recomputes all 665 lines from the DB and gets the stored totals (0 mismatches); on-hand for all 283 wine/warehouse combinations matches the CSV-based calculation (15 of them negative, as in the data report).
5. **UI shell and main menu.** NiceGUI app, menu page with the open-invoice list and buttons (§6.1), disabled backlog buttons. *Check:* the list shows the 14 open invoices (or 10 if the inner join is kept).
6. **Stock change screen** (§6.2). *Check:* adding +6 and −2 changes on-hand by +4 and writes two `stock_transactions` rows with correct `created_at`.
7. **Invoice header screen** (§5.4, §6.3). *Check:* create, edit, set delete flag, close; the row in `invoice_header` is as Access would store it.
8. **Invoice lines screen** (§5.2, §6.4). *Check:* re-enter an existing historical invoice (e.g. one with a `discount`, one with 0% VAT, one with negative quantity) and get identical line values; closed invoices are read-only.
9. **End-to-end and parallel run.** Run on a copy of the migrated database file; enter the same new invoice and stock change in Access and in the new app; compare the stored rows.

## 9. Backlog (not in v1)

From the Access app, in rough priority: invoice **PDF** (`rFaktura`; spec `export/report_spec/rFaktura.spec.json`, reference PDFs in `export/reference_invoices/`); **re-open closed invoice** (`fFaktura_genåben`); **copy invoice** (`DBCopyFakt`: copies header with new customer, today's date and `is_closed`/`warehouse_id`/`hide_subtotals`; copies lines with date today); **customer maintenance** and **mail list export** (`on_mailing_list = 1 AND is_hidden = 0 AND email <> ''`, 128 eligible); **wine list maintenance** (value lists: type `Rød;Hvid;Rose;Desert;Mousserende`, size `Alm;Halv;Magnum;Db. Mgm;50 cl.`, though the data uses `MGM`/`DMGM`); **price lists** sale/cost; **warehouse** master data; **settings screen** (`settings.json`, incl. PDF save folder); **stock report** (`qVinliste`) and **customer list** (`rKundeListe`); **stock import** (`qVinlager_Change_Import`); **Excel export** (`uVinlager_Excel`); **consistency check query**.

### 9.1 Key strategy: identity keys now, business keys later

- **v1:** every relation uses the identity (surrogate) key, 1:1 with Access (`item_id`, `customer_id`, `warehouse_id`, `invoice_id`, ...).
- **Direction:** every dimension (wine, customer, warehouse, and the free-text lookups like `price_type`, `item_type`, `bottle_size`) eventually gets a **business key that the users give and name themselves**, and relations point to that instead of the identity.
- **Precedent in the existing system:** `item_code` (`Vin_UID`) is exactly that. It was added after the fact, is unique, is what users type to find a wine, and has worked for 10+ years, but the tables still relate through `item_id`, not the code. v1 keeps this as it is. `price_type` is already a de-facto business key (free text, used in comparisons) without being a proper dimension.
- **Cheap rules for v1 so the later change stays small:**
  1. Keep `item_code` unique (it is, `CREATE UNIQUE INDEX`) and show it in wine pickers and lists next to the name.
  2. Resolve a wine from a typed code in **one** function (`find_item_by_code`), and never hard-code identity values or assume ids are consecutive or meaningful.
  3. Keep each relation lookup (`item_id`, `customer_id`, `warehouse_id` joins) in the `stock.py` / `invoice_header.py` data functions, not in the UI.
- **How the change is made later:** one numbered migration per dimension (§4.2): add the business key column, backfill and check it is unique and not empty, add the unique index, add the new key column to the child tables, fill it by joining on the old id, then rebuild the tables without the old column. The golden tests (§8 step 4) must give identical results before and after.
- **Open (not for v1):** which dimensions get a key and what it looks like (customer number? warehouse code?); whether the business key should become the primary key itself or stay a unique alternate key; how to handle codes users want to rename after history exists (history must keep pointing at the same wine).

After v1 is stable: the data model clean-up (foreign keys, lookup tables, normalising `alm`/`Alm`, the non-wine products stored as wines, stored totals), logins, backup routine, packaging as a single Windows `.exe` (PyInstaller; the database stays outside the exe in the data folder).

## 10. Open decisions and risks

| # | Item | Default if not decided |
|---|---|---|
| 1 | UI toolkit: NiceGUI vs PySide6 | NiceGUI |
| 2 | Open-invoice list: inner join (Access) vs left join (shows 4 drafts with customer 0) | Left join |
| 3 | `invoice_date`: no default found in the Access form. Prefill today, or leave blank like Access? | Prefill today, editable |
| 4 | More than one `Standard` cost row for a wine (not checked) | Lowest `cost_price_id`; log a warning |
| 5 | Warn when a sale or removal makes stock negative (Access never did; 15 combinations already negative) | No warning in v1 |
| 6 | NULL vs empty string for text fields on load | NULL |
| 7 | Access `Single` columns stored as 8-byte `REAL` | `REAL` |
| 8 | Invoice date and `is_closed` workflow on close (Access has no extra step) | Same as Access |
| 9 | "No value" in lookup columns is stored by Access as `0` (`invoice_header.customer_id` 4 rows, `invoice_lines.warehouse_id` 2 rows in the snapshot) and as NULL (`invoice_header.warehouse_id` 3 rows). The loader keeps both as they are. Convert 0 to NULL in one explicit, reported step after the load, so NULL is the only "none"? | Keep as loaded; decide before first release |
| 10 | Access creates the invoice first and assigns the customer afterwards (hence customer 0). The new app may change this process (pick the customer when creating the invoice) | Same as Access in v1; redesign later |
| 11 | **Decided: rows are never deleted; if a delete function exists it is a soft delete (a flag; the row stays).** Access could technically delete rows but never offered it in the UI, and only invoices had a flag (`invoice_header.is_deleted`). So v1 has no delete function except the invoice flag, and no flag columns on other tables. Open: the "Delete line" button in §6.4 (was it in the Access line form? how does a user correct a wrong line?) | Invoice soft delete only; add a flag with a new migration if another delete function is designed |
| 12 | Invoice output. **Decided:** an on-screen **preview** in the app, which need not look exactly like the PDF. **Proposed:** the PDF is generated directly from the data with ReportLab (pure Python, works in the packaged `.exe`; no printing step), saved to the PDF folder from `settings.json` and opened in the default viewer. The preview and the PDF use the same line and total calculation (§5.1), so they cannot disagree on amounts. Checked against the reference PDFs in `export/reference_invoices/`. Open: keep the saved PDF when an invoice is later reopened and changed (warn or overwrite)? | ReportLab; generate on request and save a copy named by invoice number |
| 13 | **Decided: app configuration lives in `settings.json`, not in the database.** The database holds master data and transactions only. `settings.json` sits next to the `data` folder (`WINE_SETTINGS_PATH` overrides) and holds the four Access settings: `invoice_address`, `invoice_bank_details`, `invoice_payment_terms` (text printed on invoices) and `invoice_pdf_folder` (machine-specific). The import writes it from `tSettings` and the audit compares every value. **Planned in migration 002:** copy the three invoice texts onto each invoice record, so the records carry themselves; until then the file holds them as the defaults for new invoices. A backup is therefore the `data` folder plus `settings.json` | Done as described |

Risks:
- **Rounding:** VBA `Round` rounds half to even; Python's `round` does too and matched all 665 lines, but keep the golden test, since a switch to `Decimal` or another rounding rule would break it silently.
- **One user at a time:** the SQLite file must be used by a single program instance on a local disk. A second instance gets "database is locked" on write, and the file must not sit in a synced folder (Dropbox, OneDrive) while the app runs, which can corrupt it. Back up by copying the file while the app is closed.
- **Collation:** `NOCASE` folds ASCII only. `Ø` and `ø` compare as different inside SQL, so Python-side matching is used where Danish letters matter.
- **Personal and bank data** in the CSVs and `settings.json`: keep out of any shared repo (`settings.json` is in `.gitignore`).
- **Unverified:** the Access form *display* behaviours (tab order, exact layout) are not reproduced; only data behaviour is specified above.
