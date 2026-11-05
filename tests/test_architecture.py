"""The front-end stays in winedb/ui: nothing else imports the UI libraries, and nothing outside the UI
imports winedb.ui. This keeps the data and business code independent of the UI toolkit."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_LIBRARIES = {"nicegui", "webview", "fastapi", "starlette", "uvicorn", "PySide6", "tkinter"}


def imported_modules(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def non_ui_files():
    files = [p for p in (ROOT / "winedb").rglob("*.py") if (ROOT / "winedb" / "ui") not in p.parents]
    return files + list((ROOT / "migrate").rglob("*.py"))


def test_only_the_ui_folder_imports_ui_libraries():
    offenders = {str(p.relative_to(ROOT)): sorted(m for m in imported_modules(p) if m.split(".")[0] in UI_LIBRARIES)
                 for p in non_ui_files()}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_the_back_end_does_not_import_the_ui():
    offenders = [str(p.relative_to(ROOT)) for p in non_ui_files()
                 if any(m == "winedb.ui" or m.startswith("winedb.ui.") for m in imported_modules(p))
                 and p.name != "__main__.py"]
    assert offenders == []


def test_the_ui_folder_does_use_the_ui_library():
    assert "nicegui" in imported_modules(ROOT / "winedb" / "ui" / "app.py")
