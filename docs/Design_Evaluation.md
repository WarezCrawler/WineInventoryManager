# Design Evaluation: Modularity Review

Date: 2026-11-15 (revision 3: all decisions checked a second time, see section 9). Scope: `docs/Vinlager_Python_SQLite_Design.md`, `docs/Functionality.md` and the code built so far (`winedb/`, `migrate/`, `tests/`).

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

- **One global migration chain.** `db.py` needs 001, 002, ... without gaps, and `user_version` is one integer. The first versions of this review advised one chain per module. The second review withdraws that (9.2): **keep the one chain.** It gives the same order on a new database and on an upgraded one. The file name carries the owning module.
- **No concept of ownership.** Which module owns which table is not written down. Section 5 gives the list.
- **The UI menu is fixed** and shows disabled buttons for later functions (§6.1). A module-based menu must be built from the enabled modules.
- **`settings.py` has a fixed `KEYS` tuple.** Modules need to declare their own keys.
- **The build script adds `winedb/migrations`** as data. With one chain this stays as it is.

### 3.3 For own-data ledgers (the main risk)

These facts of the 1:1 model matter for the ledger:

1. **Stock is an assumption, not a record.** The stock figure is computed from commercial documents. It assumes that every invoice line has physically happened. Nothing records a delivery, a count or a difference found. The 15 negative item and warehouse pairs show it. Checked on the data (the groups overlap): 4 pairs have no stock row at all (the wine was sold from a warehouse that never received it), 2 are in warehouse 0, and 9 involve an open invoice.
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

## 5. After release 1: version 2 and version 3

- **Version 2:** modules, stock ledger, stock count, orders and deliveries (steps 2a to 2c).
- **Version 3:** Accounting (step 3a), with Accounts receivable (3b) and Banking (3c) as optional modules.

Each step is its own release or pull request. Each ends with the golden tests unchanged and green.

### Modules and owned tables

| Module | Owns (existing tables) | Depends on |
|---|---|---|
| **Master data** | `warehouses`, `customers`, `items`, `prices_sales`, `prices_cost`; later the document register (6.5) | nothing |
| **Stock** | `stock_transactions` (becomes the stock ledger) | Master data |
| **Order / Invoices** | `invoice_header`, `invoice_lines` (later: orders, deliveries) | Master data, Stock |
| **Accounting** (version 3) | new tables only | Master data, Stock, Order / Invoices |
| **Accounts receivable** (version 3, optional) | new tables only | Master data, Order / Invoices, Accounting |
| **Banking** (version 3, optional) | new tables only | Master data, Accounting |

You listed Master data last. In the dependency order it is first, because all other modules read it. Build order and dependency order can differ. Master data needs no data change, so it costs the least.

Rules (each one a test, in the style of `test_architecture.py`): a module imports only the modules it depends on. One module owns each table and only the owner writes to it. Other modules read through the owner's public functions. UI libraries stay in `winedb/ui`.

### Step 2a. Module skeleton, no data change

- **Keep the one migration chain** and `user_version` (9.2). New files carry the owning module in the name, for example `004_stock_ledger.sql`. Step 2a therefore changes no schema and no data.
- Add the module registry (an explicit list in code, not folder scanning, because of PyInstaller), the manifest, the menu registry and per-module labels and settings keys.
- Move the flat files into module folders. Add the architecture tests.
- Add a small event bus: synchronous, inside the same transaction. Two kinds: **notify** (`invoice.closed`) and **veto** (`invoice.before_reopen`). The veto lets Accounting refuse a reopen later. Use it only where the upstream module may not import the downstream one, which means toward Accounting (9.4). Order / Invoices calls Stock directly.
- *Check:* same 8 tables, same data, all tests green, audit unchanged.

### Step 2b. Stock ledger with its own data

This is the change you described. The design:

