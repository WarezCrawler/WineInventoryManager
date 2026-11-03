# Functionality

The main functions of the app as a list, kept short. Details and rules are in [Vinlager_Python_SQLite_Design.md](Vinlager_Python_SQLite_Design.md) (section numbers in brackets).

Rows are never deleted. Where a delete function exists (today only invoices) it is a soft delete (flagged).

Status: **Done** = built, **v1** = planned for the first release, **Later** = backlog (after v1).

## 1. Main menu (§6.1)
- 1.1 List of open invoices (newest first) with invoice no., customer no. and customer name: **v1**
- 1.2 Open invoice lines for the selected invoice: **v1**
- 1.3 Open invoice header for the selected invoice, or create a new one: **v1**
- 1.4 Open stock adjustment: **v1**
- 1.5 Open customer list: **Later**
- 1.6 Open current stock report: **Later**
- 1.7 Buttons for the Later functions shown disabled: **v1**
- 1.8 Quit: **v1**

## 2. Stock adjustment (§6.2, §5.3)
- 2.1 Add or remove stock for a wine and warehouse (signed quantity, comment, date): **v1**
- 2.2 Show current stock and stock after the change, and the latest movements: **v1**
- 2.3 Import new stock from a file: **Later**

## 3. Manage open invoices
- 3.1 Create an invoice and edit its header: **v1** (§6.3)
- 3.2 Add and edit invoice lines with live price, VAT and discount calculation: **v1** (§5.1, §6.4)
- 3.3 Close an invoice (it becomes read-only): **v1**
- 3.4 Soft delete an invoice (flagged, never removed): **v1**

## 4. Closed invoices
- 4.1 Reopen a closed invoice: **Later**
- 4.2 Copy an invoice (new customer, today's date): **Later**
- 4.3 Preview an invoice on screen (layout need not match the PDF): **Later**
- 4.4 Create the invoice PDF directly, without a print step, saved to the PDF folder: **Later**

## 5. Customers
- 5.1 Browse the customer table: **Done** (table browser)
- 5.2 Maintain customers: **Later**
- 5.3 Customer list report: **Later**
- 5.4 Mailing list export: **Later**

## 6. Wines, prices and warehouses
- 6.1 Browse the tables (wines, prices, warehouses, settings): **Done** (table browser)
- 6.2 Maintain the wine list: **Later**
- 6.3 Maintain sales and cost prices: **Later**
- 6.4 Price lists (sales, cost): **Later**
- 6.5 Maintain warehouses: **Later**

## 7. Reports
- 7.1 Current stock report, including negative stock: **Later**
- 7.2 Export to Excel: **Later**

## 8. Settings
- 8.1 View and edit settings, including the PDF save folder: **Later**

## 9. Database and migration
- 9.1 The database file is created on first start, and upgraded by numbered migrations with a backup first: **Done**
- 9.2 One-time load of the Access CSV export, loaded as-is: **Done** (`python -m migrate.load_csv`)
- 9.3 Independent audit report of the load (PASS / FAIL / REVIEW, summary mode without row-level data): **Done**
- 9.4 "Import from Access database" button in the app: placeholder, **v1** (calls the loader)

## 10. Program
- 10.1 Table browser: lists the tables and shows their rows: **Done**
- 10.2 Runs as a Windows program (`build.ps1`, own window): **Done**
- 10.3 Backup routine and logins: **Later**
