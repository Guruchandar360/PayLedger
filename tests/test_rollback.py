from unittest.mock import patch

from sqlalchemy import func, select

from app.models import IdempotencyKey, LedgerEntry, Transaction
from app.services import posting
from helpers import account, assert_ledger_consistent, balance, deposit, transfer


def test_crash_between_debit_and_credit(app, client, monkeypatch):
    sender, receiver = account(client), account(client, owner="University")
    assert deposit(client, sender, 100_000).status_code == 201
    key = "crash-and-retry"
    original_post = posting.post_entries
    flushed_debit = []

    def fail_after_debit(session, *args, **kwargs):
        add = session.add

        def intercept_credit(instance):
            if isinstance(instance, LedgerEntry) and instance.direction == "CREDIT":
                session.flush()
                flushed_debit.append(instance.txn_id)
                raise RuntimeError("Injected failure after the debit was flushed")
            return add(instance)

        with patch.object(session, "add", side_effect=intercept_credit):
            return original_post(session, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(posting, "post_entries", fail_after_debit)
        response = transfer(client, sender, receiver, 80_000, key)
        assert response.status_code == 500
    assert len(flushed_debit) == 1

    assert balance(client, sender) == 100_000
    assert balance(client, receiver) == 0
    with app.state.sessions() as session:
        assert session.get(Transaction, flushed_debit[0]) is None
        assert session.scalar(select(func.count()).select_from(Transaction)) == 1  # Seed deposit only.
        assert session.scalar(select(func.count()).select_from(LedgerEntry)) == 2
        assert session.get(IdempotencyKey, key) is None
        assert_ledger_consistent(session)

    response = transfer(client, sender, receiver, 80_000, key)
    assert response.status_code == 201
    assert transfer(client, sender, receiver, 80_000, key).content == response.content
    assert balance(client, sender) == 20_000
    assert balance(client, receiver) == 80_000
    with app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Transaction)) == 2
        assert_ledger_consistent(session)