- **One stock ledger.** Every stock change is a row in it. Each row has a `movement_type` (the cause) and a reference to the source document and line. The document register (6.5) is built first, in this step, so that the reference has its final form from the first row. Movement types: `purchase` (stock in), `count` (stock count and correction), `transfer`, `write_off`, `sample`, `sale` (from an invoice line, later from a delivery line), later `return`. The column `movement_type` exists from release 1 (M15), so rows entered in the new program are already classified. The rows from Access are purchases, counts and similar changes. Invoices never wrote to that table.
- **`on_hand` becomes `SUM(quantity)`** over the ledger. The union formula goes away.
- **Backfill** in one migration: for each line of a closed invoice, write one negative ledger row with the line's quantity and warehouse, `movement_type = 'sale'`, a reference to the line and the posting date (9.3). Lines on open invoices are drafts. They are not booked and count as reserved (9.3). Legacy oddities are carried over unchanged (3.3, item 5).
- **Two dates on each row:** the posting date (the business date: when it happened) and the recorded time (when it was entered; set by the program, never edited). Today there is only `created_at`. The data shows why both are needed: 58 of the 665 invoice lines were created more than 30 days from the invoice date, and the start-up batch was entered six months after the sales.
- **Writes:** the stock row is written in the same transaction as the event that causes it. Nothing is edited or removed: a correction is a **reversal row** and a new row. **Decided (M14):** the row is booked when the transaction is closed, with a posting date. A save of a draft line books nothing. Lines on open invoices count as reserved (9.3).
- **Proof:** keep the old formula as a test for one release. For every item and warehouse pair, the old on-hand figure must equal the new *available* figure (on hand minus reserved). Add a consistency check that compares the ledger with the lines at any time.
- Existing `stock_transactions` rows stay. Only new columns are added. The old table has no type column, but the **comment** field carries it. A check of the export (863 rows, 46 distinct comments) shows that nearly every row has a comment that names its cause, and that there are more causes than purchase and count: purchases (a supplier and a delivery number, about 100 rows), counts and reconciliations (about 370), an opening balance and stock brought in (about 160), transfers between warehouses (30, in matching pairs), sample wines (156), write-offs and gifts (5), and one start-up batch (34 rows): sales from the first half of 2013, from before the invoice function, booked in one step in December 2013. It has no invoice and never will, so it counts as part of the opening load. Grouping by date does not work: 622 rows sit in nine large groups with mixed signs. So the backfill uses a **mapping table from comment to source type**, reviewed by the owner (46 lines to review, once). A comment that is not in the table gets `movement_type = 'legacy'`. The mapping holds supplier and person names, so it stays out of the public repository, like the data. The mapping can also give the type `opening` (it also covers the start-up batch; the comment stays on the rows). The classification does not change any quantity, so on-hand is identical either way. Rows entered after release 1 need no mapping: they carry the type from the screen (M15). A separate Purchasing module (receipts against purchase orders) is a possible later addition, and it would write `purchase` rows. It is not in the planned module list.

### Step 2b.1. Structured stock count

Today a count is done by hand: signed adjustments with a comment, mostly at year end. The old data shows this habit (large reconciliation batches in December 2013 and November 2014). This step makes it a function. It comes directly after the stock ledger, because it books `count` rows.

- **Count session:** one record per count, with warehouse, count date, status (open, booked) and a comment. It is the audit record of the count.
- **Count lines:** one per wine. Each holds the system quantity at the count date, the counted quantity and the difference. The user types only the counted quantity.
- **Booking:** one step writes a `count` ledger row for each line with a difference, with the session as its source. Lines without a difference write nothing, but stay in the session as proof that the wine was counted.
- **Movements during the count:** the system quantity is the ledger sum **at the count date**, not at the moment of booking. A sale entered after the count date does not distort the difference.
- **Partial counts are allowed:** one warehouse, or a selection of wines. A wine that is not in the session is not changed.
- **No edits after booking.** A wrong count is corrected by a new session (ledger rule: append-only).
- **Report:** differences per session, and movements per type per year. This answers the year-end question "what was sales and what was other" without manual work.
- **Entries dated before a booked count:** an entry with a business date before a booked count makes that count wrong afterwards. The detailed design must say whether such an entry is refused or only warned.
- *Check:* after booking, on-hand at the count date equals the counted quantity for every counted wine. A session with no differences writes no ledger rows.

### Step 2c. Orders, deliveries, partial delivery

