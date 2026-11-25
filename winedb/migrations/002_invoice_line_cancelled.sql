-- Owner decision 16 (2026-11-25): a wrong invoice line is cancelled, never deleted. Cancelling sets the
-- quantity and the amounts to 0 and this flag to 1; a cancelled line is never printed. The Access data is
-- still imported 1:1 into schema version 1; its lines read 0 here (not cancelled).
ALTER TABLE invoice_lines ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0;
