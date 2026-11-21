"""User-friendly names for database columns (Functionality.md 10.4). Every screen takes its
headings from here, so a name changes in one place. The database names stay technical."""

LABELS = {
    "invoice_id": "Invoice no.",
    "customer_id": "Customer no.",
    "customer_name": "Customer name",
    "is_deleted": "Deleted",
    "item_id": "Wine",
    "item_code": "Wine code",
    "name": "Name",
    "vintage": "Vintage",
    "producer": "Producer",
    "country": "Country",
    "bottle_size": "Bottle size",
    "item_type": "Type",
    "warehouse_id": "Warehouse",
    "stock_line_id": "Movement no.",
    "created_at": "Date",
    "quantity": "Quantity",
    "comment": "Comment",
}


def label(column: str) -> str:
    """Return the user-friendly name of a column, or the column name if it has none yet."""
    return LABELS.get(column, column)

