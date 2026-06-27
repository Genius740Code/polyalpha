import polyalpha

client = polyalpha.Client()

btc = client.markets.latest("BTC", "5m")

btc.print()

print(btc.volume)
print(btc.prices)
print(btc.url)