- **Document chain:** order (what the customer wants) → delivery (stock leaves; may be partial; repeated) → invoice (what is billed; may cover one or more deliveries).
- **Stock moves at delivery,** not at order and not at invoice. Add **reservation**: open order lines that are not yet delivered. Stock then has three numbers: *on hand*, *reserved* and *available* (on hand minus reserved).
- **A direct sale stays possible.** An invoice with no order is today's flow. One screen can create order, delivery and invoice in one act.
- **Legacy mapping (decision M8):** do not invent orders for old invoices. Lines of closed invoices keep their ledger row from step 2b and count as delivered and invoiced. Open invoices have no known delivery or payment state. Step 2b treats them as reserved, and the owner goes through them after the migration (9.3). Those still open at step 2c become orders or invoices with nothing delivered yet, so their lines stay reserved. No history is made up.
- Do not rename existing columns in this step unless a rule needs it. A rename gives risk and no function. (An earlier version of this review proposed a rename. Withdrawn.)

### Version 3. Accounting, with optional Accounts receivable and Banking

Version 3 comes after version 2 (M9). The strict relations in 6.4 make this order necessary: Accounting posts against deliveries and invoices, so that chain must be final first.

#### Step 3a. Accounting (general ledger)

- Own tables with an `acc_` prefix. Own ledger of postings, one set per source row (6.4). When a stock row is booked and when an invoice is closed, Accounting writes its rows for each line in the same transaction. Stock and Order / Invoices never import Accounting. They publish events.
- **Purchases need a document first.** Today a purchase is a stock row with a free-text comment. To post it, Accounting needs the supplier and the cost per line. So a purchase receipt document, and suppliers as master data, must exist before Accounting starts. They can live in Stock or in a Purchasing module.
- **Start with a full count.** The opening balance at the cut-off needs a counted stock without negative quantities. 15 pairs are negative today.
- **Exact money type.** Store ledger amounts as integer minor units. One rounding function in a shared place. Legacy `REAL` amounts are converted once at posting, with the rule written down.
- **Closed means posted.** Once an invoice is posted, the veto event refuses a reopen. A correction is a credit note, not an edit.
- Check the invoice number rule: a soft-deleted invoice leaves a gap in `invoice_id`. Accounting may need a gapless series with a record of each void.
- Foreign keys are allowed in the new tables. The legacy tables keep none until their orphan rows are handled.
- **Legal check before the design.** Danish bookkeeping law sets rules for digital bookkeeping systems, also for systems that a business builds itself (for example storage, backup and access for the authorities). Check with the accountant which rules apply before step 3a is designed.

#### Step 3b. Accounts receivable (optional)

What each customer owes, and which invoices are paid.

- **Open item per invoice.** A closed invoice creates a receivable for its customer. A payment is allocated to one or more open items. A credit note reduces an open item.
- **The payment state of an invoice lives here.** This is the third state from 9.3 (delivery, invoicing, payment). Without this module the payment state stays unknown, as today.
- **Functions:** open items per customer, a list of overdue invoices, a statement for a customer, allocation of payments.
- **Without the module:** Accounting posts all invoices to one receivables account. The total is right, but there is no balance per customer and no list of what is open.
- **Start at a cut-off date.** When the module is switched on, the invoices that are not paid at that date are entered as opening open items, each with a reference to its invoice. Invoices paid before the cut-off get no open item.
- **No loss of information (owner principle, M16).** The classic design, one open item per invoice, is a summary and loses detail. The rule:
  - The AR row itself need not carry all details. But any detail that the AR row does not carry must be tracked in the general ledger, with a reference to the source.
  - **Closing an AR record counterposts the financial record exactly.** The closing rows mirror the opening rows dimension by dimension.
  - **A fully closed record sums to zero on every dimension** (customer, account, document, VAT code and any other dimension), except the dimensions that are different on purpose, such as the posting date.
  - This gives an absolute check: for each closed record, the sum per dimension is zero.
- **Open:** how many details the AR balance row carries (per invoice, per line, or per VAT code) is not decided. It waits for the detailed design.

#### Step 3c. Banking (optional)

The bank account in the program, and the match of bank lines with the books.

