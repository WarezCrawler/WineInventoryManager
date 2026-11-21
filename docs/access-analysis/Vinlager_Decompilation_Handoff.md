# Vinlager DB – Findings Not in the Design Doc + Decompilation Runbook

Companion to [Vinlager_DB_Design.md](Vinlager_DB_Design.md). Read that first.
Purpose: (A) record extra findings from the offline read, and (B) say exactly what must be extracted on a machine with full Microsoft Access, and how.

Source file: `Vinlager DB_vMaster.accdb` (3.6 MB, last saved 2015-03-07).
Offline reader used: Python `access-parser` (tables and data only, no Access/ACE).

---

## Part A – Additional findings

### A1. Data-quality checks (run on the real data)

| Check | Result | Meaning |
|---|---|---|
| Invoices pointing to a missing customer | Customer `0` (invoice 6, an open draft) | `tKunder` has no row `0`. The DB probably does not enforce this FK, or `0` is a default. |
| Invoices with no warehouse (`Lager_ID` null) | 3 | The FK is optional. The new app needs a rule. |
| Invoices with no `FakturaDato` | 3 | Probably the open drafts. |
| Invoices with no sale lines | 8 of 143 | Empty or abandoned invoices. |
| Open (not `Lukket`) invoices | 14 (IDs 6, 24, 54, 59, 108, 129, 137, 142, 144, 146–150) | Decide whether to migrate or discard them. |
| Soft-deleted invoices (`Delete=True`) | 1 | Excluded from `qVinlager_Salg`. |
| Sale lines → invoice / wine orphans | 0 / 0 | Referential integrity is clean on the sales side. |
| Stock receipts or prices → wine orphans | 0 | Clean. |
| Wines with no sale price / no cost price | 28 / 6 | Likely discontinued or private wines. |
| Wines with more than one cost-price row | 18 | `tPrisliste_Cost` is not unique per wine. The app picks via a combo box. |
| Duplicate `Vin_UID` | 0 | Usable as a natural key. |
| `tVinlager.Quantity` negative rows | 341 of 863 | **Negative quantities are used as stock adjustments or removals.** The "receipts" table is really a stock-movement ledger. |
| Wine/warehouse combos with negative on-hand (receipts − sales) | 15 of 283 | There is no stock guard. Either historical errors or a missing movement type. |
| Sale lines with qty ≤ 0 | 13 | Possibly returns or credit lines. |
| Customers: duplicate name / no email / hidden / on mail list | 2 / 2 / 10 / 129 | Clean up on migration. |
| `Momssats` on sale lines | 0.25 on 516 lines, 0.00 on 149 | Zero-VAT lines exist (exports, wine boxes, tastings?). Confirm. |

### A2. Price and total semantics (important for the rebuild)

- `tVinlager_Salg.SalgsPris` is the **VAT-inclusive unit price**. `SamletPris` is the **ex-VAT** line total, and `SamletPris_mMoms` = `SamletPris × (1 + Momssats)`. This held on **all 665 lines** (0 mismatches).
  Example: qty 1, `SalgsPris` 165, `SamletPris` 132 (= 165 / 1.25).
- Because of this, `qty × SalgsPris − Rabat = SamletPris` fails on 504 of 665 lines. That is expected, not corruption. **The formula for how `Rabat` enters the totals is still unknown** and must come from the VBA or form code (see B3). The invoice query adds `Rabat` to `SamletPris_mMoms`.
- `tPrisliste_Salg` has 3 `PrisType` families: `0P` (198 rows), `Alm` (199 incl. case variant), `Tilbud` (43), plus `EP` and `Rabat` (1 each). Meaning of `0P` and `EP` is not documented. Ask the owner.
- `tPrisliste_Cost.PrisType`: "Standard" (223 incl. case variant) and "rå" (17, probably raw or unrefined cost). `test_slet` column is a leftover ("test, delete").

### A3. Reference values

- Sales window: **2013-06-30 → 2015-03-07**. Earliest stock record: 2013-06-21.
- Totals (good reconciliation targets for the migration): sales lines 665, invoices 143, **Σ `SamletPris` = 326,572.40** (ex VAT), Σ `tVinlager.Quantity` = 3,539 (net of adjustments).
- Warehouses: 1 Vinotrentino, 2 "<owner> Privat", 3 "Vinkøleskab" (fridge).
- Wines by country: FR 89, IT 53, DE 46, ES 35, plus non-wine "products" stored as wines (`Vinkasse 6 hvid`, `Vinkasse 6 rød`, `DK`, `Vinsmagning`). Types: Rød 141+10 (lowercase), Hvid 61, Mousserende 7, Dessert 4, Rose 3, null 2. Sizes: Alm 201+1, MGM 18, Halv 4, DMGM 2, null 2.
- `Udgået` (discontinued) = False on every wine. The flag is effectively unused, or the "Private" flag is used instead.

