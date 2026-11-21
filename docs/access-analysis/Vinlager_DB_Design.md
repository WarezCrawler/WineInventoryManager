# Vinlager DB – Design Document

This document describes the existing Access app: its tables, queries, forms, code and workflows, and the risks found in it. It is the starting point for the rebuild. The decided plan for the new app is in [Vinlager_Python_Rebuild_Plan.md](Vinlager_Python_Rebuild_Plan.md).

- **Source:** `Vinlager DB_vMaster.accdb` (Access 2010 or later format, last saved 2015-03-07).
- **Language of the tables, columns and UI:** Danish.

> **How this document was made:** Access (and its database engine, ACE) was not installed on this machine, so a pure-Python parser read the file.
> The parser recovered these items reliably: the table structures, the data, the SQL of the saved queries, the macro XML and some text fragments of the VBA code.
> **Not recovered:** the layouts of forms and reports, the full VBA source, the details of the relationships (enforced integrity, cascade rules), and the validation rules and defaults of the fields.
> Items marked *(inferred)* come from column names, query SQL or data, not from the object definition itself.

## 1. Purpose

The app is a small stock and invoicing system for the wine trading business **Vinotrentino I/S**. It records:

- a wine catalogue (about 228 wines, mainly from 4 countries: FR, IT, DE and ES),
- stock received into one of three warehouses (`tLagre`),
- customers (about 176),
- invoices (about 143, of which 129 are closed) with sale lines (665 lines from 2013-06-30 to 2015-03-07, about 326,600 DKK without VAT),
- cost and sales price lists for each wine,
- invoices as PDF files.

It is a desktop Access app for one user. The forms and the data are in the same file.

## 2. Data model

### 2.1 Tables

| Table | Rows | Purpose |
|---|---|---|
| `tVinliste` | 228 | Wine master data. Primary key `Vin_ID`. Name, vintage (`Vin_Årgang`), drink-by year (`Vin_Udløb`), year when the wine is mature (`Vin_Moden`), country, house, region, type (Rød/Hvid/Rosé/Mousserende/Dessert), size (`Vin_Str`: Alm/Halv/MGM/DMGM), `Vin_UID` (short code, for example `SAbSe_RA10`), and the flags `Udgået` (discontinued) and `Private`. |
| `tKunder` | 176 | Customers. Primary key `Kunde_ID`. Name parts, address, phone, email, and the flags `Skjul` (hidden) and `Maillist`. |
| `tLagre` | 3 | Warehouses (stock locations), for example "Vinotrentino" and "<owner> Privat". |
| `tFaktura` | 143 | Invoice header. Primary key `Fakt_ID`, and `Kunde_ID`, `Lager_ID`, `FakturaDato`, `Lukket` (closed), `Delete` (soft delete), `HideSubTotals` and `Kommentar`. |
| `tVinlager` | 863 | Stock **receipts and adjustments**: a dated `Quantity` added to a warehouse (`Lager_ID`). |
| `tVinlager_Salg` | 665 | Invoice **sale lines**: quantity, unit price, line total with and without VAT, a copy of the cost price, VAT rate, discount (`Rabat`) and price type. Links to `Fakt_ID`, `Vin_ID` and `Lager_ID`. |
| `tPrisliste_Cost` | 240 | Purchase price for each wine and `PrisType` (mostly "Standard"). |
| `tPrisliste_Salg` | 442 | Sales prices for each wine and `PrisType` (`0P`, `Alm`, `Tilbud`, `EP`, `Rabat`), with `Momssats` (0.25). |
| `tSettings` | 4 | Key/value settings used on invoices: `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>` and `<fakt_savelocation>` (the folder for the PDF files). |
| `USysApplicationLog` | 3 | Error log of Access data macros (2013; `EditRecord` failures in `tKunder.AfterUpdate`). |
| `MSys*`, `f_…_Data` | – | Access system tables. `Kontortema.thmx` is the embedded Office theme. |

### 2.2 Relationships (from column names and query joins)

```
tKunder 1──< tFaktura >──1 tLagre
                 1
                 │
                 ^
           tVinlager_Salg >──1 tVinliste 1──< tVinlager >──1 tLagre
                                  1
                       ┌──────────┴──────────┐
                       ^                     ^
                tPrisliste_Cost       tPrisliste_Salg
```