- **Bank statement import.** The statement lines are read from a file from the bank (for example CSV) and stored as they are. Each line is a document in the register (6.5), so all later effects point to it.
- **Match and post.** The user matches a bank line to its cause: a customer payment, a supplier payment, a fee. The match writes the postings in Accounting, with the bank line as the source.
- **Bank reconciliation:** the balance in the books is compared with the balance of the statement. The difference must be zero (an absolute check, 6.4).
- **Without the module:** payments are entered by hand as postings or, with Accounts receivable, as manual payments.
- **Start at a cut-off date** with the opening balance of the bank account.
- **No direct link to the bank in the first design.** A file import is enough for one user. A live bank connection needs an agreement with a provider and stores secrets.

#### Rules for optional modules

1. **No module depends on an optional module.** Accounts receivable and Banking also do not depend on each other. A customer payment that comes from a bank line reaches Accounts receivable through an event and the document register, not through an import.
2. **Optional means switched off, not absent.** With one migration chain (9.2) the tables always exist. A setting in `settings.json` switches the module on. When it is off, its menu entries are hidden and its event handlers are not registered.
3. **Switch on once, with a start date.** A module that is switched on starts at a cut-off date with its opening data. Switching it off again later is not supported: its rows are part of the books.
4. **The absolute checks of a module run only when it is on.** The checks in 6.4 between Accounting and a module that is off are skipped, and the report says so.

## 6. Design points for the own-data ledgers

### 6.1 Ledger rules (apply to stock and accounting)

1. **Append-only.** No update, no delete. A correction is a new row that reverses the old one.
2. **Every row names its source** (document and line) and carries two dates: the business date and the recorded time.
3. **Current state is a sum over the ledger,** never a stored number that someone can edit. If speed is a problem, add a derived table later and test it against the sum.
4. **The commercial record and the ledger are two things.** The invoice line is the commercial record (price, VAT). The ledger row is the effect (stock, money). They are written in one transaction and checked against each other.

### 6.2 Risk: two writes for one fact

Today one row (the line) is the only source. After step 2b the line and the ledger row can disagree if one write fails or code skips one. Controls: one function writes both; one transaction; a consistency check that runs in the tests and as an on-demand report.

### 6.3 Risk: the meaning of "invoice" changes

In Access an invoice is also an order and a delivery. In the new model these are three documents. Keep the old flow available (direct sale) so that daily work does not change on the day of the conversion.

### 6.4 Strict relations between modules (owner requirement, after version 2)

**Requirement:** every effect in one module can be traced back row by row to its cause in another module. A stock change that is reflected in accounting has at least as many rows in accounting as in stock. The same holds from sales to stock and from sales to accounting. Consistency checks can then be absolute, and the data is transparent.

Rules that follow from it:

1. **Row-level reference, always.** Each downstream row names exactly one upstream row (not null). The reference goes through the document register (6.5). A module can then point to a row of another module without importing that module. This matters for Stock: its rows point to sales lines, but Stock must not depend on Order / Invoices.
2. **One or more, never fewer.** One upstream row has one or more downstream rows. One sales line can have several stock rows (partial deliveries). One stock row has two or more accounting rows (debit and credit).
3. **No summary postings.** No "one posting per invoice" and no "one posting per day". A total is always a sum over rows, never a stored row of its own.
4. **Same transaction as the event.** The effect is written in the same transaction as the event that makes it due (a delivery is booked, an invoice is closed), or not at all. A draft has no effect yet. There is no moment at which the modules disagree about a booked row.
5. **Reversals mirror.** A reversal row upstream gets its own reversal rows downstream. Downstream rows are never edited to follow an upstream correction.
6. **Every row has a source.** A manual entry (a manual journal, a manual stock correction) is its own document with its own type. No row is without a source.

**Absolute checks** (zero tolerance, run in the tests and as an on-demand report):

- Every booked upstream row that must have an effect has at least one downstream row.
- Every downstream row points to an existing upstream row of the right type.
- Sales to stock: the stock rows of a sales line sum to its delivered quantity, exactly.
- Stock to accounting: the accounting rows of a stock row sum to its value, exactly. Debit equals credit for each source row, not only in total.
- Sales to accounting: the accounting rows of a sales line sum to its amounts (net, VAT), exactly.

