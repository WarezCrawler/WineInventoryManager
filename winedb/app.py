"""Table browser: start with `python -m winedb`, then open each table in the browser."""
import argparse
import sys

from nicegui import app, run, ui

from migrate.import_accdb import import_accdb
from winedb.browse import table_counts, table_view
from winedb.config import app_dir, db_path
from winedb.db import connect


def _load(name: str | None):
    conn = connect()
    try:
        counts = table_counts(conn)
        selected = name or counts[0][0]
        return counts, selected, table_view(conn, selected)
    except KeyError:
        return counts, None, None
    finally:
        conn.close()


async def _browse(path_input) -> None:
    """Native file dialog (only available in the program window, not in a browser tab)."""
    try:
        import webview
        window = app.native.main_window
        files = await window.create_file_dialog(webview.FileDialog.OPEN, directory=str(app_dir()), file_types=("Access database (*.accdb;*.mdb)", "All files (*.*)"))
    except Exception:
        ui.notify("The file dialog is only available in the program window. Type or paste the path instead.")
        return
    if files:
        path_input.value = files[0]


def _import_dialog() -> None:
    with ui.dialog().props("persistent") as dialog, ui.card().classes("w-[44rem] max-w-full"):
        ui.label("Import from Access database").classes("text-lg font-bold")
        ui.label("One-time import into an empty database. The Access file is only read, never changed. "
                 "Use a copy of it.").classes("text-sm opacity-70")
        with ui.row().classes("w-full items-center no-wrap"):
            path = ui.input("Access file (.accdb)").props("dense clearable").classes("grow")
            ui.button("Browse...", on_click=lambda: _browse(path)).props("flat dense no-caps")
        status = ui.label("").classes("font-bold")
        report = ui.textarea().props("readonly outlined input-class=font-mono").classes("w-full")
        report.set_visibility(False)
        spinner = ui.spinner(size="lg")
        spinner.set_visibility(False)

        async def start() -> None:
            if not (path.value or "").strip():
                status.text = "Choose the Access file first."
                return
            go.disable()
            spinner.set_visibility(True)
            status.text = "Importing and checking the data..."
            outcome = await run.io_bound(import_accdb, path.value.strip().strip('"'))
            spinner.set_visibility(False)
            status.text = outcome.message
            report.value = outcome.report
            report.set_visibility(bool(outcome.report))
            if outcome.ok:
                close.text = "Show the tables"
                close.on_click(lambda: ui.navigate.to("/"))
            else:
                go.enable()

        with ui.row().classes("w-full justify-end"):
            close = ui.button("Close", on_click=dialog.close).props("flat no-caps")
            go = ui.button("Import", on_click=start).props("no-caps")
    dialog.open()


@ui.page("/")
@ui.page("/table/{name}")
def table_page(name: str | None = None):
    counts, selected, view = _load(name)

    with ui.header().classes("items-center"):
        ui.label("Wine Inventory Manager").classes("text-lg font-bold")
        ui.label(str(db_path())).classes("text-xs opacity-70")

    with ui.left_drawer().classes("bg-slate-100"):
        ui.label("Tables").classes("font-bold")
        for table, count in counts:
            weight = "font-bold" if table == selected else ""
            ui.link(f"{table} ({count})", f"/table/{table}").classes(weight)
        ui.separator()
        ui.button("Import from Access database", icon="upload_file", on_click=_import_dialog).props("flat dense no-caps")

    if view is None:
        ui.label(f"Unknown table: {name}")
        return

    ui.label(f"{selected}: {view['total']} rows").classes("text-lg")
    if view["total"] > len(view["rows"]):
        ui.label(f"Showing the first {len(view['rows'])} rows").classes("text-orange")
    columns = [{"name": c, "label": c, "field": c, "align": "left", "sortable": True} for c in view["columns"]]
    filter_box = ui.input("Filter").props("clearable dense")
    table = ui.table(columns=columns, rows=view["rows"], row_key=view["key"], pagination=25)
    table.classes("w-full")
    table.bind_filter_from(filter_box, "value")


def _fail(message: str) -> None:
    """The packaged program has no console, so a startup problem is shown in a message box."""
    print(message, file=sys.stderr)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Wine Inventory Manager", 0x10)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="winedb", description="Browse the wine inventory tables.")
    parser.add_argument("--mode", choices=["window", "browser", "server"], default="window",
                        help="window = own program window (default), browser = open in the browser, server = no UI opened")
    parser.add_argument("--port", type=int, default=8080, help="port for browser/server mode")
    args = parser.parse_args(argv)
    try:
        connect().close()  # create or upgrade the database before showing anything
    except Exception as e:
        _fail(f"Could not open the database:\n{db_path()}\n\n{e}")
        raise SystemExit(1)
    window = args.mode == "window"
    ui.run(host="127.0.0.1", port=None if window else args.port, title="Wine Inventory Manager", reload=False,
           native=window, window_size=(1280, 800) if window else None, show=args.mode == "browser")
