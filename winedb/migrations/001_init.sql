-- 001: initial schema, a 1:1 copy of the Access data model with English column names.
-- Released migrations are never edited: a change is always a new numbered file.

CREATE TABLE tLagre (
  warehouse_id INTEGER PRIMARY KEY AUTOINCREMENT,
  warehouse_name TEXT, comment TEXT);

CREATE TABLE tKunder (
  customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_name TEXT NOT NULL COLLATE NOCASE, first_name TEXT, last_name TEXT,
  city TEXT, postal_code INTEGER DEFAULT 0, address TEXT, phone TEXT,
  is_hidden INTEGER DEFAULT 0, email TEXT, on_mailing_list INTEGER DEFAULT 0,
  comment TEXT);

CREATE TABLE tVinliste (
  wine_id INTEGER PRIMARY KEY AUTOINCREMENT,
  wine_code TEXT NOT NULL COLLATE NOCASE, name TEXT NOT NULL COLLATE NOCASE, vintage INTEGER NOT NULL,
  country TEXT, producer TEXT, region TEXT,
  wine_type TEXT COLLATE NOCASE, bottle_size TEXT COLLATE NOCASE, drink_by_year INTEGER, mature_year INTEGER,
  is_discontinued INTEGER DEFAULT 0, is_private INTEGER DEFAULT 0, comment TEXT);
CREATE UNIQUE INDEX wine_code ON tVinliste (wine_code);

CREATE TABLE tFaktura (
  invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER DEFAULT 0, is_closed INTEGER DEFAULT 0, comment TEXT,
  warehouse_id INTEGER, invoice_date TEXT, hide_subtotals INTEGER DEFAULT 0, is_deleted INTEGER DEFAULT 0);
CREATE INDEX tFaktura_warehouse_id ON tFaktura (warehouse_id);

CREATE TABLE tVinlager (
  stock_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT, wine_id INTEGER NOT NULL, quantity INTEGER DEFAULT 0, comment TEXT,
  warehouse_id INTEGER NOT NULL);
CREATE INDEX tVinlager_warehouse_id ON tVinlager (warehouse_id);

CREATE TABLE tVinlager_Salg (
  sales_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  wine_id INTEGER NOT NULL, created_at TEXT, quantity INTEGER DEFAULT 0, comment TEXT,
  invoice_id INTEGER NOT NULL, sales_price REAL DEFAULT 0, amount_ex_vat REAL DEFAULT 0,
  amount_incl_vat REAL DEFAULT 0, price_type TEXT COLLATE NOCASE, cost_price REAL DEFAULT 0,
  amount_cost REAL DEFAULT 0, vat_rate REAL DEFAULT 0, warehouse_id INTEGER NOT NULL,
  discount REAL NOT NULL DEFAULT 0);
CREATE INDEX tVinlager_Salg_warehouse_id ON tVinlager_Salg (warehouse_id);

CREATE TABLE tPrisliste_Cost (
  cost_price_id INTEGER PRIMARY KEY AUTOINCREMENT, wine_id INTEGER NOT NULL, price_type TEXT COLLATE NOCASE,
  cost_price REAL, test_delete INTEGER);

CREATE TABLE tPrisliste_Salg (
  sales_price_id INTEGER PRIMARY KEY AUTOINCREMENT, wine_id INTEGER NOT NULL, price_type TEXT COLLATE NOCASE,
  sales_price REAL, vat_rate REAL NOT NULL DEFAULT 0.25);

CREATE TABLE tSettings (
  setting_key TEXT NOT NULL PRIMARY KEY COLLATE NOCASE, setting_value TEXT, description TEXT);
