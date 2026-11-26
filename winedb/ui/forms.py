"""Shared parts of the master data screens (design doc §6.6; step 10): a list with a filter, an edit panel,
problems marked at the fields, and the confirmation dialog.

A screen is described by its fields; `master_screen()` builds the list, the panel and the buttons. The data
functions (winedb.masterdata) do the checks; this module only shows their result."""
import logging
from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from winedb.db import connect
from winedb.ui.labels import label
from winedb.validation import ValidationError

log = logging.getLogger(__name__)


@dataclass
class Field:
    """One input of an edit panel. `kind`: text, suggest (text that suggests the values in the data), whole,
    number, flag, textarea. `suggest` returns the suggestions (called with a connection)."""
    name: str
    caption: str = ""
    kind: str = "text"
    suggest: Callable | None = None
    default: object = None


@dataclass
class Flag:
    """The "Delete" of a screen, as Access did it: a flag that hides the row and can be undone."""
    name: str                       # the column, for example is_discontinued
    show_caption: str               # the check box that also lists the flagged rows
    delete_caption: str             # the button that sets the flag
    restore_caption: str            # the button that removes it
    flagged_text: str               # shown on the panel of a flagged row
    question: str                   # the confirmation, with {id}
    done: str                       # the message after the flag is set, with {id}
    undone: str                     # the message after the flag is removed, with {id}
    set: Callable                   # set(conn, row_id, bool)


@dataclass
class Screen:
    title: str
    noun: str                       # "wine", "customer", "warehouse"
    key: str                        # the id column
    columns: list[str]              # the list columns
    fields: list[Field]
    load: Callable                  # load(conn, include_flagged) -> rows
    get: Callable                   # get(conn, row_id) -> row
    save: Callable                  # save(conn, values, row_id) -> row_id
    flag: Flag | None = None
    no_delete_text: str = ""        # shown when the screen has no delete
    extra: Callable | None = None   # extra(): builds more UI below the panel; returns show(row_id or None)


def clear_mark(element) -> None:
    element.props.pop("error", None)
    element.props.pop("error-message", None)


def show_problems(error: ValidationError, inputs: dict, summary, what: str) -> None:
    """Show why an action failed: in red at each field concerned, in the summary line and in a pop-up."""
    for element in inputs.values():
        clear_mark(element)
    for name, message in error.fields.items():
        if name in inputs:
            inputs[name].props["error"] = True
            inputs[name].props["error-message"] = message
    summary.text = " ".join(error.problems)
    ui.notify(f"{what}: {summary.text}", type="negative", multi_line=True)


def watch_marks(inputs: dict) -> None:
    """A field loses its red mark when the user changes it."""
    for element in inputs.values():
        element.on_value_change(lambda _, element=element: clear_mark(element))


async def confirm(question: str, yes: str, marker: str) -> bool:
    """Ask before an action. The buttons have the markers <marker>-yes and <marker>-no (for the tests)."""
    with ui.dialog() as dialog, ui.card():
        ui.label(question)
        with ui.row():
            ui.button(yes, on_click=lambda: dialog.submit(True)).props("no-caps").mark(f"{marker}-yes")
            ui.button("Cancel", on_click=lambda: dialog.submit(False)).props("no-caps flat").mark(f"{marker}-no")
    answer = await dialog
    dialog.delete()
    return bool(answer)


def run_write(action: Callable, inputs: dict, summary, what: str):
    """Run a write function with a connection. Return its result, or None after the problem is shown. An
    unexpected error is shown too, never only written to the log."""
    conn = connect()
    try:
        return action(conn)
    except ValidationError as e:
        show_problems(e, inputs, summary, what)
    except Exception as e:  # noqa: BLE001  (never fail without a message)
        log.exception("%s", what)
        show_problems(ValidationError([f"Unexpected error: {e}"]), inputs, summary, what)
    finally:
        conn.close()
    return None


def make_input(f: Field, suggestions: list[str]):
    caption = f.caption or label(f.name)
    if f.kind == "flag":
        return ui.checkbox(caption)
    if f.kind == "whole":
        return ui.number(caption, precision=0).classes("w-full")
    if f.kind == "number":
        return ui.number(caption, format="%.2f").classes("w-full")
    if f.kind == "textarea":
        return ui.textarea(caption).props("autogrow").classes("w-full")
    if f.kind == "suggest":
        return ui.input(caption, autocomplete=suggestions).classes("w-full")
    return ui.input(caption).classes("w-full")


def shown_value(f: Field, value):
    """The value as the input can show it. A number field cannot show an old text value; it shows empty."""
    if f.kind == "flag":
        return bool(value)
    if f.kind in ("whole", "number"):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return "" if value is None else str(value)