### A4. Encoding and naming

- Danish characters (æ øå) appear in column names: `Vin_Årgang`, `Vin_Udløb`, `Udgået`, `Vin_Område`, and in data (`Vink�leskab`). My reader showed them as `�`. **Use the exact names from the Access export** and read text as Unicode.
- Reserved or awkward column names: `By`, `Delete`, `Value`, `Id` (SQL keywords or ambiguous). Rename in the new schema.
- `tSettings` keys: `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>`, `<fakt_savelocation>`. Values contain a postal address, bank registration and account numbers (personal/company data) and a path under `C:\Users\<user>\Dropbox\…`. Not reproduced here.

### A5. Objects inventory (from `MSysObjects`)

- **Forms (13):** fFaktura, fFaktura_CopyExisting, fFaktura_genåben, fKunder, fKunder_Mailliste, fLagre, fNavigation, fPrisliste_Cost, fPrisliste_Salg, fSettings, fVinlager_Change, fVinlager_Salg, fVinliste_Vedligehold.
- **Reports (3):** rFaktura, rKundeListe, rVinliste. **Modules (3):** DBCopyFakt, DBFunctionsA, Development. **Macros (2):** Autoexec, ~TMPCLPMacro.
- **Saved queries (8 named):** qVinlager_Change, qVinlager_Change_Import, qVinlager_Salg, qVinliste, qVinliste_Vedligehold, uVinlager, uVinlager_Excel, and one called **"Consistency Check"** (compares row counts and sums between `uVinlager` / `uVinlager_Excel` and `tVinlager` + `tVinlager_Salg`; implies the Excel export is a reconciliation tool).
- **Hidden `~sq_*` objects** are embedded row-source queries of controls: `cKunde_ID` and `cLager_ID` on fFaktura, `cboFaktura` on fNavigation, and `cboSalgsPris`, `cboCostPris`, `cVin_ID`, `cLager_ID`, `cFakt_ID`, `Combo81` on fVinlager_Salg. Reproduced inside the form export, not separately needed.
- **Relationship objects found:** only `tVinlistetPrisliste_Cost` (plus two Nav-pane system ones). Other joins may be defined only in queries.
- `qVinlager_Change` filters `tVinlager.Date_Create > Now()` *(future-dated receipts)*. Purpose unknown (planned deliveries?).
- A data macro on `tKunder` (After Update, `EditRecord`) logged errors on 2013-02-28 (error −20335). Its content is not recovered.
- Embedded resource: Office theme `Kontortema.thmx` (not needed).
- A `Development` module and `~TMPCLPMacro` look like scratch.

### A6. Items I could not see

Defaults, validation rules, input masks, required flags, indexes, which relationships enforce integrity or cascade, all form/report layouts and control bindings, all VBA procedure bodies, `Autoexec` contents, startup options, and the full text of every query.

---

## Part B – What to extract on the Access machine

### B1. Needed outputs (checklist)

| # | Artifact | Why it matters to the Python rebuild |
|---|---|---|
| 1 | **Table schema**: field names (with æøå), data type, size, required, allow-zero-length, default, validation rule and text, caption/format, indexes (unique, primary), lookup properties | Correct DDL and constraints; hidden business rules |
| 2 | **Relationships**: name, parent/child table, fields, attributes (enforced, cascade update/delete, join type) | Foreign keys and delete behaviour |
| 3 | **All VBA source** (3 modules plus form/report class modules, with code behind buttons) | Rabat/VAT arithmetic, invoice numbering, close/reopen, copy, PDF naming, mail list, import logic |
| 4 | **All saved query SQL** (including `uVinlager`, `qVinlager_Change_Import`, "Consistency Check") | Stock formula, import path |
| 5 | **Forms and reports as text** (`SaveAsText`) | Field lists, control bindings, event wiring, report layout and grouping for the invoice PDF |
| 6 | **Macros, UI macros and data macros** (`tKunder` After Update) | Hidden behaviour on customers |
| 7 | **References** (VBA project) and **startup/DB properties** (start form, ribbon, etc.) | What the app depends on |
| 8 | **Linked tables** (`TableDef.Connect`) | Check whether anything lives outside this file (none expected) |
| 9 | **Screenshots** of fNavigation, fFaktura, fVinlager_Salg and the printed rFaktura | Target UX and the invoice look |
| 10 | Optional: **clean CSV dump** of every table (UTF-8) | Better than my parser for migration. **Contains personal data. Keep private.** |