- `tFaktura.Kunde_ID → tKunder`, `tFaktura.Lager_ID → tLagre`
- `tVinlager_Salg.Fakt_ID → tFaktura`, `.Vin_ID → tVinliste`, `.Lager_ID → tLagre`
- `tVinlager.Vin_ID → tVinliste`, `.Lager_ID → tLagre`
- `tPrisliste_Cost.Vin_ID` and `tPrisliste_Salg.Vin_ID → tVinliste`

The database catalog stores only one relationship that could be identified: `tVinliste ↔ tPrisliste_Cost`. Query joins and combo boxes use the other relationships, but constraints do not necessarily enforce them.

### 2.3 Important design points

- **Stock is calculated, not stored:** on-hand stock = Σ `tVinlager.Quantity` − Σ `tVinlager_Salg.Quantity`. The union query `uVinlager` combines both tables. `uVinlager_Excel` is a variant of it, and a consistency check compares the totals.
- **Prices are copied onto each sale line:** a sale line copies the sales price, cost price and VAT rate at the time of sale, so later changes to the price lists do not change history. The totals (`SamletPris`, `SamletPris_mMoms`, `SamletCostPris`) are **stored, not calculated**. This duplicates data, and the stored totals can become different from the calculated ones.
- **Rows are hidden, not removed:** the flags `Udgået`, `Skjul`, `Delete` and `Lukket` hide rows.
- **Price types are free text** in both price lists, with case variants: `alm`/`Alm`, `standard`/`Standard`, `rød`/`Rød`.
- **Settings are key/value pairs** with angle-bracket placeholders (`<fakt_adr>`). The invoice reports probably replace these placeholders with the values.

## 3. Queries

| Query | Kind | Role |
|---|---|---|
| `qVinliste` | Select | Active wines (`Udgået<>True`, sorted by name and vintage). Source of the combo boxes. |
| `qVinliste_Vedligehold` | Select | Wine list for the maintenance form. |
| `qVinlager_Salg` | Select | Joins sale lines, invoices, customers, wines and warehouses. It is the source of `rFaktura`, leaves out `Delete=True`, and formats dates as `yyyy/mm/dd`. |
| `qVinlager_Change`, `qVinlager_Change_Import` | Select / Append *(inferred)* | Stock change entry, and import of many stock changes at once. |
| `uVinlager`, `uVinlager_Excel` | Union | Receipts and sales in one list, for the stock calculation and the Excel export. |
| `qVinliste` combo boxes and price lookups | Select | Show only wines with `Udgået<>True AND Private<>True`. The price combo boxes read `[Forms]![fVinlager_Salg]![Vin_ID]` (queries with a form parameter). |
| Invoice combo boxes | Select | Open invoices (`Lukket<>True`) and closed invoices, each joined to the customer name. |

Queries marked *(inferred)* could not be read in full; only their names and fragments were recovered.

## 4. Forms (UI)

| Form | Purpose |
|---|---|
| `fNavigation` | Main menu. It opens an existing or new invoice (combo box `cboFaktura`), and has buttons for customers, wine list, stock, sales prices, mail list and settings. Its UI macros work like this: if the user selected an invoice, they open `fFaktura` and `fVinlager_Salg` filtered to that invoice; if not, they open `fFaktura` to add a new invoice. |
| `fFaktura` | Invoice header (customer, warehouse, date, comment, closed flag). |
| `fFaktura_CopyExisting` | Copies an existing invoice to a new one (see §5). |
| `fFaktura_genåben` | Reopens a closed invoice. |
| `fVinlager_Salg` | Entry of invoice lines (wine, price type, price, quantity, discount; combo boxes `cboSalgsPris` and `cboCostPris`). |
| `fVinlager_Change` | Adds stock receipts and adjustments. |
| `fVinliste_Vedligehold` | Maintenance of the wine catalogue. |
| `fKunder`, `fKunder_Mailliste` | Customer maintenance and the mailing list. |
| `fPrisliste_Cost`, `fPrisliste_Salg` | Maintenance of the price lists. |
| `fLagre` | Maintenance of the warehouses. |
| `fSettings` | Edits `tSettings`. |

## 5. Reports and code

**Reports:**
- `rFaktura`: the invoice. Its source is `qVinlager_Salg`, and it has a *Hide Sub Totals* option.
- `rKundeListe`: the customer list.
- `rVinliste`: the wine list.