What this requires:

- **Exact money.** "Exactly" is not possible with `REAL`. Amounts in the ledgers are integer minor units. Rounding happens once, per line, in one function. VAT is already computed per line (§5.1), which fits: a per-invoice VAT calculation would create a rounding row with no line as its source. Checked on the data (9.6): the change to exact amounts does not alter any of the 665 lines, if the rounding stays half-to-even. Unit cost prices need four decimals, so whole øre is right for amounts but not for unit costs.
- **A value on each stock row.** To post a stock change, the row needs a cost value at the moment it is written (a snapshot, like the price on an invoice line). The valuation method is left to the detailed design of Accounting in version 3 (M12).
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
- **Order of work.** The register must exist before the stock ledger takes its first reference (step 2b). Legacy invoices get their register entries in the same migration.
- **Open for the detailed design:**
  - how a row references a single *line* of a document (row-level tracing needs the line, not only the document);
  - which module creates the register entry (recommended: the owning module, through a Master data function);
  - whether a reversal is a new document or a new line in the same document;
  - whether legacy stock rows get a document (one per old batch) or stay without one (validate on write only);
  - when the visible number is set: at creation, as today, or at closing. Danish VAT rules ask for a sequential invoice number. A voided invoice keeps its number and stays as a flagged record, so the series can be explained. Confirm with the accountant.

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
| M2 | Module split after release 1 as step 2a, without data change, before the ledger change? | Yes for the code. **Changed in the second review:** no migration chain per module; keep the one chain (9.2). |
| M3 | UI folder after the split: keep all UI in `winedb/ui/<module>/` (current rule), or give each module its own `ui/` sub-package? | Keep the rule |
| M4 | Events: synchronous, same transaction, with notify and veto? | Yes, but only toward Accounting (9.4) |
| M5 | Which module owns `prices_cost` and `prices_sales`? | **Decided: Master data**, because Stock and Invoices both read them |
| M6 | Stock ledger: append-only with reversal rows, a movement type, a document reference and two dates? | Yes |
| M7 | Does stock leave at delivery (not at line save) once orders exist? | Yes. See M14 for the time before orders exist. |
| M8 | Legacy invoices after conversion: no invented orders; how do open invoices count? | **Decided:** no invented orders. **Changed:** open invoices have no known delivery or payment state. The migration treats them all as reserved. The owner goes through them after the migration (9.3). |
| M9 | Order of orders and accounting? | **Decided: orders first** (it changes the stock model). Accounting comes in version 3 and posts the final document chain. |
| M10 | Fix the document inconsistencies (3.4)? | **Done** |
| M11 | Structured stock count as step 2b.1, directly after the stock ledger? | Yes |
| M12 | Stock valuation for accounting (cost snapshot per row, moving average or FIFO). | **Deferred:** subject to the detailed design of Accounting (version 3). Not decided here. |
| M13 | Documents as global master data: one document register in Master data; number ranges are labels only (6.5)? | **Decided: yes** (owner requirement). Details in the version 2 design. |
| M14 | When is a stock row booked (9.3)? | **Decided:** when the transaction is closed, with a posting date. After version 2 the user enters the posting date; until then it is the closing date. A draft ledger is an option for the version 2 design. To confirm: open legacy invoices then count as reserved, not as delivered. |
| M15 | Additions in release 1, outside strict 1:1 (9.5)? | **Decided: yes.** A type field on the stock change screen, a recorded time on new rows, and the closing time of an invoice. |
| M16 | Accounts receivable: how much detail does an open item carry (3b)? | **Principle decided (owner):** no information is lost. Detail the AR row does not carry is tracked in the general ledger. Closing an AR record counterposts the financial record exactly. A fully closed record sums to zero on every dimension except those that differ on purpose (such as the posting date). **Open:** the detail level of the AR row, for the detailed design. |
| M17 | Version 3: Accounting, with Accounts receivable and Banking as optional modules (switched on once, with a start date)? | **Decided: yes** (owner requirement). |

## 9. Second review of the decisions (2026-11-15)

All decisions and recommendations were checked again, against the data export and the repository settings. Result: the direction is sound. One recommendation is withdrawn, one new decision is needed, and some statements in this document were wrong and are corrected.

