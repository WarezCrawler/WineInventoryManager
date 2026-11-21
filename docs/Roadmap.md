# Roadmap

This page shows the plan on one page: what each version contains, in which order, and the status. The details are in the documents that each section links to.

| Version | Goal | Status |
|---|---|---|
| **1** | Replace the Access app. Copy its functions and data with minimal change. | In progress: step 6 of 9 |
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
| 6 | Stock change screen (the fields of the Access form) and mass stock registration (the Access "Import vinlager tilgange/afgange" grid) | In progress |
| 7 | Invoice header screen (create, edit, delete flag, close) | Not started |
| 8 | Invoice lines screen | Not started |
| 9 | End-to-end test and parallel run with Access | Not started |
| Release | Import the **live** Access file (the test data ends in January 2015), repeat the checks, rehearse on a copy ([Branching_Strategy.md §6](Branching_Strategy.md)) | Not started |

### Differences from Access in version 1

Version 1 copies Access, but not exactly. Each difference below is either decided or open. **Open items need your decision.**

| # | Difference | Why | Status |
|---|---|---|---|
| 1 | The UI is in British English, not Danish. The data stays as it is. | Your decision | Done |
| 2 | Settings are in `settings.json`, not in a table. | Configuration is not business data | Done |
| 3 | The open-invoice list also shows invoices without a customer, as "(no customer)". Access hid them. | So these drafts can be finished or deleted | Done (default of decision 2) |
| 4 | Stock leaves out the lines of soft-deleted invoices. Access counted them. | Your rule: calculations leave out flagged rows. No effect on the current data. | Done |
| 5 | A new invoice must have a customer. Access allowed customer 0. | Prevents new drafts without a customer | Planned, step 7 |
| 6 | The invoice date is filled in with today. Access left it blank. | Default of decision 3 | Planned, step 7 |
| 7 | Inputs are checked when saved (for example: the quantity must be a whole number other than 0). Old rows are never checked. | Prevents new bad data | In step 6 |
**Rule for version 1 (owner, 2026-11-21): keep data transformations to a minimum.** The data is loaded 1:1 and the schema does not change after `001_init.sql`. The screens store only the fields that the Access forms stored. So these planned additions **moved to version 2**:

- **Type of change** on each stock movement (purchase, count, transfer, write-off, sample, other). In version 1 the cause stays in the free-text comment, as in Access.
- **Recorded at:** the time when the program wrote a stock movement, an invoice or an invoice line.
- **Closing time** of an invoice.
- The three **invoice texts** (address, bank details, payment terms) copied onto each invoice.

The effect: in step 2b, the mapping from comment to type of change must also cover the stock movements entered with version 1.

**Note:** version 1 has **no invoice PDF and no printing.** In Access, the invoice report (`rFaktura`) is part of the daily work. Decide whether version 1 can go live without it, or whether the invoice PDF moves into version 1.

## Version 1.x: the rest of the Access functions

The Access functions that are not in version 1, in about this order of priority ([design doc §9](Vinlager_Python_SQLite_Design.md)):

1. Invoice PDF
2. Reopen a closed invoice
3. Copy an invoice
4. Customer maintenance and mailing list export
5. Wine list maintenance
6. Sales and cost price lists
7. Warehouse master data
8. Settings screen
9. Stock report and customer list
10. Excel export
11. Consistency check query

The stock import (mass registration) moved into version 1, step 6.

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
