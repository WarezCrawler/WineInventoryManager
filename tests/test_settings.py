import pytest

from winedb.settings import KEYS, has_values, load_settings, save_settings, settings_path


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