### 9.1 Verdict for each decision

| Decision | Verdict | Remark |
|---|---|---|
| M1 Release 1 near 1:1, modules later | Good | The module split moves code, not data. Doing it later costs little if the rules in section 4 hold. |
| M2 Module split as step 2a | Good in part | The code split is good. The migration chain per module is withdrawn (9.2). |
| M3 UI stays in `winedb/ui` | Good | No conflict with any later decision. |
| M4 Events | Good, but narrower | Needed only toward Accounting (9.4). |
| M5 Price lists in Master data | Good | |
| M6 Append-only stock ledger | Good, with two additions | The reference goes through the document register. Each row needs two dates. |
| M7 Stock leaves at delivery | Good | The same question exists already in step 2b (M14). |
| M8 No invented orders for old invoices | Good | It keeps on-hand identical and invents no history. |
| M9 Orders before Accounting | Good, and now necessary | The strict relations need the final document chain first. |
| M11 Structured stock count | Good, one gap closed | It needs the business date, and a rule for entries dated before a booked count. |
| M12 Valuation deferred | Correct to defer | Two inputs are noted for it: unit costs have four decimals, and purchases have no document yet. |
| M13 Document register | Good. The strongest decision | It solves a problem this review had missed: a stock row must point to a sales line, but Stock must not depend on Order / Invoices. |
| Strict relations (6.4) | Good | Two rules were worded wrongly and are corrected (9.7). |

### 9.2 Withdrawn: one migration chain per module

The earlier versions advised a `schema_migrations` table and one chain per module. This is withdrawn. Reasons:

- With strict relations and a global document register, a schema change often touches more than one module. The backfill of the stock ledger reads invoice tables and writes stock rows.
- Chains per module run in module order. One chain runs in the order of writing. For a change that touches two modules, the two orders can differ. A new database is then built in another order than an upgraded one. This is a known source of errors that only a dependency solver removes, and section 7 says not to build one.
- The gain of a chain per module is a module that is installed or left out per user. Here one program holds all modules for one user.

Keep the one numbered chain and `user_version`. A module is then a border in the code and an owner of tables, not a separate schema. "Module not active" means the menu entry is hidden, or the function has not started (Accounting before its cut-off date). The tables always exist.

### 9.3 Decided: a stock row is booked when the transaction is closed (M14)

Step 2b first said: each save of an invoice line writes a stock row, and each edit writes a reversal row and a new row. This copies the Access behaviour, but each change to a draft would leave two rows in the ledger for ever, and later cause accounting rows for a document that is not final.

**Decision (owner):**

- A stock row is booked when the transaction is closed, not at each save of a draft line.
- Each booked row has a **posting date.** After version 2 the user enters it. Until then the posting date is the closing date.
- Lines on an open invoice are drafts. They count as **reserved**. The screen shows on hand, reserved and available. The old on-hand figure equals the new *available* figure, and the golden test compares these two.
- A reopen of a closed invoice writes reversal rows. This is a real event and it is rare.

**What it needs: a closing date.** Access does not store one. The invoice table has a closed flag and an invoice date only.

- Release 1 records the closing time when an invoice is closed (a third additive column, see M15). Every invoice closed in the new program then has an exact closing date.
- For invoices closed in Access, the posting date is an estimate: the later of the invoice date and the creation time of the last line. In the old export these two differ by more than 7 days for 9 of the 129 closed invoices, and 1 closed invoice has no invoice date.

**Option for the version 2 design: a draft ledger.** Draft lines could be written to a parallel ledger, which is posted to the real ledger at closing. To be weighed against the complexity at that time.

- Gain: reserved stock and a preview of the posting come from the same kind of rows as the real ledger.
- Cost: a draft is edited freely. The parallel ledger is then either not append-only or full of reversal rows. Each draft line also exists twice: the line and its draft row.
- A lighter variant gives the same preview: compute the draft rows on request, with the same function that later writes the real rows, and store nothing.

