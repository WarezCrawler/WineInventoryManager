import pytest

from migrate.column_map import COLUMN_MAP
from winedb.browse import table_counts, table_names, table_view
from winedb.db import connect


def test_lists_all_tables_with_counts(tmp_path):
    conn = connect(tmp_path / "wine.db")
    conn.execute("INSERT INTO tLagre (warehouse_name) VALUES ('Main'), ('Fridge')")
    assert table_names(conn) == sorted(COLUMN_MAP)
    assert dict(table_counts(conn))["tLagre"] == 2
    assert dict(table_counts(conn))["tKunder"] == 0


def test_table_view_returns_columns_rows_and_key(tmp_path):
    conn = connect(tmp_path / "wine.db")
    conn.execute("INSERT INTO tLagre (warehouse_name, comment) VALUES ('Main', 'c')")
    view = table_view(conn, "tLagre")
    assert view["columns"] == ["warehouse_id", "warehouse_name", "comment"]
    assert view["rows"] == [{"warehouse_id": 1, "warehouse_name": "Main", "comment": "c"}]
    assert view["total"] == 1 and view["key"] == "warehouse_id"
    assert table_view(conn, "tSettings")["key"] == "setting_key"


def test_limit_caps_rows_but_not_total(tmp_path):
    conn = connect(tmp_path / "wine.db")
    conn.executemany("INSERT INTO tLagre (warehouse_name) VALUES (?)", [("a",), ("b",), ("c",)])
    view = table_view(conn, "tLagre", limit=2)
    assert len(view["rows"]) == 2 and view["total"] == 3


def test_unknown_table_is_rejected(tmp_path):
    conn = connect(tmp_path / "wine.db")
    with pytest.raises(KeyError):
        table_view(conn, 'tLagre"; DROP TABLE tLagre; --')
