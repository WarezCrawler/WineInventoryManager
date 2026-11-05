from multiprocessing import freeze_support

freeze_support()

from winedb.ui.app import main  # noqa: E402

if __name__ in {"__main__", "__mp_main__"}:
    main()
