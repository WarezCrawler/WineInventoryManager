# Design Evaluation: Modularity Review

Date: 2026-11-15 (revision 2). Scope: `docs/Vinlager_Python_SQLite_Design.md`, `docs/Functionality.md` and the code built so far (`winedb/`, `migrate/`, `tests/`).

**Direction decided by the owner (revision 2):**

1. **Release 1 stays close to 1:1 with Access.** Stock and invoice only. No module layer yet.
2. **Modularity comes after release 1.** Modules: Stock, Order/Invoices, Accounting, Master data.
3. **After modularity, each ledger holds its own data.** Today the stock position is a union: `stock_transactions` minus `invoice_lines`. In the target, the stock ledger holds every movement itself. This opens partial deliveries and open-order management.

This revision replaces the first version, which advised to build the module layer before release.

## 1. Summary

The design is a good base for release 1. Its choices (1:1 data, migrations, golden tests, layer test) also make the later conversion safe. Doing modularity after release is a sound choice: it keeps release 1 small, and the 1:1 data gives a fixed reference to test the conversion against.

The risk is not the module split. The split moves code and ownership, not data. The risk is the **ledger conversion**: it changes how stock is computed, and it changes what an invoice means. Plan that change with care. Release 1 needs only a few cheap rules to keep it small (section 4).

| Area | Rating | Remark |
|---|---|---|
| Scope and discipline | Strong | v1 is small. The backlog is explicit. |
| Data safety and migration | Strong | Numbered migrations, backup first, audit of the import. |
| Business rules | Strong | Taken from the VBA code. Golden test over 665 lines. |
| Layer separation (UI / logic / data) | Strong | A test enforces it. |
| Readiness for modules after release | Fair | Fine if the rules in section 4 are followed. |
| Readiness for own-data ledgers | Weak today | Stock is derived from invoices, not recorded: an invoice line counts as shipped when saved. Also, no row-level link exists between a line and a movement. Plan it (section 6). |
| Money and audit readiness | Weak | Amounts are `REAL`. Closed invoices can be reopened. Matters for Accounting only. |

## 2. What the design does well

1. **Clear scope.** v1 has three functions. The rest is backlog.
2. **Plain SQLite and plain SQL.** No ORM. Moving tables between modules costs no code generation.
3. **Numbered migrations with `user_version` and a backup** before an upgrade (`winedb/db.py`). The conversion to modules is itself a migration. This pattern carries it.
4. **Layer test.** `tests/test_architecture.py` reads the imports with `ast`. The same method can guard module borders later.
5. **Golden tests.** All 665 lines recomputed, on-hand for all 283 item and warehouse pairs. These tests are the safety net for the ledger conversion. Treat them as a contract.
6. **Price snapshot on the invoice line.** An old line never changes when a price changes.
7. **Soft delete only.** Rows are never removed. Ledgers must follow the same rule (section 6.3).
8. **Settings outside the database,** with module-prefixed names (`invoice_*`).
9. **Open decisions are written down** with a default.

## 3. Findings

### 3.1 For release 1 (no change needed, but note them)

- **The import tools are tied to schema version 1** (`load_csv.py` checks `user_version`, `import_accdb.py` checks all tables for rows). With the new plan this is **correct**: the import runs once, at release 1, into a version-1 database. After release it must refuse to run. It already does. Do not generalise it. No module can seed rows before the import, because modules do not exist yet.
- **`on_hand` is one formula over two tables** (§5.3). It is right for 1:1. It is the first thing the ledger conversion replaces. Keep it in one function.
- **Stock and invoices are one domain with two sources.** The Access app does it this way. Keep it.

### 3.2 For the conversion to modules (after release 1)

- **One global migration chain.** `db.py` needs 001, 002, ... without gaps, and `user_version` is one integer. Modules need a chain each. This is a one-time change in the runner and a bootstrap migration (section 5, step 2a). It works on a live database. It does not need a pre-release change.
- **No concept of ownership.** Which module owns which table is not written down. Section 5 gives the list.
- **The UI menu is fixed** and shows disabled buttons for later functions (§6.1). A module-based menu must be built from the enabled modules.
- **`settings.py` has a fixed `KEYS` tuple.** Modules need to declare their own keys.
- **The build script adds only `winedb/migrations`** as data. Each module folder needs the same.

### 3.3 For own-data ledgers (the main risk)

These facts of the 1:1 model matter for the ledger:

1. **Stock is an assumption, not a record.** The stock figure is computed from commercial documents. It assumes that every invoice line has physically happened. Nothing records a delivery, a count or a difference found. The 15 negative item and warehouse pairs are probably a result: a sale was entered before the matching receipt.
2. **Stock leaves when a line is saved**, even on an open invoice. A cancelled draft or an edited line changes stock without any physical event. In the new model, stock leaves at **delivery**. For a direct sale, order, delivery and invoice are one act. For a partial delivery they are not.
3. **No row-level link.** Invoice and stock share `item_id` and `warehouse_id`, so the formula can join them. But `stock_transactions` does not say "caused by invoice line 123", and invoice lines have no movement row at all.
4. **Corrections today are edits.** A line can be changed while the invoice is open. An append-only ledger needs reversal rows instead of edits. The soft-delete rule (rows are never deleted) points the same way.
5. **Legacy rows are imperfect.** Two invoice lines have `warehouse_id = 0`, three invoices have no warehouse, four point to customer 0, and 15 item and warehouse pairs are negative. The conversion must carry these over as they are, not repair them (validate on write only).
6. **Amounts are `REAL`.** This is fine for the stock ledger (whole numbers). It is not fine for an accounting ledger.

### 3.4 Small inconsistencies in the design document (fixed 2026-11-15)

All five are corrected in `Vinlager_Python_SQLite_Design.md`:

- §1 said "In v1 (built)" although the main menu, stock and invoices are not built. It now says "In scope for v1" and points to `Functionality.md` for the status.
- §2 and §9.1 named `invoice_header.py`. They now name `invoices.py`, as §7 does.
- §4 called `column_map.py` the single source for the DDL. It now says: `column_map.py` is the source for the names, `001_init.sql` is the DDL, and a test checks that they agree.
- §7 listed `query()`, `execute()` and `transaction()` in `db.py`. It now lists `connect()` only, with `transaction()` as planned. `settings.py` was missing from the layout and is added.
- The first line referred to `Vinlager_Python_Rebuild_Plan.md` without saying where it is. It now says that the file is outside this repository, in the Access decomposition folder.

## 4. Release 1: rules that keep the conversion small

These cost almost nothing. They add no module code. Add them to the design as "conversion-ready rules".

1. **Group code by its future owner, in flat files.** `stock.py` for stock. `invoices.py` for invoice header, lines and close. One file (for example `masterdata.py`) for customers, items, warehouses and price lists. The later move is then a file move.
2. **One function for each rule that will change.**
   - `stock.on_hand(item, warehouse)`: the only place that knows the formula.
   - `invoices.close()`, `invoices.reopen()`, `invoices.set_deleted()`: the only places that change the status of an invoice. These are the later event points (Accounting will need them).
   - `invoices.save_line()`: the only place that writes a line. This is where the ledger write goes later.
3. **The UI calls these functions only.** No SQL on the tables of another future module from the UI or from another feature. (Already a principle. Add a test if cheap.)
4. **Keep the golden tests as a contract,** and add two: invoice totals per invoice, and on-hand per item and warehouse, both on synthetic data. The conversion must give identical results.
5. **Keep `created_at` on every line and movement** (already in the model). The conversion needs it for the backfill.
6. **Do not edit `001_init.sql` after release.** Every change is a new numbered file (already the rule).
7. **Do not create module folders, manifests or an event bus in release 1.** They would be unused code.
8. **Fix the document inconsistencies** (3.4). Done.

## 5. After release 1: the conversion in steps

Each step is its own release or pull request. Each ends with the golden tests unchanged and green.

### Modules and owned tables

| Module | Owns (existing tables) | Depends on |
|---|---|---|
| **Master data** | `warehouses`, `customers`, `items`, `prices_sales`, `prices_cost` (open: M5) | nothing |
| **Stock** | `stock_transactions` (becomes the stock ledger) | Master data |
| **Order / Invoices** | `invoice_header`, `invoice_lines` (later: orders, deliveries) | Master data, Stock |
| **Accounting** | new tables only | Master data, Order / Invoices |

You listed Master data last. In the dependency order it is first, because all other modules read it. Build order and dependency order can differ. Master data needs no data change, so it costs the least.

Rules (each one a test, in the style of `test_architecture.py`): a module imports only the modules it depends on. One module owns each table and only the owner writes to it. Other modules read through the owner's public functions. UI libraries stay in `winedb/ui`.

