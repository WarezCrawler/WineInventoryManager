"""User-friendly names for database columns (Functionality.md 10.4). Every screen takes its column
headings from here, so a name changes in one place. The database names stay technical."""

LABELS = {
    "invoice_id": "Invoice no.",
    "customer_id": "Customer no.",
    "customer_name": "Customer name",
    "is_deleted": "Deleted",
}


def label(column: str) -> str:
    """Return the user-friendly name of a column, or the column name if it has none yet."""
    return LABELS.get(column, column)