**Open invoices have no known state (owner, 2026-11-15).** The current design does not follow delivery or payment. This was a choice for simplicity. An open invoice can be reserved only, delivered but not paid, or paid but not delivered. The data can not tell which. So M8 must not say "delivered" for open legacy invoices: that would invent a fact.

Consequences:

- **Three states, three owners.** Delivery, invoicing and payment are independent states. Delivery belongs to Order / Invoices (step 2c). Payment belongs to Accounts receivable (version 3, optional). An invoice is not "done" until all three are settled. The version 2 design must keep them apart and not fold them into one "closed" flag.
- **Decided: the migration treats every open invoice as reserved.** No review is needed before the migration, and it needs no input. Available stock is the same as the old on-hand figure, so nothing visible changes. On hand is higher by the reserved quantity (old copy: 75 lines, 335 bottles, 9 open invoices).
- **The owner goes through the open invoices after the migration,** with the normal functions: close an invoice (it is then posted with its posting date), or leave it open. There will be few (14 in the old copy).
- **Release 1 does not add delivery or payment fields.** It stays 1:1 here. The closing time (M15) is enough to post closed invoices later.

### 9.4 Narrowed: the event bus

An event is needed only where the module that causes an effect may not import the module that records it. That is the case toward Accounting. Order / Invoices depends on Stock and calls it directly. A direct call is easier to read and to debug than an event. Keep the list of events as short as possible.

### 9.5 Gaps found

1. **Two dates.** The model has one date per row (`created_at`). A ledger needs the business date and the recorded time. Without both, "stock at the count date" and later the accounting period can not be right.
2. **Purchases have no document.** A purchase is a stock row with a comment. Accounting can not post it without a supplier and a cost. A purchase receipt document and suppliers as master data must come before Accounting.
3. **The cut-off needs a full count** and no negative stock.
4. **Release 1 collects data that can not be rebuilt (M15, decided).** The cause of each stock movement is free text today. The classification in step 2b must read these comments by hand, and the work grows with each month of use. Three additive columns in release 1 stop this growth. All are outside strict 1:1, all leave the Access behaviour unchanged, and all are empty on rows from Access:
   - `movement_type` on stock changes, picked on the stock change screen (purchase, count, transfer, write-off, sample, other);
   - `recorded_at` on stock changes, invoices and invoice lines: the time the program wrote the row, never edited;
   - `closed_at` on invoices: the time the invoice was closed (needed for M14).
5. **The export is old (confirmed by the owner).** Its last stock row and its last invoice are from January 2015. The live Access file is newer. All counts and data facts in this document and in the design document come from the old copy. Before release 1: take a current copy, run the import with its audit on it, and repeat the checks in 9.6 and the review of the comments. The import and the audit do not depend on the old numbers.

### 9.6 Checked on the data (old copy)

These results hold for the export that ends in January 2015. Repeat them on a current copy (9.5, item 5). The rounding result depends on two facts that newer data can break: all VAT rates are 0 or 25 %, and all sales prices have two decimals.

- **Rounding is safe.** All unit sales prices have two decimals, and the VAT rates are 0 and 25 %. All 665 lines give the same sales amounts (with and without VAT) with the current rule, with exact half-to-even and with exact half-up.
- **Cost amounts need half-to-even.** 183 lines have a unit cost with more than two decimals. Exact half-to-even reproduces all cost totals. Half-up differs on 2 lines. So the exact money type must round half-to-even, and unit costs need four decimals.
- **Negative stock.** The causes are mixed (3.3). The earlier text guessed one cause. That guess is removed.

### 9.7 Statements corrected in this document

- The table in section 5 gave Accounting no dependency on Stock. It has one: stock changes are posted.
- Section 5 said that orders (2c) and accounting are independent. They are not (M9). Accounting is now version 3.
- 6.4 rule 1 said that the reference follows the dependency direction of the modules. For sales to stock it does not. The document register solves this.
- 6.4 rule 4 said that a row and its effect are always written together. Correct is: together with the event that makes the effect due. A draft has no effect.
- Step 2b used `source_type` and `source_id`. With the document register the reference is a document and a line.
- Step 2b.1 said that on-hand equals the counted quantity after booking. Correct is: on-hand at the count date.
- Step 2c proposed to rename columns. Withdrawn: risk without function.