### Step 2a. Module skeleton, no data change

- Add the `schema_migrations` table. A **bootstrap migration** records the existing chain as the baseline of each module. From then on each module has its own chain, applied in dependency order, with the backup first.
- Add the module registry (an explicit list in code, not folder scanning, because of PyInstaller), the manifest, the menu registry and per-module labels and settings keys.
- Move the flat files into module folders. Add the architecture tests.
- Add a small event bus: synchronous, inside the same transaction. Two kinds: **notify** (`invoice.closed`) and **veto** (`invoice.before_reopen`). The veto lets Accounting refuse a reopen later.
- *Check:* same 8 tables, same data, all tests green, audit unchanged.

### Step 2b. Stock ledger with its own data

This is the change you described. The design:

- **One stock ledger.** Every stock change is a row in it. New columns say where the row came from: `source_type` and `source_id`. Source types: `purchase` (stock in), `count` (stock count and correction), `invoice_line` (from the backfill), later `delivery_line` and `return`. Today's rows in `stock_transactions` are only purchases and counts. Invoices never wrote to that table.
- **`on_hand` becomes `SUM(quantity)`** over the ledger. The union formula goes away.
- **Backfill** in one migration: for each of the 665 invoice lines, write one negative ledger row with the line's quantity, warehouse and `created_at`, and `source_type = 'invoice_line'`. Legacy oddities are carried over unchanged (3.3, item 5).
- **Writes:** saving a line writes the ledger row in the same transaction. Changing or deleting a line writes a **reversal row** and a new row. Nothing is edited or removed.
- **Proof:** keep the old formula as a test for one release. On-hand for all 283 pairs must be identical before and after. Add a consistency check that compares the ledger with the lines at any time.
- Existing `stock_transactions` rows stay. Only new columns are added. The old table has no type column, but the **comment** field carries it. A check of the export (863 rows, 46 distinct comments) shows that nearly every row has a comment that names its cause, and that there are more causes than purchase and count: purchases (a supplier and a delivery number, about 100 rows), counts and reconciliations (about 370), an opening balance and stock brought in (about 160), transfers between warehouses (30, in matching pairs), sample wines (156), write-offs and gifts (5), and one start-up batch (34 rows): sales from the first half of 2013, from before the invoice function, booked in one step in December 2013. It has no invoice and never will, so it counts as part of the opening load. Grouping by date does not work: 622 rows sit in nine large groups with mixed signs. So the backfill uses a **mapping table from comment to source type**, reviewed by the owner (46 lines to review, once). A comment that is not in the table gets `source_type = 'legacy'`. The mapping holds supplier and person names, so it stays out of the public repository, like the data. The source types grow by `transfer`, `write_off`, `sample` and `opening` (the opening type also covers the start-up batch; the comment stays on the rows). The classification does not change any quantity, so on-hand is identical either way. New rows use `purchase` or `count`. A separate Purchasing module (receipts against purchase orders) is a possible later addition, and it would write `purchase` rows. It is not in the planned module list.

### Step 2b.1. Structured stock count

Today a count is done by hand: signed adjustments with a comment, mostly at year end. The old data shows this habit (large reconciliation batches in December 2013 and November 2014). This step makes it a function. It comes directly after the stock ledger, because it books `count` rows.

- **Count session:** one record per count, with warehouse, count date, status (open, booked) and a comment. It is the audit record of the count.
- **Count lines:** one per wine. Each holds the system quantity at the count date, the counted quantity and the difference. The user types only the counted quantity.
- **Booking:** one step writes a `count` ledger row for each line with a difference, with the session as its source. Lines without a difference write nothing, but stay in the session as proof that the wine was counted.
- **Movements during the count:** the system quantity is the ledger sum **at the count date**, not at the moment of booking. A sale entered after the count date does not distort the difference.
- **Partial counts are allowed:** one warehouse, or a selection of wines. A wine that is not in the session is not changed.
- **No edits after booking.** A wrong count is corrected by a new session (ledger rule: append-only).
- **Report:** differences per session, and movements per type per year. This answers the year-end question "what was sales and what was other" without manual work.
- *Check:* after booking, on-hand equals the counted quantity for every counted wine. A session with no differences writes no ledger rows.

### Step 2c. Orders, deliveries, partial delivery

