# Vinlager DB – Extra Findings and Access Export Runbook

This document adds to [Vinlager_DB_Design.md](Vinlager_DB_Design.md); read that document first. It has two parts:
- **Part A** records the extra findings from the offline read of the Access file.
- **Part B** tells exactly what to export on a machine with full Microsoft Access, and how to do it.

> **Status:** the export in Part B was done. Its output is in `A:\Development\WineDB_py\WineDB_work\export`. The VBA code answered question 1 in B3: the formula for `Rabat` is in §5.1 of [the new design doc](../Vinlager_Python_SQLite_Design.md).

- **Source file:** `Vinlager DB_vMaster.accdb` (3.6 MB, last saved 2015-03-07).
- **Offline reader:** the Python library `access-parser`. It reads tables and data only, without Access or its database engine (ACE).

---

## Part A – Extra findings

### A1. Data quality checks (on the real data)

| Check | Result | Meaning |
|---|---|---|
| Invoices that point to a customer that does not exist | Customer `0` (invoice 6, an open draft) | `tKunder` has no row `0`. The database probably does not enforce this foreign key, or `0` is a default. |
| Invoices with no warehouse (`Lager_ID` is null) | 3 | The foreign key is optional. The new app needs a rule. |
| Invoices with no `FakturaDato` | 3 | Probably the open drafts. |
| Invoices with no sale lines | 8 of 143 | Empty or abandoned invoices. |
| Open invoices (not `Lukket`) | 14 (ids 6, 24, 54, 59, 108, 129, 137, 142, 144, 146–150) | Decide whether to migrate them or discard them. |
| Soft-deleted invoices (`Delete=True`) | 1 | `qVinlager_Salg` leaves it out. |
| Sale lines without their invoice / without their wine | 0 / 0 | The links on the sales side are all valid. |
| Stock receipts or prices without their wine | 0 | All valid. |
| Wines with no sales price / no cost price | 28 / 6 | Probably discontinued or private wines. |
| Wines with more than one cost price row | 18 | `tPrisliste_Cost` is not unique for each wine. The user picks the row in a combo box. |
| Duplicate `Vin_UID` | 0 | `Vin_UID` can be a natural key. |
| Rows in `tVinlager` with a negative `Quantity` | 341 of 863 | **Negative quantities are stock adjustments or removals.** So the "receipts" table is really a ledger of stock movements. |
| Combinations of wine and warehouse with negative on-hand stock (receipts − sales) | 15 of 283 | Nothing stops negative stock. The cause is either historical errors or a missing type of stock movement. |
| Sale lines with a quantity of 0 or less | 13 | Possibly returns or credit lines. |
| Customers: duplicate name / no email / hidden / on mail list | 2 / 2 / 10 / 129 | Clean up during the migration. |
| `Momssats` on sale lines | 0.25 on 516 lines, 0.00 on 149 lines | Some lines have no VAT (exports, wine boxes, tastings?). Confirm with the owner. |

### A2. Meaning of the prices and totals (important for the rebuild)

- `tVinlager_Salg.SalgsPris` is the **unit price with VAT**. `SamletPris` is the line total **without VAT**, and `SamletPris_mMoms` = `SamletPris × (1 + Momssats)`. This is true on **all 665 lines** (0 mismatches).
  Example: quantity 1, `SalgsPris` 165, `SamletPris` 132 (= 165 / 1.25).
- So the formula `quantity × SalgsPris − Rabat = SamletPris` is false on 504 of the 665 lines. This is expected and does not mean the data is corrupt. **How `Rabat` changes the totals is still unknown.** It must come from the VBA or form code (see B3). The invoice query adds `Rabat` to `SamletPris_mMoms`.
- `tPrisliste_Salg` has 3 main `PrisType` groups: `0P` (198 rows), `Alm` (199, including a case variant) and `Tilbud` (43). `EP` and `Rabat` have 1 row each. The meaning of `0P` and `EP` is not documented; ask the owner.
- `tPrisliste_Cost.PrisType` has two values: "Standard" (223, including a case variant) and "rå" (17, probably the raw or unrefined cost). The column `test_slet` is a leftover ("test, delete").

### A3. Reference values