### B2. How to run

1. Copy the `.accdb` to a working folder. Never run this on the original.
2. Open the copy **holding Shift** (bypasses `Autoexec` and startup form). Enable content if prompted.
3. `Alt+F11` → Insert → Module → paste the script below → put the cursor in `ExportAll` → `F5`.
4. Output goes to an `export\` folder next to the file: `forms\`, `reports\`, `modules\`, `macros\`, `queries\`, `datamacros\`, `schema.txt`, `relationships.txt`, `references.txt`, `dbprops.txt`, optionally `csv\`.
5. Zip `export\` plus the screenshots (item 9) and bring it back into this folder. Delete the CSVs from shared locations afterwards (personal data).

`SaveAsText` writes UTF-16 files. Keep them as-is. I can read them.

### B3. Specific questions the exports must answer

1. How exactly does `Rabat` change `SamletPris`, `SamletPris_mMoms` and `SamletCostPris`? (Look in fVinlager_Salg code and AfterUpdate events.)
2. What do price types `0P`, `EP`, `Alm`, `Tilbud`, `Rabat` and cost type `rå` mean, and how does the form choose the default one?
3. How is `Fakt_ID` allocated (autonumber or manual) and what do `Lukket`, `Delete`, "genåben" do exactly?
4. What do `qVinlager_Change_Import` and `uVinlager_Excel` import/export, from where, and in what format?
5. Which relationships enforce integrity and how do deletes behave?
6. What does the `tKunder` After Update data macro do?
7. Does the invoice report show subtotals by VAT rate, and what does `HideSubTotals` hide? Is there an invoice number format or text beyond `Fakt_ID`?
8. What happens when stock goes negative? Any warning in `fVinlager_Salg`?

### B4. Export script (VBA, paste into a standard module)

```vba
Option Compare Database
Option Explicit

Private Sub EnsureDir(p As String)
    If Dir(p, vbDirectory) = "" Then MkDir p
End Sub

Private Function FTName(t As Long) As String
    Select Case t
        Case dbBoolean: FTName = "Yes/No"
        Case dbByte: FTName = "Byte"
        Case dbInteger: FTName = "Integer"
        Case dbLong: FTName = "Long"
        Case dbCurrency: FTName = "Currency"
        Case dbSingle: FTName = "Single"
        Case dbDouble: FTName = "Double"
        Case dbDate: FTName = "Date/Time"
        Case dbText: FTName = "Text"
        Case dbMemo: FTName = "Memo/LongText"
        Case dbDecimal: FTName = "Decimal"
        Case dbGUID: FTName = "GUID"
        Case dbBigInt: FTName = "BigInt"
        Case Else: FTName = "Type" & t
    End Select
End Function

Private Function Prop(o As Object, n As String) As String
    On Error Resume Next
    Prop = CStr(o.Properties(n).Value)
End Function

