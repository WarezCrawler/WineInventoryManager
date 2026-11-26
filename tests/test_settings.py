import pytest

from winedb import settings
from winedb.settings import KEYS, has_values, load_settings, logo_path, move_old_files, save_settings, settings_path


def test_missing_file_gives_empty_known_keys(tmp_path):
    values = load_settings(tmp_path / "settings.json")
    assert set(values) == set(KEYS) and not any(values.values())
    assert not has_values(tmp_path / "settings.json")


def test_save_and_load_round_trip_with_special_characters(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    save_settings({"invoice_address": "Æble\nÅrhus", "invoice_pdf_folder": "C:\Faktura\\"}, path)
    values = load_settings(path)
    assert values["invoice_address"] == "Æble\nÅrhus" and values["invoice_pdf_folder"] == "C:\Faktura\\"
    assert has_values(path) and not list(path.parent.glob("*.tmp"))


def test_invalid_json_is_reported_not_ignored(tmp_path):
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_settings(tmp_path / "settings.json")


def test_path_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("WINE_SETTINGS_PATH", str(tmp_path / "x.json"))
    assert settings_path() == tmp_path / "x.json"


def test_settings_are_in_the_data_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("WINE_SETTINGS_PATH", raising=False)
    monkeypatch.setenv("WINE_DB_PATH", str(tmp_path / "data" / "wine_inventory.db"))
    assert settings_path() == tmp_path / "data" / "settings.json"
    assert "logo_file" in KEYS


def test_logo_is_a_png_or_svg_named_in_the_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("WINE_DB_PATH", str(tmp_path / "wine.db"))
    for name in ("logo.png", "logo.SVG", "logo.jpg"):
        (tmp_path / name).write_bytes(b"x")
    assert logo_path({"logo_file": "logo.png"}) == tmp_path / "logo.png"          # a name: in the data folder
    assert logo_path({"logo_file": " logo.SVG "}) == tmp_path / "logo.SVG"
    assert logo_path({"logo_file": str(tmp_path / "logo.png")}) == tmp_path / "logo.png"   # a full path
    assert logo_path({"logo_file": "logo.jpg"}) is None                           # only .png and .svg
    assert logo_path({"logo_file": "missing.png"}) is None
    assert logo_path({"logo_file": ""}) is None and logo_path({}) is None


def test_old_files_next_to_the_program_move_into_the_data_folder(monkeypatch, tmp_path):
    program = tmp_path / "program"
    program.mkdir()
    monkeypatch.setattr(settings, "app_dir", lambda: program)
    monkeypatch.delenv("WINE_SETTINGS_PATH", raising=False)
    monkeypatch.setenv("WINE_DB_PATH", str(program / "data" / "wine_inventory.db"))
    save_settings({"invoice_address": "Firm", "invoice_pdf_folder": "C:/pdf"}, program / "settings.json")
    (program / "logo.png").write_bytes(b"png")
    assert len(move_old_files()) == 2
    data = program / "data"
    assert not (program / "settings.json").exists() and not (program / "logo.png").exists()
    values = load_settings(data / "settings.json")
    assert (values["invoice_address"], values["invoice_pdf_folder"], values["logo_file"]) == ("Firm", "C:/pdf", "logo.png")
    assert (data / "logo.png").read_bytes() == b"png"
    assert move_old_files() == []                                               # once only


def test_the_move_never_overwrites_a_file_in_the_data_folder(monkeypatch, tmp_path):
    program = tmp_path / "program"
    (program / "data").mkdir(parents=True)
    monkeypatch.setattr(settings, "app_dir", lambda: program)
    monkeypatch.delenv("WINE_SETTINGS_PATH", raising=False)
    monkeypatch.setenv("WINE_DB_PATH", str(program / "data" / "wine_inventory.db"))
    save_settings({"invoice_address": "old"}, program / "settings.json")
    save_settings({"invoice_address": "new", "logo_file": "mine.svg"}, program / "data" / "settings.json")
    (program / "logo.png").write_bytes(b"old logo")
    move_old_files()
    assert load_settings(program / "data" / "settings.json")["invoice_address"] == "new"
    assert (program / "settings.json").exists()                                 # left where it is
    assert load_settings(program / "data" / "settings.json")["logo_file"] == "mine.svg"   # a set logo stays