- **Document chain:** order (what the customer wants) → delivery (stock leaves; may be partial; repeated) → invoice (what is billed; may cover one or more deliveries).
- **Stock moves at delivery,** not at order and not at invoice. Add **reservation**: open order lines that are not yet delivered. Stock then has three numbers: *on hand*, *reserved* and *available* (on hand minus reserved).
- **A direct sale stays possible.** An invoice with no order is today's flow. One screen can create order, delivery and invoice in one act.
- **Legacy mapping (decision M8):** do not invent orders for old invoices. The 665 legacy lines keep their ledger row from step 2b and count as delivered and invoiced. The 14 open invoices are today's drafts that already reduce stock. Recommended: treat them as invoices that are not closed and already delivered. This keeps on-hand identical and makes up no history.
- Rename `invoice_lines.sales_line_id` and the status columns in this step, in a migration, with the golden tests as proof.

### Step 2d. Accounting

- Own tables with an `acc_` prefix. Own ledger of postings, written from events (`invoice.closed`, `invoice.deleted`). Order / Invoices never imports Accounting.
- **Exact money type.** Store ledger amounts as integer minor units. One rounding function in a shared place. Legacy `REAL` amounts are converted once at posting, with the rule written down.
- **Closed means posted.** Once an invoice is posted, the veto event refuses a reopen. A correction is a credit note, not an edit.
- Check the invoice number rule: a soft-deleted invoice leaves a gap in `invoice_id`. Accounting may need a gapless series with a record of each void.
- Foreign keys are allowed in the new tables. The legacy tables keep none until their orphan rows are handled.

Steps 2c and 2d are independent. Their order is your choice.

## 6. Design points for the own-data ledgers

### 6.1 Ledger rules (apply to stock and accounting)

1. **Append-only.** No update, no delete. A correction is a new row that reverses the old one.
2. **Every row names its source** (type and id) and carries `created_at`.
3. **Current state is a sum over the ledger,** never a stored number that someone can edit. If speed is a problem, add a derived table later and test it against the sum.
4. **The commercial record and the ledger are two things.** The invoice line is the commercial record (price, VAT). The ledger row is the effect (stock, money). They are written in one transaction and checked against each other.

### 6.2 Risk: two writes for one fact

Today one row (the line) is the only source. After step 2b the line and the ledger row can disagree if one write fails or code skips one. Controls: one function writes both; one transaction; a consistency check that runs in the tests and as an on-demand report.

### 6.3 Risk: the meaning of "invoice" changes

In Access an invoice is also an order and a delivery. In the new model these are three documents. Keep the old flow available (direct sale) so that daily work does not change on the day of the conversion.

### 6.4 Strict relations between modules (owner requirement, after version 2)

**Requirement:** every effect in one module can be traced back row by row to its cause in another module. A stock change that is reflected in accounting has at least as many rows in accounting as in stock. The same holds from sales to stock and from sales to accounting. Consistency checks can then be absolute, and the data is transparent.

Rules that follow from it:

1. **Row-level reference, always.** Each downstream row names exactly one upstream row (`source_type`, `source_id`, not null). The reference points upstream, which is also the dependency direction of the modules.
2. **One or more, never fewer.** One upstream row has one or more downstream rows. One sales line can have several stock rows (partial deliveries). One stock row has two or more accounting rows (debit and credit).
3. **No summary postings.** No "one posting per invoice" and no "one posting per day". A total is always a sum over rows, never a stored row of its own.
4. **Same transaction.** The upstream row and its downstream rows are written together or not at all. There is no moment at which the modules disagree.
5. **Reversals mirror.** A reversal row upstream gets its own reversal rows downstream. Downstream rows are never edited to follow an upstream correction.
6. **Every row has a source.** A manual entry (a manual journal, a manual stock correction) is its own document with its own type. No row is without a source.

**Absolute checks** (zero tolerance, run in the tests and as an on-demand report):

- Every upstream row that must have an effect has at least one downstream row.
- Every downstream row points to an existing upstream row of the right type.
- Sales to stock: the stock rows of a sales line sum to its delivered quantity, exactly.
- Stock to accounting: the accounting rows of a stock row sum to its value, exactly. Debit equals credit for each source row, not only in total.
- Sales to accounting: the accounting rows of a sales line sum to its amounts (net, VAT), exactly.

What this requires:

- **Exact money.** "Exactly" is not possible with `REAL`. Amounts in the ledgers are integer minor units. Rounding happens once, per line, in one function. VAT is already computed per line (§5.1), which fits: a per-invoice VAT calculation would create a rounding row with no line as its source.
- **A value on each stock row.** To post a stock change, the row needs a cost value at the moment it is written (a snapshot, like the price on an invoice line). The valuation method is left to the detailed design of version 2 (M12).
- **A defined list of stock types with an accounting effect.** Purchases, counts, write-offs, samples and sales have one. A transfer between warehouses has none, unless accounts are kept per warehouse.
- **A cut-off for legacy data.** Rows from before the start of Accounting have no accounting rows. Accounting starts with an opening balance at a cut-off date, and the strict rules apply to every row after it. Legacy rows are never forced to satisfy them (validate on write only). The opening balance is the one documented exception to rule 3.
- **Foreign keys in the new tables,** so the database itself refuses a row without a valid source where possible.

This requirement also answers the risk in 6.2: with a row-level reference and an absolute check, a missing or doubled write is found at once.

### 6.5 Documents are global master data (owner requirement)

Strict relations (6.4) need one shared identity for the thing a row points to. So the **document** is a global piece of master data.

- **One document register,** owned by Master data. Every business transaction is a document in it: invoice, order, delivery, purchase, count session, transfer, manual journal. The register holds only what is common: the global document id, the document type, the date and the visible number. The content stays in the module that owns the document type.
- **All modules reference the same id.** A stock row and an accounting row that come from the same invoice both carry the same document id. Tracing across modules is then one key, not a pair of type and id per module. This fits the dependency order: Master data is at the bottom, so every module may point to it.
- **Identity and number are two things.** The global id is the identity. It is technical, never reused and never shown as the business number. A **number range** (for example the invoice number series) is only a label that points to the source transaction. It is set once, when the document is created, and it has no other function: no relation uses it, and no rule depends on its value or its order.
- **Consequences.** The legacy `invoice_id` becomes the visible invoice number of the document, and stays unchanged for the user. Number ranges per document type can be designed freely later (gapless series, prefix, year) without touching any relation. This is the same direction as §9.1 of the design (identity keys and business keys).
- **Open for the detailed design:** how a row references a single *line* of a document (row-level tracing needs the line, not only the document); which module creates the register entry; whether a reversal is a new document or a new line in the same document.

## 7. Risks of this approach

- **A conversion on live data.** Steps 2b and 2c change a database with real history. Control: automatic backup first (exists), golden tests identical before and after, and a rehearsal on a copy of the live file before each release.
- **Late conversion cost.** Code written in release 1 can hide the union formula in many places. Control: the rules in section 4.
- **Over-design.** Four modules, one manifest and one event bus are enough. Do not add a plugin loader, dynamic discovery or a dependency solver until an outside module needs them.
- **Event misuse.** Keep the list of events short. Document each one: name, moment, payload, notify or veto.
- **Old choices stay in release 1** on purpose: 1:1 model, `REAL` amounts, no foreign keys, one user at a time.

## 8. Decisions needed

| # | Decision | Recommended |
|---|---|---|
| M1 | Release 1 gets only the rules in section 4, no module code? | Yes (your decision) |
| M2 | Module split after release 1 as step 2a, without data change, before the ledger change? | Yes |
| M3 | UI folder after the split: keep all UI in `winedb/ui/<module>/` (current rule), or give each module its own `ui/` sub-package? | Keep the rule |
| M4 | Events: synchronous, same transaction, with notify and veto? | Yes |
| M5 | Which module owns `prices_cost` and `prices_sales`? | **Decided: Master data**, because Stock and Invoices both read them |
| M6 | Stock ledger: append-only with reversal rows and `source_type` / `source_id`? | Yes |
| M7 | Does stock leave at delivery (not at line save) once orders exist? | Yes |
| M8 | Legacy invoices after conversion: no invented orders; open invoices count as delivered, not closed? | **Decided: yes** |
| M9 | Order of steps 2c (orders) and 2d (accounting)? | **Decided: orders first** (it changes the stock model). Accounting then posts the final document chain. |
| M10 | Fix the document inconsistencies (3.4)? | **Done** |
| M11 | Structured stock count as step 2b.1, directly after the stock ledger? | Yes |
| M12 | Stock valuation for accounting (cost snapshot per row, moving average or FIFO). | **Deferred:** subject to the detailed design of version 2. Not decided here. |
| M13 | Documents as global master data: one document register in Master data; number ranges are labels only (6.5)? | **Decided: yes** (owner requirement). Details in the version 2 design. |
