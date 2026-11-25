# Parallel run: Access and the new program side by side

This procedure checks that the new program stores the same data as Access for the same work. You enter one short scenario in Access and the same scenario in the new program. Then a check compares what each system stored, field by field. It is step 11 of version 1 ([Roadmap.md](Roadmap.md)).

Do the run on **copies**. The live Access file and the program's own `data` folder are never used.

## What you need

- The Access file that you use every day (the live file, not the old test copy).
- The built program: `dist\WineInventoryManager\WineInventoryManager.exe`.
- The project folder with its Python environment, to run the check: `A:\Development\WineInventoryManager`.
- About 30 minutes.

## 1. Make the copies

1. Close Access.
2. Make the folder `C:\ParallelRun`. Do not use a Dropbox, OneDrive or other synced folder: the copies contain customer and bank data.
3. Copy the live Access file into the folder **two times**, with these names:
   - `BEFORE.accdb`: the starting point. Do not open it.
   - `AFTER.accdb`: the copy that you work in with Access.

## 2. Start the program on its own test database

1. Close the program if it is open.
2. Open PowerShell and type these three lines. They start the program with an empty database in `C:\ParallelRun`, so the program's own data is not touched:

   ```powershell
   $env:WINE_DB_PATH = "C:\ParallelRun\app.db"
   $env:WINE_SETTINGS_PATH = "C:\ParallelRun\settings.json"
   & "A:\Development\WineInventoryManager\dist\WineInventoryManager\WineInventoryManager.exe"
   ```
3. In the program, click **Tables**, then **Import from Access database**. Select `C:\ParallelRun\BEFORE.accdb` and click **Import**. The import must end with "The import matches the source".
4. Keep this PowerShell window open. When you start the program again for this run, use the same window.

## 3. Enter the scenario in both systems

Do each step first in Access (in `AFTER.accdb`), then in the program. Use the same values in both. Write down the wine codes that you use.

| # | What to do | In Access | In the program |
|---|---|---|---|
| 1 | Stock change: a wine of your choice, warehouse Vinotrentino, quantity **6**, comment `Parallel run 1` | Open Vinlager tilgange/afgange | Stock change |
| 2 | Stock change: the same wine, quantity **-2**, comment `Parallel run 2` | the same form | Stock change |
| 3 | New customer: name `Parallel Test`, postal code `2700`, city `Test` | Vedligehold Kundedata, new record | Maintain customers, New customer |
| 4 | New invoice: customer `Parallel Test`, warehouse Vinotrentino, **invoice date today** (type it in Access; Access leaves the date empty), comment `Parallel run` | Åben faktura egenskaber (no invoice selected) | Invoice (no invoice selected) |
| 5 | Line 1: a wine with a price of type `Alm` in its price list. Pick that price. Quantity **2**. | Åben Faktura | Open invoice lines |
| 6 | Line 2: another wine. Type the price **150** yourself, discount **10**, quantity **1**. | the same form | Save line, then the next line |
| 7 | Line 3: a wine. Type the price **99** yourself, VAT **0**, quantity **-1** (a return). | the same form | the same screen |
| 8 | Close the invoice | Luk Faktura | Close invoice |

Notes:
- Keep the cost price that each system fills in (the "Standard" cost). Do not change it.
- If you make a mistake in one system, make the same correction in the other one. A wrong invoice line is deleted in Access and cancelled in the program. The check knows this difference.

## 4. Run the check

1. Close Access and the program.
2. In PowerShell, type:

   ```powershell
   cd A:\Development\WineInventoryManager
   .\.venv\Scripts\python -m migrate.parallel_run C:\ParallelRun\BEFORE.accdb C:\ParallelRun\AFTER.accdb C:\ParallelRun\app.db --report C:\ParallelRun\report.txt
   ```

The check only reads the three files.

## 5. Read the result

The first line of the report gives the result:

- **PASS**: Access and the program made the same changes. The report shows how many rows each system changed, per table. Expect changes in `stock_transactions` (2), `customers` (1), `invoice_header` (1) and `invoice_lines` (3).
- **DIFF**: the report lists each difference with the table, the row and the column, for example `amount_ex_vat: Access 352.0, app 352.01`. Send the report to the developer. It holds no customer data other than the rows of the scenario.

How the check compares:
- A new row is compared with the new row in the other system that was made in the same order (the first new invoice with the first new invoice). The two systems can give a new row a different number; the report then shows a note, not a difference.
- The time of entry is compared by date only.
- A line that was cancelled in the program and deleted in Access is a note, not a difference (decision 16).

## 6. Clean up

Delete the folder `C:\ParallelRun` after the run. It contains business data.

To start the program normally again, close the PowerShell window and start the program as usual. It then uses its own database again.
