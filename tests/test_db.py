import sqlite3

import pytest

from migrate.column_map import COLUMN_MAP
from winedb import config
from winedb.db import SchemaTooNewError, connect, latest_version


def tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def make_migrations(directory, **files):
    directory.mkdir(exist_ok=True)
    for name, sql in files.items():
        (directory / f"{name}.sql").write_text(sql, encoding="utf-8")
    return directory


def test_first_start_creates_the_database(tmp_path):
    db = tmp_path / "sub" / "wine.db"  # the folder does not exist either
    conn = connect(db)
    assert db.exists()
    assert tables(conn) == set(COLUMN_MAP)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version() >= 1


def test_schema_columns_match_column_map(tmp_path):
    conn = connect(tmp_path / "wine.db")
    for table, mapping in COLUMN_MAP.items():
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
        assert cols == list(mapping.values()), table


def test_second_start_changes_nothing(tmp_path):
    db = tmp_path / "wine.db"
    conn = connect(db)
    conn.execute("INSERT INTO tLagre (warehouse_name) VALUES ('Main')")
    conn.close()
    conn = connect(db)
    assert conn.execute("SELECT warehouse_name FROM tLagre").fetchone()[0] == "Main"
    assert list(tmp_path.glob("*.bak-*")) == []  # no backup when nothing is upgraded


def test_newer_database_is_refused_and_untouched(tmp_path):
    db = tmp_path / "wine.db"
    connect(db).close()
    raw = sqlite3.connect(db)
    raw.execute("PRAGMA user_version = 99")
    raw.close()
    before = db.read_bytes()
    with pytest.raises(SchemaTooNewError):
        connect(db)
    assert db.read_bytes() == before


def test_upgrade_applies_only_new_scripts_and_backs_up(tmp_path):
    first = "CREATE TABLE a (id INTEGER PRIMARY KEY, x TEXT);"
    v1 = make_migrations(tmp_path / "m1", **{"001_init": first})
    db = tmp_path / "wine.db"
    conn = connect(db, v1)
    conn.execute("INSERT INTO a (x) VALUES ('keep')")
    conn.close()

    v2 = make_migrations(tmp_path / "m2", **{"001_init": first, "002_add_y": "ALTER TABLE a ADD COLUMN y TEXT;"})
    conn = connect(db, v2)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
    assert [r["name"] for r in conn.execute("PRAGMA table_info(a)")] == ["id", "x", "y"]
    assert conn.execute("SELECT x FROM a").fetchone()[0] == "keep"
    backups = list(tmp_path.glob("wine.db.bak-*"))
    assert len(backups) == 1
    old = sqlite3.connect(backups[0])  # the backup is the version-1 database
    assert old.execute("PRAGMA user_version").fetchone()[0] == 1
    old.close()


def test_failed_migration_rolls_back(tmp_path):
    first = "CREATE TABLE a (id INTEGER PRIMARY KEY);"
    v1 = make_migrations(tmp_path / "m1", **{"001_init": first})
    db = tmp_path / "wine.db"
    connect(db, v1).close()
    bad = make_migrations(tmp_path / "m2", **{"001_init": first, "002_bad": "CREATE TABLE b (id INTEGER); THIS IS NOT SQL;"})
    with pytest.raises(sqlite3.Error):
        connect(db, bad)
    conn = connect(db, v1)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert tables(conn) == {"a"}  # table b from the failed script is gone


def test_migration_numbering_gap_is_rejected(tmp_path):
    gap = make_migrations(tmp_path / "m", **{"001_a": "SELECT 1;", "003_c": "SELECT 1;"})
    with pytest.raises(ValueError):
        connect(tmp_path / "wine.db", gap)


def test_wine_code_is_unique_ignoring_case(tmp_path):
    conn = connect(tmp_path / "wine.db")
    conn.execute("INSERT INTO tVinliste (wine_code, name, vintage) VALUES ('SAbSe_RA10', 'x', 2010)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO tVinliste (wine_code, name, vintage) VALUES ('sabse_ra10', 'y', 2011)")


def test_db_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WINE_DB_PATH", str(tmp_path / "x.db"))
    assert config.db_path() == tmp_path / "x.db"
    monkeypatch.delenv("WINE_DB_PATH")
    assert config.db_path().name == "wine_inventory.db" and config.db_path().parent.name == "data"