- Sales period: **2013-06-30 to 2015-03-07**. The first stock record is from 2013-06-21.
- Totals, which are good targets for the migration check: 665 sale lines, 143 invoices, **Σ `SamletPris` = 326,572.40** (without VAT), Σ `tVinlager.Quantity` = 3,539 (after adjustments).
- Warehouses: 1 Vinotrentino, 2 "<owner> Privat", 3 "Vinkøleskab" (fridge).
- Wines by country: FR 89, IT 53, DE 46, ES 35. Some products that are not wine are stored as wines: `Vinkasse 6 hvid`, `Vinkasse 6 rød`, `DK` and `Vinsmagning`.
- Types: Rød 141 + 10 (lowercase), Hvid 61, Mousserende 7, Dessert 4, Rose 3, null 2.
- Sizes: Alm 201 + 1, MGM 18, Halv 4, DMGM 2, null 2.
- `Udgået` (discontinued): **corrected 2026-11-21:** 60 of the 228 wines are discontinued. The offline parser misread the flag as False on every wine. Example: the 10 wines with a code ending in `_fejl` ("error"), mostly second copies of a wine, of which 9 are discontinued.

### A4. Encoding and names

- Danish characters (æ, ø, å) are in column names (`Vin_Årgang`, `Vin_Udløb`, `Udgået`, `Vin_Område`) and in the data (`Vink�leskab`). The offline reader showed them as `�`. **Use the exact names from the Access export,** and read all text as Unicode.
- Some column names are reserved words or unclear: `By`, `Delete`, `Value` and `Id`. Rename them in the new schema.
- `tSettings` keys: `<fakt_adr>`, `<fakt_bank_opl>`, `<fakt_betaling_bet>` and `<fakt_savelocation>`. The values contain a postal address, bank registration and account numbers (personal and company data), and a path under `C:\Users\<user>\Dropbox\…`. This document does not show the values.

### A5. List of objects (from `MSysObjects`)

- **Forms (13):** fFaktura, fFaktura_CopyExisting, fFaktura_genåben, fKunder, fKunder_Mailliste, fLagre, fNavigation, fPrisliste_Cost, fPrisliste_Salg, fSettings, fVinlager_Change, fVinlager_Salg, fVinliste_Vedligehold.
- **Reports (3):** rFaktura, rKundeListe, rVinliste.
- **Modules (3):** DBCopyFakt, DBFunctionsA, Development.
- **Macros (2):** Autoexec, ~TMPCLPMacro.
- **Saved queries (8 with a name):** qVinlager_Change, qVinlager_Change_Import, qVinlager_Salg, qVinliste, qVinliste_Vedligehold, uVinlager, uVinlager_Excel, and **"Consistency Check"**. The last one compares row counts and sums between `uVinlager` / `uVinlager_Excel` and `tVinlager` + `tVinlager_Salg`. This suggests that the Excel export is used to check the data.
- **Hidden `~sq_*` objects** are the row-source queries of controls: `cKunde_ID` and `cLager_ID` on fFaktura, `cboFaktura` on fNavigation, and `cboSalgsPris`, `cboCostPris`, `cVin_ID`, `cLager_ID`, `cFakt_ID` and `Combo81` on fVinlager_Salg. The form export contains them, so they need no separate export.
- **Relationship objects:** only `tVinlistetPrisliste_Cost`, plus two system relationships of the navigation pane. The other joins are possibly defined only in queries.
- `qVinlager_Change_Import` (not `qVinlager_Change`) filters on `tVinlager.Date_Create > Now()`. **Explained 2026-11-21:** no row has a future date, so the query opens as an empty editable grid. The button "Import vinlager tilgange/afgange" opens it, and the user pastes many stock changes at once.
- A data macro on `tKunder` (After Update, `EditRecord`) logged errors on 2013-02-28 (error −20335). Its content was not recovered.
- The embedded Office theme `Kontortema.thmx` is not needed.
- The `Development` module and `~TMPCLPMacro` look like scratch objects.

### A6. Items the offline reader could not see

Defaults, validation rules, input masks, required flags, indexes, which relationships enforce integrity or cascade, all layouts and control bindings of forms and reports, all VBA procedure bodies, the content of `Autoexec`, the startup options, and the full text of every query.

---

## Part B – What to export on the Access machine

### B1. Required output (checklist)

