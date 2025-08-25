import pytest

def _kind(v: str | None) -> str:
    v = (v or "").lower()
    if v in ("topup", "пополнение"):
        return "topup"
    if v in ("debit", "списание"):
        return "debit"
    return v

@pytest.mark.asyncio
async def test_register_topup_debit_history(client, auth_headers):
    # стартовый баланс
    r = await client.get("/wallet/balance", headers=auth_headers)
    assert r.status_code == 200
    start_balance = r.json().get("balance")
    assert isinstance(start_balance, (int, float))

    # пополнение
    r = await client.post("/wallet/topup", json={"amount": 100}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text

    # баланс увеличился
    r = await client.get("/wallet/balance", headers=auth_headers)
    assert r.status_code == 200
    after_topup = r.json().get("balance")
    assert after_topup >= start_balance + 100 - 1e-6

    # действие со списанием (перевод)
    r = await client.post("/translate", json={"text": "hello", "target_lang": "ru"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    cost = r.json().get("cost")

    # баланс уменьшился
    r = await client.get("/wallet/balance", headers=auth_headers)
    assert r.status_code == 200
    after = r.json().get("balance")
    if cost is not None:
        assert after == pytest.approx(after_topup - cost)
    else:
        assert after <= after_topup

    # в истории есть пополнение и списание
    r = await client.get("/history/transactions", headers=auth_headers)
    assert r.status_code == 200, r.text
    txns = r.json()
    kinds = {_kind(t.get("type")) for t in txns}
    assert "topup" in kinds
    assert ("debit" in kinds) or (cost is None)

@pytest.mark.asyncio
async def test_translations_history(client, auth_headers):
    r = await client.post("/translate", json={"text": "test", "target_lang": "en"}, headers=auth_headers)
    assert r.status_code == 200, r.text

    r = await client.get("/history", headers=auth_headers)
    assert r.status_code == 200
    hist = r.json()
    assert isinstance(hist, list)
    assert any((i.get("text") or i.get("source_text")) for i in hist)
