from uuid import UUID

from sqlalchemy import func, select

from app.models import LedgerEntry, Transaction
from helpers import account, assert_ledger_consistent, balance, concurrently, deposit, transfer, transfer_body


def test_50_competing_transfers(app, client, live_url):
    sender = account(client)
    receivers = [account(client, owner=f"University {index}") for index in range(5)]
    assert deposit(client, sender, 100_000).status_code == 201

    requests = [
        ("/transfers", transfer_body(sender, receivers[index % 5], 4_000), f"competing-{index}")
        for index in range(50)
    ]
    responses = concurrently(live_url, requests)
    assert sorted(response.status_code for response in responses) == [201] * 25 + [422] * 25
    assert all(
        response.json()["error"]["code"] == "INSUFFICIENT_FUNDS"
        for response in responses
        if response.status_code == 422
    )
    assert balance(client, sender) == 0
    assert sum(balance(client, receiver) for receiver in receivers) == 100_000
    with app.state.sessions() as session:
        assert_ledger_consistent(session)


def test_10_requests_with_the_same_key(app, client, live_url):
    sender, receiver = account(client), account(client, owner="University")
    assert deposit(client, sender, 100_000).status_code == 201

    key = "same-transfer-key"
    request = ("/transfers", transfer_body(sender, receiver, 80_000), key)
    responses = concurrently(live_url, [request] * 10)
    assert all(response.status_code == 201 for response in responses)
    assert len({response.content for response in responses}) == 1
    assert sum(response.headers.get("Idempotent-Replay") == "true" for response in responses) == 9
    transaction_id = UUID(responses[0].json()["transaction_id"])
    assert balance(client, sender) == 20_000
    assert balance(client, receiver) == 80_000
    with app.state.sessions() as session:
        transfers = session.scalars(select(Transaction).where(Transaction.type == "TRANSFER")).all()
        assert [row.id for row in transfers] == [transaction_id]
        assert session.scalar(
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.txn_id == transaction_id)
        ) == 2
        assert_ledger_consistent(session)

    conflict = transfer(client, sender, receiver, 70_000, key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