| # | Item | Why the Python rebuild needs it |
|---|---|---|
| 1 | **Table schema:** field names (with æ, ø, å), data type, size, required, allow zero length, default, validation rule and text, caption and format, indexes (unique, primary), lookup properties | Correct table definitions and constraints; hidden business rules |
| 2 | **Relationships:** name, parent and child table, fields, attributes (enforced, cascade update or delete, join type) | Foreign keys and how deletes behave |
| 3 | **All VBA source:** the 3 modules, and the class modules of forms and reports with the code behind the buttons | Rabat and VAT arithmetic, invoice numbering, close and reopen, copy, PDF names, mail list, import logic |
| 4 | **The SQL of all saved queries,** including `uVinlager`, `qVinlager_Change_Import` and "Consistency Check" | Stock formula, import path |
| 5 | **Forms and reports as text** (`SaveAsText`) | Field lists, control bindings, event handlers, layout and grouping of the invoice report for the PDF |
| 6 | **Macros, UI macros and data macros** (`tKunder` After Update) | Hidden behaviour on customers |
| 7 | **References** of the VBA project, and **startup and database properties** (start form, ribbon and other options) | What the app depends on |
| 8 | **Linked tables** (`TableDef.Connect`) | Shows whether any data is outside this file (none expected) |
| 9 | **Screenshots** of fNavigation, fFaktura, fVinlager_Salg and the printed rFaktura | How the new screens and the invoice must look |
| 10 | Optional: **a clean CSV export** of every table (UTF-8) | More reliable than the offline parser for the migration. **It contains personal data. Keep it private.** |

### B2. How to run the export

> **Caution:** never run the export on the original file. Always use a copy.

1. Copy the `.accdb` file to a working folder.
2. Hold down **Shift** and open the copy. Shift stops `Autoexec` and the startup form.
3. If Access asks, enable the content.
4. Push `Alt+F11` to open the VBA editor.
5. Select Insert → Module, and paste the script in B4.
6. Put the cursor in `ExportAll` and push `F5`.
   The script writes its output to an `export\` folder next to the file: `forms\`, `reports\`, `modules\`, `macros\`, `queries\`, `datamacros\`, `schema.txt`, `relationships.txt`, `references.txt`, `dbprops.txt`, and `csv\` if you selected it.
7. Zip the `export\` folder together with the screenshots (item 9), and copy the zip file back to this project.
8. Delete the CSV files from all shared locations, because they contain personal data.

`SaveAsText` writes UTF-16 files. Do not convert them; the rebuild can read them as they are.

### B3. Questions the export must answer

1. How exactly does `Rabat` change `SamletPris`, `SamletPris_mMoms` and `SamletCostPris`? (Look in the code of fVinlager_Salg and its AfterUpdate events.)
2. What do the price types `0P`, `EP`, `Alm`, `Tilbud` and `Rabat` and the cost type `rå` mean? How does the form select the default price type?
3. How does the app give out `Fakt_ID` (AutoNumber or by hand)? What exactly do `Lukket`, `Delete` and "genåben" do?
4. What do `qVinlager_Change_Import` and `uVinlager_Excel` import or export, from where, and in which format?
5. Which relationships enforce integrity, and how do deletes behave?
6. What does the After Update data macro on `tKunder` do?
7. Does the invoice report show subtotals for each VAT rate, and what does `HideSubTotals` hide? Does the invoice number have a format or text other than `Fakt_ID`?
8. What happens when stock becomes negative? Does `fVinlager_Salg` show a warning?

### B4. Export script (VBA; paste it into a standard module)

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

**Notes:**
- `ExportAll` needs the DAO reference. An `.accdb` file has it by default. To check, open the VBA editor and select Tools → References → *Microsoft Office xx Access database engine Object Library*.
- If a form exports empty, open the database once without Shift and try again. The form can also be corrupt or locked; record which form failed.
- If your Access version does not define `acTableDataMacro`, use the value `12`.
- As an optional cross-check of the schema, run Tools → Analyze → Documenter and save the result as a PDF file.

### B5. Alternative if the work computer blocks macros

Do the export by hand. It takes longer, but the result is the same:
1. Open each form in Design view and take a screenshot.
2. In the VBA editor, open each module and form class in the Project Explorer and copy the VBA code.
3. In Query Design, open SQL View for each query and copy the SQL.

---

## Part C – Next steps after the export

1. Complete the schema, relationships, query SQL and business rules in the design doc, and replace every *(inferred)* item.
2. Write the table definitions (SQLite or Postgres) from `schema.txt` and `relationships.txt`.
3. Write the migration (CSV → clean → load) so that it can run again at any time. Include the checks from A3: 665 lines, 143 invoices, Σ `SamletPris` = 326,572.40, and on-hand stock for each wine.
4. Rebuild invoicing first, because it has the highest risk (`Rabat` and VAT arithmetic, PDF layout). Test it against historical invoices.
