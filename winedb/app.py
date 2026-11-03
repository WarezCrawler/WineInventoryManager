"""Table browser: start with `python -m winedb`, then open each table in the browser."""
import argparse

from nicegui import ui

from winedb.browse import table_counts, table_view
from winedb.config import db_path
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
        # Placeholder: the importer (CSV migration tool) is not built yet.
        ui.button("Import from Access database", icon="upload_file",
                  on_click=lambda: ui.notify("Not built yet: the import from the Access database is a planned feature.")
                  ).props("flat dense no-caps")

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="winedb", description="Browse the wine inventory tables.")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)
    connect().close()  # create or upgrade the database before serving, so a problem shows up here
    ui.run(host="127.0.0.1", port=args.port, title="Wine Inventory Manager", reload=False, show=not args.no_browser)
