"""Master data read functions on a small hand-made database."""
from winedb.db import connect
from winedb.masterdata import get_item, list_items, list_warehouses


def test_items_sorted_by_code_and_one_item_by_id(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (item_id, item_code, name, vintage, country) VALUES (2, 'B', 'Vin Å', 2010, 'Frankrig'), (1, 'C', 'X', 2011, NULL)")
    assert [i["item_code"] for i in list_items(conn)] == ["B", "C"]
    assert get_item(conn, 2)["country"] == "Frankrig"   # data stays as it is
    assert get_item(conn, 99) is None


def test_warehouses_sorted_by_id(tmp_path):
    conn = connect(tmp_path / "t.db")
    conn.execute("INSERT INTO warehouses (warehouse_id, warehouse_name) VALUES (2, 'Fridge'), (1, 'Main')")
    assert list_warehouses(conn) == [{"warehouse_id": 1, "warehouse_name": "Main"}, {"warehouse_id": 2, "warehouse_name": "Fridge"}]
