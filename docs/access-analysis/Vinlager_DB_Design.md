# Vinlager DB – Design Document

Source: `Vinlager DB_vMaster.accdb` (Access 2010+ format, last saved 2015-03-07).
Language of the schema/UI: Danish.

> **How this was produced:** Access/ACE is not installed on this machine, so the file was read with a pure-Python parser.
> Table structures, data, saved-query SQL, macro XML and some VBA string fragments were recovered reliably.
> **Not recovered:** form/report layouts, full VBA source, relationship-diagram details (enforced integrity, cascade rules), field validation rules and defaults.
> Anything marked *(inferred)* comes from column names, query SQL or data, not from the object definition itself.

## 1. Purpose

A small wine-trading stock and invoicing system for **Vinotrentino I/S**. It tracks:

- a wine catalogue (~228 wines, 4 countries mainly: FR, IT, DE, ES),
- stock received into one of three warehouses (`tLagre`),
- customers (~176),
- invoices (~143, 129 closed) with sale lines (665 lines, 2013-06-30 → 2015-03-07, ≈ 326.6k DKK ex. VAT),
- cost and sale price lists per wine, and
- PDF invoice output.

Single-user desktop Access app (front end and data in one file).

## 2. Data model

### 2.1 Tables

| Table | Rows | Purpose |
|---|---|---|
| `tVinliste` | 228 | Wine master. `Vin_ID` PK. Name, vintage (`Vin_Årgang`), drink-by (`Vin_Udløb`), mature (`Vin_Moden`), country, house, region, type (Rød/Hvid/Rosé/Mousserende/Dessert), size (`Vin_Str`: Alm/Halv/MGM/DMGM), `Vin_UID` (short code, e.g. `SAbSe_RA10`), flags `Udgået` (discontinued) and `Private`. |
| `tKunder` | 176 | Customers. `Kunde_ID` PK. Name parts, address, phone, email, flags `Skjul` (hidden) and `Maillist`. |
| `tLagre` | 3 | Warehouses/stock locations (e.g. "Vinotrentino", "<owner> Privat"). |
| `tFaktura` | 143 | Invoice header. `Fakt_ID` PK, `Kunde_ID`, `Lager_ID`, `FakturaDato`, `Lukket` (closed), `Delete` (soft delete), `HideSubTotals`, `Kommentar`. |
| `tVinlager` | 863 | Stock **receipts/adjustments** (`Quantity` added to `Lager_ID`, dated). |
| `tVinlager_Salg` | 665 | Invoice **sale lines**: quantity, unit price, line total ex/inc VAT, cost price snapshot, VAT rate, discount (`Rabat`), price type. Links `Fakt_ID`, `Vin_ID`, `Lager_ID`. |
| `tPrisliste_Cost` | 240 | Purchase price per wine and `PrisType` (mostly "Standard"). |
| `tPrisliste_Salg` | 442 | Sales prices per wine and `PrisType` (`0P`, `Alm`, `Tilbud`, `EP`, `Rabat`) with `Momssats` (0.25). |
| `tSettings` | 4 | Key/value config used on invoices: `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>`, `<fakt_savelocation>` (PDF output folder). |
| `USysApplicationLog` | 3 | Access data-macro error log (2013; `tKunder.AfterUpdate` EditRecord failures). |
| `MSys*`, `f_…_Data` | – | Access system tables; `Kontortema.thmx` is the embedded Office theme. |

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
- `tPrisliste_Cost.Vin_ID` / `tPrisliste_Salg.Vin_ID → tVinliste`
- The only relationship stored in the DB catalog that could be identified is `tVinliste ↔ tPrisliste_Cost`; the rest are enforced by query joins/combo boxes, not necessarily by constraints.

### 2.3 Key design observations

- **Stock is derived, not stored:** on-hand = Σ `tVinlager.Quantity` − Σ `tVinlager_Salg.Quantity` (union query `uVinlager` combines both; `uVinlager_Excel` is a variant; a consistency check compares the totals).
- **Price snapshotting:** sale lines copy sale price, cost price and VAT rate at time of sale, so later price-list edits do not change history. Totals (`SamletPris`, `SamletPris_mMoms`, `SamletCostPris`) are **stored, not computed** – redundancy that can drift.
- **Soft delete / archive:** `Udgået`, `Skjul`, `Delete`, `Lukket` flags hide rather than remove rows.
- **Price types** are free text in both price lists (case variants exist: `alm`/`Alm`, `standard`/`Standard`, `rød`/`Rød`).
- **Settings as key/value** with angle-bracket placeholders (`<fakt_adr>`), presumably substituted into invoice reports.

## 3. Queries

| Query | Kind | Role |
|---|---|---|
| `qVinliste` | Select | Active wines (`Udgået<>True`, ordered by name/vintage) – combo-box source. |
| `qVinliste_Vedligehold` | Select | Wine list for the maintenance form. |
| `qVinlager_Salg` | Select | Joins sale lines ↔ invoices ↔ customers ↔ wines ↔ warehouses. Feeds `rFaktura`; filters out `Delete=True`; dates formatted `yyyy/mm/dd`. |
| `qVinlager_Change`, `qVinlager_Change_Import` | Select / Append *(inferred)* | Stock-change entry and bulk import. |
| `uVinlager`, `uVinlager_Excel` | Union | Combined receipts and sales ledger for stock level calculation and Excel export. |
| `qVinliste` combos / price lookups | Select | Filter wines `Udgået<>True AND Private<>True`; price combos read `[Forms]![fVinlager_Salg]![Vin_ID]` (form-parameter queries). |
| Invoice combos | Select | Open invoices (`Lukket<>True`) and closed invoices, each joined to customer name. |

