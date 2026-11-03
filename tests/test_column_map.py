import re
from migrate.column_map import COLUMN_MAP


def test_new_names_are_unique_snake_case():
    for table, cols in COLUMN_MAP.items():
        new = list(cols.values())
        assert len(new) == len(set(new)), table
        assert all(re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in new), table
