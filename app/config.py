import os

DEFAULT_DATABASE_URL = "postgresql+psycopg://payledger:payledger-local@127.0.0.1:55436/payledger"
CURRENCIES = ("INR", "USD", "GBP")
MAX_AMOUNT = 10**12
MAX_BALANCE = 10**15


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