**Modules:**
- `DBCopyFakt`: copies an invoice. It creates a new `tFaktura` row for a selected customer, copies `Lukket`, `Lager_ID` and `HideSubTotals`, and sets the comment "Oprettet som kopi af faktura N". Then it copies the sale lines of the invoice.
- `DBFunctionsA`: helper functions. The recovered fragments show two of them:
  - the **mail list builder**: `SELECT Mailadr FROM tKunder WHERE Maillist = True and Skjul <> True and Mailadr <> ''`
  - the **PDF export**: `DoCmd.OutputTo acOutputReport, …, acFormatPDF`, saved to `<fakt_savelocation>`.
- `Development`: a scratch and utility module for the developer.

**Macros:**
- `Autoexec` runs at startup and probably opens `fNavigation`.
- `~TMPCLPMacro` is a temporary clipboard macro.
- Embedded UI macros on the buttons of `fNavigation`.
- A data macro on `tKunder` (After Update). It failed two times in 2013 (`EditRecord failed…`, error −20335).

## 6. Main workflows

1. **Receive stock:** in `fVinlager_Change`, the user adds a row to `tVinlager`.
2. **Invoice a sale:**
   1. In `fNavigation`, the user opens a new or existing invoice (`fFaktura`).
   2. In `fVinlager_Salg`, the user adds lines. The price comes from `tPrisliste_Salg` and the cost from `tPrisliste_Cost`; the line stores a copy of both.
   3. The user closes the invoice (`Lukket`).
   4. The user prints `rFaktura` to a PDF file in the configured folder.
3. **Reopen or copy an invoice:** `fFaktura_genåben`, and `fFaktura_CopyExisting` (`DBCopyFakt`).
4. **Maintain master data:** wines, customers, warehouses, both price lists and settings, each with its own form.
5. **Mailing list and exports:** `fKunder_Mailliste` and `uVinlager_Excel`.

## 7. Risks and candidates for clean-up

- **Personal data in the file:** customer names, addresses, phone numbers and email addresses, and bank and registration data in `tSettings`. Treat the file as sensitive, and do not commit it to a public repo.
- **Hard-coded path:** `<fakt_savelocation>` points to the Dropbox folder of one user (`C:\Users\<user>\Dropbox\…`). The PDF export fails on all other machines.
- **Stored totals** (`SamletPris*`) can be different from quantity × price − discount. The invoice query adds `Rabat` to the total with VAT; check this.
- **Free-text lookup values** (`PrisType`, `Vin_Type`, `Vin_Str`, `Vin_Land`) have case variants and wrong values: `Vin_Land` contains "Vinkasse 6 hvid", "Vinsmagning" and "DK", because products that are not wine are stored as wines. Use lookup tables.
- **Stock is only arithmetic** over two tables. There is no uniqueness check and no check against negative stock, and no stock check per invoice was found.
- **Each table has its own soft-delete flag,** with a different meaning: `Delete`, `Skjul` and `Udgået`.
- **One file for everything:** the data and the UI share one `.accdb`. Front end and back end are not split, so use by more than one user, or an upgrade, can corrupt or overwrite data.
- **Old or temporary objects:** `~TMPCLPMacro`, the internal query objects `~sq_*`, an old reference to `tPrisliste` in a saved row source, and the column `test_slet` ("test/delete") in `tPrisliste_Cost`.
- **Broken data macro:** the error log shows that `tKunder.AfterUpdate` failed in 2013.

> **Update:** the decided plan is in [Vinlager_Python_Rebuild_Plan.md](Vinlager_Python_Rebuild_Plan.md): SQLite, all logic in Python, self-contained, no Access, Power BI for analytics, and a one-time migration tool. More findings and the runbook for the Access export are in [Vinlager_Decompilation_Handoff.md](Vinlager_Decompilation_Handoff.md). The section below is the original outline; the plan replaces it.

## 8. Suggested migration path (original outline, replaced)

1. Open the file once in Access. Export the full schema, relationships, forms and VBA (with the Database Documenter or `Application.SaveAsText`), and confirm the *(inferred)* items above.
2. Move the data to a SQL database (SQLite, SQL Server or Postgres), with foreign keys on the relationships in §2.2 and lookup tables for price types, wine types, sizes and countries.
3. Replace the stored totals with calculated columns or views, and keep the copied prices.
4. Rebuild the invoice workflow and the PDF output, with an output folder that the user can configure.
