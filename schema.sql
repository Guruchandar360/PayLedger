CREATE TABLE IF NOT EXISTS accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner TEXT NOT NULL,
  currency CHAR(3) NOT NULL CHECK (currency IN ('INR','USD','GBP')),
  balance_cents BIGINT NOT NULL DEFAULT 0,
  is_internal BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (is_internal OR balance_cents >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_funding_per_currency
  ON accounts (currency) WHERE is_internal;

CREATE TABLE IF NOT EXISTS transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type TEXT NOT NULL CHECK (type IN ('DEPOSIT','TRANSFER')),
  status TEXT NOT NULL DEFAULT 'POSTED',
  currency CHAR(3) NOT NULL,
  amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS txn_order ON transactions (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id BIGSERIAL PRIMARY KEY,
  txn_id UUID NOT NULL REFERENCES transactions(id),
  account_id UUID NOT NULL REFERENCES accounts(id),
  direction TEXT NOT NULL CHECK (direction IN ('DEBIT','CREDIT')),
  amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
  UNIQUE (txn_id, direction)
);
CREATE INDEX IF NOT EXISTS entries_by_account ON ledger_entries (account_id);

CREATE TABLE IF NOT EXISTS idempotency_keys (
  key TEXT PRIMARY KEY,
  request_hash TEXT NOT NULL,
  status_code INT,
  response_body JSONB,
  txn_id UUID REFERENCES transactions(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