Public Sub ExportAll()
    Dim root As String, db As DAO.Database, ao As AccessObject
    Dim td As DAO.TableDef, fld As DAO.Field, idx As DAO.Index, rel As DAO.Relation
    Dim qd As DAO.QueryDef, f As Integer, d As String, ref As Object
    Dim doCsv As Boolean
    root = CurrentProject.Path & "\export\"
    doCsv = (MsgBox("Also dump every table to CSV? (contains personal data)", vbYesNo) = vbYes)
    Set db = CurrentDb
    For Each d In Array("", "forms\", "reports\", "modules\", "macros\", "queries\", "datamacros\", "csv\")
        EnsureDir root & d
    Next

    For Each ao In CurrentProject.AllForms
        Application.SaveAsText acForm, ao.Name, root & "forms\" & ao.Name & ".txt"
    Next
    For Each ao In CurrentProject.AllReports
        Application.SaveAsText acReport, ao.Name, root & "reports\" & ao.Name & ".txt"
    Next
    For Each ao In CurrentProject.AllModules
        Application.SaveAsText acModule, ao.Name, root & "modules\" & ao.Name & ".txt"
    Next
    For Each ao In CurrentProject.AllMacros
        Application.SaveAsText acMacro, ao.Name, root & "macros\" & ao.Name & ".txt"
    Next
    For Each qd In db.QueryDefs   ' includes ~sq_ hidden ones; harmless
        On Error Resume Next
        Application.SaveAsText acQuery, qd.Name, root & "queries\" & Replace(qd.Name, "~", "_") & ".txt"
        On Error GoTo 0
    Next

    ' Table schema + data macros + optional CSV
    f = FreeFile
    Open root & "schema.txt" For Output As #f
    For Each td In db.TableDefs
        If (td.Attributes And dbSystemObject) = 0 Then
            Print #f, "TABLE " & td.Name & "  rows=" & td.RecordCount & "  connect=[" & td.Connect & "]  validation=[" & td.ValidationRule & "]"
            For Each fld In td.Fields
                Print #f, "  FIELD " & fld.Name & " | " & FTName(fld.Type) & " | size=" & fld.Size & _
                    " | required=" & fld.Required & " | zeroLen=" & IIf(fld.Type = dbText Or fld.Type = dbMemo, fld.AllowZeroLength, "") & _
                    " | default=[" & fld.DefaultValue & "] | rule=[" & fld.ValidationRule & "] | ruleText=[" & fld.ValidationText & "]" & _
                    " | format=[" & Prop(fld, "Format") & "] | caption=[" & Prop(fld, "Caption") & "]" & _
                    " | autonum=" & ((fld.Attributes And dbAutoIncrField) <> 0) & _
                    " | lookup=[" & Prop(fld, "RowSource") & "]"
            Next
            For Each idx In td.Indexes
                Dim cols As String: cols = ""
                For Each fld In idx.Fields: cols = cols & fld.Name & ",": Next
                Print #f, "  INDEX " & idx.Name & " (" & cols & ") primary=" & idx.Primary & " unique=" & idx.Unique & " required=" & idx.Required
            Next
            On Error Resume Next
            Application.SaveAsText acTableDataMacro, td.Name, root & "datamacros\" & td.Name & ".txt"
            If doCsv Then DoCmd.TransferText acExportDelim, , td.Name, root & "csv\" & td.Name & ".csv", True, , 65001
            On Error GoTo 0
        End If
    Next
    Close #f

    ' Relationships
    f = FreeFile
    Open root & "relationships.txt" For Output As #f
    For Each rel In db.Relations
        Print #f, rel.Name & " | parent=" & rel.Table & " | child=" & rel.ForeignTable & " | attributes=" & rel.Attributes & _
            "  (1=unique,2=dontEnforce,256=cascadeUpdate,4096=cascadeDelete,16777216=leftJoin,33554432=rightJoin)"
        For Each fld In rel.Fields
            Print #f, "    " & fld.Name & " -> " & fld.ForeignName
        Next
    Next
    Close #f

    ' VBA references, DB properties
    f = FreeFile
    Open root & "references.txt" For Output As #f
    For Each ref In Application.VBE.ActiveVBProject.References
        Print #f, ref.Name & " | " & ref.FullPath & " | builtin=" & ref.BuiltIn
    Next
    Close #f
    f = FreeFile
    Open root & "dbprops.txt" For Output As #f
    Dim p As DAO.Property
    On Error Resume Next
    For Each p In db.Properties
        Print #f, p.Name & " = " & CStr(p.Value)
    Next
    Close #f

    MsgBox "Done: " & root
End Sub
```

Notes:
- `ExportAll` needs the DAO reference (default in `.accdb`; check VBE → Tools → References → *Microsoft Office xx Access database engine Object Library*).
- If a form exports empty, open the DB once without Shift and retry. A corrupt or locked form is also possible; report which one failed.
- If `acTableDataMacro` is not defined in your Access version, use the value `12`.
- If you prefer, run `Tools → Analyze → Documenter` for the schema as a cross-check and save to PDF.

### B5. Alternative if code export is blocked

If the work computer blocks macros: open each form in Design view and screenshot; copy VBA by hand from the VBE (Project Explorer → each module and form class); in Query Design → SQL View copy the SQL of every query. Slower but equivalent.

---

## Part C – Next steps once the export is back

1. I will complete the schema, relationships, query SQL and business rules in the design doc (replacing every "inferred").
2. Build the SQLite/Postgres DDL from `schema.txt` and `relationships.txt`.
3. Write the re-runnable ETL (CSV → clean → load) with the reconciliation checks from A3 (665 lines, 143 invoices, Σ `SamletPris` = 326,572.40, per-wine on-hand).
4. Rebuild invoicing first (highest risk: `Rabat`/VAT maths and PDF layout), with tests against historical invoices.
