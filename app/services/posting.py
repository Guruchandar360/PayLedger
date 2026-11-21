from sqlalchemy.orm import Session

from app.models import Account, LedgerEntry, Transaction


def post_entries(
    session: Session,
    type: str,
    currency: str,
    amount: int,
    debit_account: Account,
    credit_account: Account,
) -> Transaction:
    transaction = Transaction(type=type, currency=currency, amount_cents=amount)
    session.add(transaction)
    session.flush()

    session.add(
        LedgerEntry(
            txn_id=transaction.id,
            account_id=debit_account.id,
            direction="DEBIT",
            amount_cents=amount,
        )
    )
    debit_account.balance_cents -= amount

    session.add(
        LedgerEntry(
            txn_id=transaction.id,
            account_id=credit_account.id,
            direction="CREDIT",
            amount_cents=amount,
        )
    )
    credit_account.balance_cents += amount
    return transaction
