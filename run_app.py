"""Entry point of the packaged program (and of `python run_app.py`)."""
from multiprocessing import freeze_support

freeze_support()  # needed for the native window in a packaged .exe; must run first

from winedb.app import main  # noqa: E402

if __name__ in {"__main__", "__mp_main__"}:
    main()
