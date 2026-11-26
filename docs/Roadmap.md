# Roadmap

This page shows the plan on one page: what each version contains, in which order, and the status. The details are in the documents that each section links to.

| Version | Goal | Status |
|---|---|---|
| **1** | Replace the Access app. Copy its functions and data with minimal change. | In progress: step 11 of 11 |
| **1.x** | The Access functions that are not in version 1 (backlog). | Not started |
| **2** | Modules, a real stock ledger, stock count, orders and deliveries. | Designed, not started |
| **3** | Accounting, with accounts receivable and banking as optional modules. | Outline only |

## Version 1: replace the Access app

**Goal:** the user stops using Access. The new app does the daily work that the Access app did, with the same data and the same calculations. The data is copied 1:1 from Access, once.

**Scope:** the main menu, the stock change screen and the invoice screens (header and lines, including closing an invoice). Details: [design doc §1 and §8](Vinlager_Python_SQLite_Design.md), status per function: [Functionality.md](Functionality.md).

### Steps

| Step | Content | Status |
|---|---|---|
| 1 | Skeleton: repo, tests, configuration | Done |
| 2 | Database created on first start, numbered schema migrations | Done |
| 3 | One-time import from Access, checked against the source | Done |
| 4 | Line amounts and on-hand stock, golden tests on the real data | Done |
| 5 | Main menu with the list of open invoices | Done |
| 6 | Stock change screen (the fields of the Access form) and mass stock registration (the Access "Import vinlager tilgange/afgange" grid) | Done |
| 7 | Invoice header screen (create, edit, delete flag, close) | Done |
| 8 | Invoice lines screen | Done |
| 9 | Invoice preview and PDF (replaces the Access report `rFaktura`) | Done |
| 10 | Master data screens (wines with prices, customers, warehouses) and reopen invoice | Done |
| 11 | End-to-end test and parallel run with Access | Tools done: end-to-end test and parallel run check. **Open: your parallel run** ([Parallel_Run.md](Parallel_Run.md)) |
| Release | Import the **live** Access file (the test data ends in January 2015), repeat the checks, rehearse on a copy ([Branching_Strategy.md §6](Branching_Strategy.md)) | Not started |

### Differences from Access in version 1

Version 1 copies Access, but not exactly. Each difference below is either decided or open. **Open items need your decision.**

| # | Difference | Why | Status |
|---|---|---|---|
| 1 | The UI is in British English, not Danish. The data stays as it is. | Your decision | Done |
| 2 | Settings are in `settings.json`, not in a table. All user data (database, settings, logo, by default the invoice PDFs) is in the `data` folder next to the program. | Configuration is not business data; owner decisions 2026-11-21 and 2026-11-26 | Done |
| 3 | The open-invoice list also shows invoices without a customer, as "(no customer)". Access hid them. | So these drafts can be finished or deleted | Done (default of decision 2) |
| 4 | Stock leaves out the lines of soft-deleted invoices. Access counted them. | Your rule: calculations leave out flagged rows. No effect on the current data. | Done |
| 5 | A new invoice must have a customer. Access allowed customer 0. | Prevents new drafts without a customer | Done |
| 6 | The invoice date is filled in with today. Access left it blank. | Default of decision 3 | Done |
| 7 | Inputs are checked when saved (for example: the quantity must be a whole number other than 0). Old rows are never checked. | Prevents new bad data | In step 6 |
| 8 | The stock change picker hides discontinued wines whose total stock is 0, and marks the others "(discontinued)". Access listed all wines. | Fewer wrong picks; stock on a discontinued wine can still be corrected | Done (owner decision) |
| 9 | Mass stock registration also accepts the wine code, not only the wine id. | Users know the code better | Done (owner decision) |
| 10 | A wrong invoice line is cancelled (quantity 0, status flag, not printed). Access deleted the line. | Rows are never deleted | Done (owner decision 16) |
| 11 | The invoice PDF prints the lines of each wine house in the order they were entered. Access had no order there, so its order looked random. | A fixed order that the user can follow | Done |
| 12 | "Create PDF" asks before it replaces a PDF that exists. Access replaced it without asking. | Your decision (decision 12) | Done |
| 13 | The invoice PDF prints the full wine house name. Access cut long names, for example "St. Martin de la Garr". | Nothing is gained by cutting the name | Done |
| 14 | An invoice whose customer has no name still gets a PDF. Access stopped without a message. | The user gets the PDF | Done |
| 15 | The sales and cost prices are maintained on the wine screen, for the selected wine. Access had two separate price list forms. | A new wine gets its prices in one place | Done |
| 16 | A closed invoice is reopened with a button on its Invoice screen. Access had a separate form with a list. | Your decision; the reverse of Close | Done |

