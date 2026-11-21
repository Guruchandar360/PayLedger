import random
from uuid import uuid4

from helpers import account, assert_ledger_consistent, balance, concurrently, deposit, transfer_body


def test_opposite_direction_transfers(app, client, live_url):
    first, second = account(client), account(client)
    for account_id in (first, second):
        assert deposit(client, account_id, 100_000).status_code == 201

    requests = [
        ("/transfers", transfer_body(sender, receiver, 1_000), uuid4().hex)
        for _ in range(20)
        for sender, receiver in ((first, second), (second, first))
    ]
    responses = concurrently(live_url, requests)
    assert all(response.status_code == 201 for response in responses)
    assert balance(client, first) == balance(client, second) == 100_000
    with app.state.sessions() as session:
        assert_ledger_consistent(session)


def test_ledger_invariants_after_mixed_workload(app, client, live_url):
    randomizer = random.Random(746)
    currencies = ("INR", "GBP", "USD")
    accounts = {currency: [account(client, currency=currency) for _ in range(3)] for currency in currencies}
    for account_ids in accounts.values():
        for account_id in account_ids:
            assert deposit(client, account_id, 100_000).status_code == 201

    requests = []
    for index in range(36):
        group = accounts[randomizer.choice(currencies)]
        amount = randomizer.randint(1, 1_000)
        if index % 2 == 0:
            requests.append(("/deposits", {"account_id": randomizer.choice(group), "amount_cents": amount}, uuid4().hex))
        else:
            sender, receiver = randomizer.sample(group, 2)
            requests.append(("/transfers", transfer_body(sender, receiver, amount), uuid4().hex))

    responses = concurrently(live_url, requests)
    assert all(response.status_code == 201 for response in responses)
    with app.state.sessions() as session:
        assert_ledger_consistent(session)
