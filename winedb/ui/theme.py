"""The colours of the screens from settings.json (step: testing phase, owner 2026-11-26)."""
from nicegui import ui

from winedb.settings import header_colours, load_settings


# The links in the heading bar take the colour of its text, so they can be read on any background colour.
LINK_CSS = ".q-header a { color: inherit; }\n"


def header_css(settings: dict) -> str:
    """CSS for the heading bar of every screen: the links always take the text colour of the bar; with the
    setting header_colour, also the background and a readable text colour."""
    colours = header_colours(settings)
    if not colours:
        return LINK_CSS
    background, text = colours
    return LINK_CSS + (f".q-header {{ background-color: {background} !important; color: {text} !important;"
                       f" border-bottom: 1px solid rgba(0, 0, 0, 0.12); }}\n")


def apply_theme() -> None:
    """Set the colour of the heading bar on all screens (the setting header_colour). Called once at start, so a
    change in settings.json counts from the next start."""
    try:
        settings = load_settings()
    except ValueError:
        settings = {}                            # a broken settings.json must not stop the program
    ui.add_css(header_css(settings), shared=True)
