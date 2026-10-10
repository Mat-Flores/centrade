from decimal import Decimal

# ruleid: centrade-float-for-money
price = float("1.5")
# ruleid: centrade-float-for-money
order_qty: float = 2.0
# ok: centrade-float-for-money
price = Decimal("1.5")
# ok: centrade-float-for-money
ratio = float("0.5")


def f(client):
    # ruleid: centrade-venue-order-call
    client.create_order("BTC/USDT", "limit", "buy", 1)
    # ruleid: centrade-venue-order-call
    client.exchange.place_order(1)
    # ok: centrade-venue-order-call
    client.fetch_order("1")
