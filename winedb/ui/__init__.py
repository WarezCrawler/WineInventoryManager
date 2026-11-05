"""The front-end: everything the user sees lives in this folder (pages, dialogs, labels).

It is the only part of the program that imports the UI libraries (NiceGUI, pywebview). The rest of
winedb (config, db, settings, browse, logic) and migrate/ know nothing about the UI, so the UI toolkit
can be replaced without touching the data and business code. tests/test_architecture.py enforces this.
"""