**Rule for version 1 (owner, 2026-11-21): keep data transformations to a minimum.** The data is loaded 1:1 and the schema does not change after `001_init.sql`. The screens store only the fields that the Access forms stored. So these planned additions **moved to version 2**:

**One exception (owner, 2026-11-25):** the flag `invoice_lines.is_deleted` (migration `002`, decision 16). A wrong invoice line is cancelled: quantity 0, the flag set, never printed. It does not change the 1:1 import: the import still loads into schema version 1, and the program upgrades the file.

- **Type of change** on each stock movement (purchase, count, transfer, write-off, sample, other). In version 1 the cause stays in the free-text comment, as in Access.
- **Recorded at:** the time when the program wrote a stock movement, an invoice or an invoice line.
- **Closing time** of an invoice.
- The three **invoice texts** (address, bank details, payment terms) copied onto each invoice.

The effect: in step 2b, the mapping from comment to type of change must also cover the stock movements entered with version 1.

**Invoice PDF:** in version 1, step 9 (owner decision, 2026-11-21). In Access, the invoice report (`rFaktura`) is part of the daily work. The printed invoice keeps the Danish labels of Access (owner decision 17, 2026-11-25); the screens stay in English.

## Version 1.x: the rest of the Access functions

The Access functions that are not in version 1, in about this order of priority ([design doc §9](Vinlager_Python_SQLite_Design.md)):

1. Copy an invoice
2. Mailing list export
3. Settings screen
4. Stock report and customer list
5. Excel export
6. Consistency check query

The stock import (mass registration) moved into version 1, step 6, the invoice PDF into step 9, and the master data screens and reopening an invoice into step 10 (owner, 2026-11-25: simple editing of the lists is needed for the app to work; a dedicated master data module comes later).

## Version 2: modules and a real stock ledger

**Goal:** the app becomes modular, and stock becomes a ledger of its own instead of a calculation over two tables. Details: [Design_Evaluation.md §5](Design_Evaluation.md).

| Step | Content |
|---|---|
| 2a | Module skeleton: move the code into modules (master data, stock, order / invoices). No change to the data. Retire or adapt the Access import before the first new schema migration. |
| 2b, first | The additions moved from version 1: type of change, recorded-at time, closing time of an invoice, invoice texts on each invoice. |
| 2b | Stock ledger: every stock change is a row with a type and a source. Closed invoices book their stock rows. On-hand = the sum of the ledger. |
| 2b.1 | Structured stock count: count a warehouse, type the counted quantities, book the differences in one step. |
| 2c | Orders, deliveries and partial deliveries. Stock leaves at delivery. On hand, reserved and available stock. |

## Version 3: accounting

**Goal:** bookkeeping in the app, posted from the stock and invoice documents. Details: [Design_Evaluation.md §5, version 3](Design_Evaluation.md).

| Step | Content |
|---|---|
| 3a | Accounting (general ledger). Check the Danish bookkeeping rules with the accountant first. |
| 3b | Accounts receivable (optional): what each customer owes, payments, overdue invoices. |
| 3c | Banking (optional): bank statement import, match and post, bank reconciliation. |
