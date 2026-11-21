"""The program is in British English (design doc §2): no Danish text in the program code or the schema.
The data is never translated, and migrate/ keeps the Access names of the source, so both are not checked."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DANISH_LETTERS = set("æøåÆØÅ")


def test_no_danish_letters_in_the_program_or_the_schema():
    files = list((ROOT / "winedb").rglob("*.py")) + list((ROOT / "winedb" / "migrations").glob("*.sql"))
    offenders = [f"{p.relative_to(ROOT)}:{n}" for p in files
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if DANISH_LETTERS & set(line)]
    assert offenders == []
