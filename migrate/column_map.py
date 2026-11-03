"""Access (Danish) -> SQLite (English) column names. Single source of truth for the
schema DDL and the data migration. COLUMN_MAP is keyed by the Access (source) table name;
TABLE_MAP gives the SQLite table name (migration 001).
Values are never renamed or translated, only table and column names."""

TABLE_MAP = {
    "tLagre": "warehouses",
    "tKunder": "customers",
    "tVinliste": "wines",
    "tFaktura": "invoices",
    "tVinlager": "stock_movements",
    "tVinlager_Salg": "invoice_lines",
    "tPrisliste_Cost": "cost_prices",
    "tPrisliste_Salg": "sales_prices",
    "tSettings": "settings",
}

COLUMN_MAP = {
    "tLagre": {
        "Lager_ID": "warehouse_id",
        "LagerNavn": "warehouse_name",
        "Kommentar": "comment",
    },
    "tKunder": {
        "Kunde_ID": "customer_id",
        "Kundenavn": "customer_name",
        "Fornavn": "first_name",
        "Efternavn": "last_name",
        "By": "city",
        "Post_nr": "postal_code",
        "Adresse": "address",
        "Tlf": "phone",
        "Skjul": "is_hidden",
        "Mailadr": "email",
        "Maillist": "on_mailing_list",
        "Kommentar": "comment",
    },
    "tVinliste": {
        "Vin_ID": "wine_id",
        "Vin_UID": "wine_code",
        "Vin_Navn": "name",
        "Vin_Årgang": "vintage",
        "Vin_Land": "country",
        "Vin_Hus": "producer",
        "Vin_Område": "region",
        "Vin_Type": "wine_type",
        "Vin_Str": "bottle_size",
        "Vin_Udløb": "drink_by_year",
        "Vin_Moden": "mature_year",
        "Udgået": "is_discontinued",
        "Private": "is_private",
        "Vin_Kommentar": "comment",
    },
    "tFaktura": {
        "Fakt_ID": "invoice_id",
        "Kunde_ID": "customer_id",
        "Lukket": "is_closed",
        "Kommentar": "comment",
        "Lager_ID": "warehouse_id",
        "FakturaDato": "invoice_date",
        "HideSubTotals": "hide_subtotals",
        "Delete": "is_deleted",
    },
    "tVinlager": {
        "VinLager_ID": "stock_line_id",
        "Date_Create": "created_at",
        "Vin_ID": "wine_id",
        "Quantity": "quantity",
        "Kommentar": "comment",
        "Lager_ID": "warehouse_id",
    },
    "tVinlager_Salg": {
        "Vin_SalgID": "sales_line_id",
        "Vin_ID": "wine_id",
        "Date_Create": "created_at",
        "Quantity": "quantity",
        "Kommentar": "comment",
        "Fakt_ID": "invoice_id",
        "SalgsPris": "sales_price",              # unit price, VAT included
        "SamletPris": "amount_ex_vat",
        "SamletPris_mMoms": "amount_incl_vat",
        "PrisType": "price_type",
        "CostPris": "cost_price",               # unit cost
        "SamletCostPris": "amount_cost",
        "Momssats": "vat_rate",
        "Lager_ID": "warehouse_id",
        "Rabat": "discount",                    # VAT-included amount off the line
    },
    "tPrisliste_Cost": {
        "Id": "cost_price_id",
        "Vin_ID": "wine_id",
        "PrisType": "price_type",
        "CostPris": "cost_price",
        "test_slet": "test_delete",             # unused leftover, kept 1:1
    },
    "tPrisliste_Salg": {
        "Id": "sales_price_id",
        "Vin_ID": "wine_id",
        "PrisType": "price_type",
        "SalgsPris": "sales_price",
        "Momssats": "vat_rate",
    },
    "tSettings": {
        "Setting": "setting_key",
        "Value": "setting_value",
        "Description": "description",
    },
}