def master_screen(s: Screen) -> None:
    """Build a master data screen: header, filter, list, edit panel and buttons."""
    with ui.header().classes("items-center"):
        ui.label(s.title).classes("text-xl font-bold")
        ui.space()
        ui.link("Main menu", "/")

    conn = connect()
    try:
        suggestions = {f.name: f.suggest(conn) if f.suggest else [] for f in s.fields}
    finally:
        conn.close()

    # Layout (owner): the buttons, then the form, then the list.
    state = {"id": None, "stored": {}, "unshown": set()}
    with ui.card().classes("w-full"):
        panel_title = ui.label("").classes("text-lg font-bold")
        with ui.row().classes("items-center"):
            save_button = ui.button("Save").props("no-caps").mark("save")
            ui.button(f"New {s.noun}", on_click=lambda: new_row()).props("no-caps flat")
            ui.button("Undo", on_click=lambda: load_row(state["id"]) if state["id"] else new_row()).props("no-caps flat")
            flag_button = ui.button("").props("no-caps flat color=negative").mark("flag") if s.flag else None
            if s.no_delete_text:
                ui.label(s.no_delete_text).classes("text-sm opacity-70")
        problems = ui.label("").classes("text-negative")
        flag_text = ui.label("").classes("font-bold text-warning")
        inputs = {}
        with ui.grid(columns=2).classes("w-full gap-x-6"):
            for f in s.fields:
                inputs[f.name] = make_input(f, suggestions[f.name])
    show_extra = s.extra() if s.extra else None

    with ui.row().classes("items-center gap-6"):
        search = ui.input("Filter the list").props("clearable dense").classes("w-80")
        show_flagged = ui.checkbox(s.flag.show_caption) if s.flag else None
    columns = [{"name": c, "label": "No." if c == s.key else label(c), "field": c, "align": "left", "sortable": True}
               for c in s.columns]
    grid = ui.table(columns=columns, rows=[], row_key=s.key, selection="single", pagination=12).props("dense").mark("list")
    grid.classes("w-full").bind_filter_from(search, "value")
    watch_marks(inputs)

    def flagged_rows(rows):
        flags = [f.name for f in s.fields if f.kind == "flag"] + ([s.flag.name] if s.flag else [])
        return [{**r, **{c: ("Yes" if r.get(c) else "") for c in flags if c in r}} for r in rows]

    def refresh_grid() -> None:
        conn = connect()
        try:
            grid.rows = flagged_rows(s.load(conn, bool(show_flagged.value) if show_flagged else False))
        finally:
            conn.close()

    def set_values(row: dict) -> None:
        state["unshown"] = set()
        for f in s.fields:
            value = row.get(f.name, f.default)
            shown = shown_value(f, value)
            if f.kind in ("whole", "number") and value is not None and shown is None:
                state["unshown"].add(f.name)          # keep the old value unless the user types a new one
            inputs[f.name].value = shown
        problems.text = ""
        for element in inputs.values():
            clear_mark(element)

    def values() -> dict:
        result = {}
        for f in s.fields:
            value = inputs[f.name].value
            if f.name in state["unshown"] and value is None:
                value = state["stored"].get(f.name)
            result[f.name] = value
        return result

    def new_row() -> None:
        state["id"], state["stored"] = None, {}
        grid.selected = []
        panel_title.text = f"New {s.noun}"
        flag_text.text = ""
        set_values({})
        if flag_button:
            flag_button.disable()
        if show_extra:
            show_extra(None)

    def load_row(row_id) -> None:
        conn = connect()
        try:
            row = s.get(conn, row_id)
        finally:
            conn.close()
        if row is None:
            new_row()
            return
        state["id"], state["stored"] = row_id, row
        panel_title.text = f"{s.noun.capitalize()} {row_id}"
        set_values(row)
        if s.flag:
            flagged = bool(row.get(s.flag.name))
            flag_text.text = s.flag.flagged_text if flagged else ""
            flag_button.text = s.flag.restore_caption if flagged else s.flag.delete_caption
            flag_button.enable()
        if show_extra:
            show_extra(row_id)

    def on_save() -> None:
        row_id = run_write(lambda conn: s.save(conn, values(), state["id"]), inputs, problems,
                           f"The {s.noun} is not saved")
        if row_id is None:
            return
        ui.notify(f"{s.noun.capitalize()} {row_id} is saved.", type="positive")
        refresh_grid()
        load_row(row_id)                               # stays on the row, so a new wine can get its prices

    async def on_flag() -> None:
        row_id = state["id"]
        flagged = bool(state["stored"].get(s.flag.name))
        if not flagged and not await confirm(s.flag.question.format(id=row_id), s.flag.delete_caption, "flag"):
            return
        if run_write(lambda conn: s.flag.set(conn, row_id, not flagged) or True, inputs, problems,
                     f"The {s.noun} is not changed") is None:
            return
        ui.notify((s.flag.undone if flagged else s.flag.done).format(id=row_id), type="positive")
        refresh_grid()
        load_row(row_id)

    save_button.on_click(on_save)
    if flag_button:
        flag_button.on_click(on_flag)
    if show_flagged:
        show_flagged.on_value_change(lambda _: refresh_grid())
    grid.on_select(lambda e: load_row(e.selection[0][s.key]) if e.selection else None)
    refresh_grid()
    new_row()