Queries marked *(inferred)* could not be read in full; names and fragments only.

## 4. Forms (UI)

| Form | Purpose |
|---|---|
| `fNavigation` | Main menu/switchboard: open/new invoice (combo `cboFaktura`), buttons to customers, wine list, stock, sale prices, mail list, settings. UI macros branch: if an invoice is chosen → open `fFaktura` and `fVinlager_Salg` filtered to it; otherwise open `fFaktura` in Add mode. |
| `fFaktura` | Invoice header (customer, warehouse, date, comment, closed flag). |
| `fFaktura_CopyExisting` | Copy an existing invoice to a new one (see §5). |
| `fFaktura_genåben` | Re-open a closed invoice. |
| `fVinlager_Salg` | Invoice line entry (wine, price type, price, quantity, discount; combos `cboSalgsPris`, `cboCostPris`). |
| `fVinlager_Change` | Add stock receipts/adjustments. |
| `fVinliste_Vedligehold` | Maintain the wine catalogue. |
| `fKunder`, `fKunder_Mailliste` | Customer maintenance and mailing-list view. |
| `fPrisliste_Cost`, `fPrisliste_Salg` | Maintain price lists. |
| `fLagre` | Maintain warehouses. |
| `fSettings` | Edit `tSettings`. |

## 5. Reports and code

**Reports:** `rFaktura` (invoice, sourced from `qVinlager_Salg`, with a *Hide Sub Totals* option), `rKundeListe` (customer list), `rVinliste` (wine list).

**Modules:**

- `DBCopyFakt` – copies an invoice: creates a new `tFaktura` row for a chosen customer (copies Lukket, Lager_ID, HideSubTotals, comment "Oprettet som kopi af faktura N"), then copies its sale lines.
- `DBFunctionsA` – helper functions; recovered fragments show the **mail-list builder** (`SELECT Mailadr FROM tKunder WHERE Maillist = True and Skjul <> True and Mailadr <> ''`) and **PDF export** (`DoCmd.OutputTo acOutputReport, …, acFormatPDF`, saved to `<fakt_savelocation>`).
- `Development` – developer scratch/utility module.

**Macros:** `Autoexec` (startup, presumably opens `fNavigation`), `~TMPCLPMacro` (temporary clipboard macro), embedded UI macros on `fNavigation` buttons, and a data macro on `tKunder` (After Update) that failed twice in 2013 (`EditRecord failed…`, error −20335).

## 6. Main workflows

1. **Receive stock:** `fVinlager_Change` → row in `tVinlager`.
2. **Invoice a sale:** `fNavigation` → new/open invoice (`fFaktura`) → add lines in `fVinlager_Salg` (price from `tPrisliste_Salg`, cost from `tPrisliste_Cost`, stored as snapshot) → close invoice (`Lukket`) → print `rFaktura` to PDF in the configured folder.
3. **Re-open / copy invoice:** `fFaktura_genåben`, `fFaktura_CopyExisting` (`DBCopyFakt`).
4. **Maintain masters:** wines, customers, warehouses, both price lists, settings via their forms.
5. **Mailing list / exports:** `fKunder_Mailliste`, `uVinlager_Excel`.

## 7. Risks and cleanup candidates

- **Personal data in the file:** customer names, addresses, phones, emails, plus bank/registration data in `tSettings`. Treat the file as sensitive; do not commit it to a public repo.
- **Hard-coded path:** `<fakt_savelocation>` points to a user's Dropbox folder (`C:\Users\<user>\Dropbox\…`); PDF export breaks on any other machine.
- **Stored derived totals** (`SamletPris*`) can disagree with quantity × price − discount; `Rabat` is added to the VAT-inclusive figure in the invoice query, which should be checked.
- **Free-text lookup values** (`PrisType`, `Vin_Type`, `Vin_Str`, `Vin_Land`) have case variants and misuse (`Vin_Land` contains "Vinkasse 6 hvid", "Vinsmagning", "DK" – non-wines kept as products). Use lookup tables.
- **Stock by arithmetic** over two tables with no uniqueness/negative-stock guard; no per-invoice stock check was visible.
- **Soft-delete flags** are repeated per table with inconsistent semantics (`Delete` vs `Skjul` vs `Udgået`).
- **Single-file design:** data and UI share one `.accdb`; no split front-end/back-end, so multi-user use or upgrades risk corruption/overwrites.
- Obsolete/temporary objects: `~TMPCLPMacro`, `~sq_*` internal query objects, a stale `tPrisliste` reference in a saved row source, `test_slet` column ("test/delete") in `tPrisliste_Cost`.
- Data macro error log shows `tKunder.AfterUpdate` was broken in 2013.

> **Update:** the decided plan (SQLite, all logic in Python, self-contained, Access removed, Power BI on top, one-time migration tool) is in [Vinlager_Python_Rebuild_Plan.md](Vinlager_Python_Rebuild_Plan.md). Extra findings and the Access export runbook are in [Vinlager_Decompilation_Handoff.md](Vinlager_Decompilation_Handoff.md). The section below is the original outline and is superseded.

## 8. Suggested migration path (if the app is to be modernized)

1. Open once in Access to export the full schema, relationships, forms and VBA (Database Documenter or `Application.SaveAsText`) and confirm the *(inferred)* items above.
2. Move data to SQL (SQLite/SQL Server/Postgres) with FKs on the relationships in §2.2 and lookup tables for price types, wine types, sizes, countries.
3. Replace stored totals with computed columns/views; keep price snapshots.
4. Rebuild the invoice flow and PDF output against a configurable output path.
