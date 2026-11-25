import sqlite3

import pytest

from migrate.column_map import COLUMN_MAP, TABLE_MAP
from winedb import config
from winedb.db import SchemaTooNewError, connect, latest_version, transaction


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
    assert tables(conn) == set(TABLE_MAP.values())
    assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version() >= 1


# Columns outside the 1:1 copy, added by later migrations (design doc §10, decision 16).
ADDED_COLUMNS = {"invoice_lines": ["is_deleted"]}


def columns(conn, table):
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_schema_version_1_columns_match_column_map(tmp_path):
    conn = connect(tmp_path / "wine.db", version=1)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    for access_table, mapping in COLUMN_MAP.items():
        assert columns(conn, TABLE_MAP[access_table]) == list(mapping.values()), access_table


def test_newest_schema_adds_only_the_decided_columns(tmp_path):
    conn = connect(tmp_path / "wine.db")
    for access_table, mapping in COLUMN_MAP.items():
        table = TABLE_MAP[access_table]
        assert columns(conn, table) == list(mapping.values()) + ADDED_COLUMNS.get(table, []), table


def test_a_database_stopped_at_version_1_is_upgraded_later_with_a_backup(tmp_path):
    db = tmp_path / "wine.db"
    conn = connect(db, version=1)
    conn.execute("INSERT INTO invoice_lines (item_id, invoice_id, warehouse_id, quantity) VALUES (1, 1, 1, 6)")
    conn.close()
    conn = connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == latest_version()
    assert tuple(conn.execute("SELECT quantity, is_deleted FROM invoice_lines").fetchone()) == (6, 0)   # old lines: not cancelled
    assert list(tmp_path.glob("wine.db.bak-*"))


def test_an_unknown_version_is_refused(tmp_path):
    with pytest.raises(ValueError):
        connect(tmp_path / "wine.db", version=latest_version() + 1)


def test_second_start_changes_nothing(tmp_path):
    db = tmp_path / "wine.db"
    conn = connect(db)
    conn.execute("INSERT INTO warehouses (warehouse_name) VALUES ('Main')")
    conn.close()
    conn = connect(db)
    assert conn.execute("SELECT warehouse_name FROM warehouses").fetchone()[0] == "Main"
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
    conn.execute("INSERT INTO items (item_code, name, vintage) VALUES ('SAbSe_RA10', 'x', 2010)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO items (item_code, name, vintage) VALUES ('sabse_ra10', 'y', 2011)")


def test_db_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("WINE_DB_PATH", str(tmp_path / "x.db"))
    assert config.db_path() == tmp_path / "x.db"
    monkeypatch.delenv("WINE_DB_PATH")
    assert config.db_path().name == "wine_inventory.db" and config.db_path().parent.name == "data"


def test_transaction_saves_all_or_nothing(tmp_path):
    conn = connect(tmp_path / "wine.db")
    with transaction(conn):
        conn.execute("INSERT INTO warehouses (warehouse_name) VALUES ('A')")
    with pytest.raises(RuntimeError):
        with transaction(conn):
            conn.execute("INSERT INTO warehouses (warehouse_name) VALUES ('B')")
            raise RuntimeError("stop")
    assert [r[0] for r in conn.execute("SELECT warehouse_name FROM warehouses")] == ["A"]
