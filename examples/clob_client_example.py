"""
CLOB Client Example — Demonstrates Polymarket CLOB API integration.

This example shows how to use the ClobClient to interact with the
Polymarket CLOB for order placement, cancellation, and orderbook queries.

Usage
-----
    python examples/clob_client_example.py

Note
----
This example uses simulated responses for demonstration purposes.
To use with real API, provide valid credentials.
"""

import polyalpha
from polyalpha.trading.clob_client import ClobClient


def main():
    """Demonstrate ClobClient functionality."""
    
    print("=" * 60)
    print("CLOB Client Example")
    print("=" * 60)
    
    # Initialize CLOB client
    # In production, use real credentials from environment variables
    client = ClobClient(
        api_key="your-api-key",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        base_url="https://clob.polymarket.com",
        timeout=10,
        retry_attempts=3,
        retry_delay=1.0,
        simulate=True,  # Set to False for real trading
    )
    
    print("\n✓ CLOB Client initialized")
    print(f"  Base URL: {client.base_url}")
    print(f"  Timeout: {client.timeout}s")
    print(f"  Retry attempts: {client.retry_attempts}")
    
    # Get wallet address
    address = client._get_address()
    print(f"\n✓ Wallet address: {address}")
    
    # Get account balance
    print("\n" + "-" * 60)
    print("Account Balance")
    print("-" * 60)
    balance = client.get_balance()
    print(f"  Address: {balance['address']}")
    print(f"  USDC Balance: ${balance['usdc_balance']:.2f}")
    print(f"  Allowance: ${balance['allowance']:.2f}")
    
    # Get orderbook for a token
    print("\n" + "-" * 60)
    print("Orderbook")
    print("-" * 60)
    token_id = "token-123"
    orderbook = client.get_orderbook(token_id)
    
    print(f"  Token ID: {token_id}")
    print("\n  Bids:")
    for i, (price, size) in enumerate(orderbook["bids"][:5], 1):
        print(f"    {i}. ${price:.4f} × {size:.2f}")
    
    print("\n  Asks:")
    for i, (price, size) in enumerate(orderbook["asks"][:5], 1):
        print(f"    {i}. ${price:.4f} × {size:.2f}")
    
    # Place a buy order
    print("\n" + "-" * 60)
    print("Place Buy Order")
    print("-" * 60)
    buy_order = client.place_order(
        token_id=token_id,
        side="buy",
        price=0.55,
        size=10.0,
        order_type="limit",
    )
    print(f"  Order ID: {buy_order['order_id']}")
    print(f"  Status: {buy_order['status']}")
    print(f"  Side: {buy_order['side']}")
    print(f"  Price: ${buy_order['price']:.4f}")
    print(f"  Size: {buy_order['size']:.2f}")
    
    # Place a sell order
    print("\n" + "-" * 60)
    print("Place Sell Order")
    print("-" * 60)
    sell_order = client.place_order(
        token_id=token_id,
        side="sell",
        price=0.56,
        size=5.0,
        order_type="limit",
    )
    print(f"  Order ID: {sell_order['order_id']}")
    print(f"  Status: {sell_order['status']}")
    print(f"  Side: {sell_order['side']}")
    print(f"  Price: ${sell_order['price']:.4f}")
    print(f"  Size: {sell_order['size']:.2f}")
    
    # Get order status
    print("\n" + "-" * 60)
    print("Order Status")
    print("-" * 60)
    order_id = buy_order["order_id"]
    status = client.get_order_status(order_id)
    print(f"  Order ID: {status['order_id']}")
    print(f"  Status: {status['status']}")
    print(f"  Filled Size: {status['filled_size']:.2f}")
    print(f"  Average Price: ${status['avg_price']:.4f}")
    
    # Cancel order
    print("\n" + "-" * 60)
    print("Cancel Order")
    print("-" * 60)
    cancel_response = client.cancel_order(order_id)
    print(f"  Order ID: {cancel_response['order_id']}")
    print(f"  Status: {cancel_response['status']}")
    
    # Close client
    print("\n" + "-" * 60)
    client.close()
    print("✓ CLOB Client closed")
    
    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


def advanced_example():
    """Demonstrate advanced CLOB client usage."""
    
    print("\n" + "=" * 60)
    print("Advanced CLOB Client Example")
    print("=" * 60)
    
    client = ClobClient(
        api_key="your-api-key",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    
    # Market order (no price specified, executes immediately)
    print("\n" + "-" * 60)
    print("Market Order")
    print("-" * 60)
    market_order = client.place_order(
        token_id="token-456",
        side="buy",
        price=0.55,  # Still need price for market orders
        size=20.0,
        order_type="market",
    )
    print(f"  Market Order ID: {market_order['order_id']}")
    print(f"  Type: market")
    
    # Order with custom nonce
    print("\n" + "-" * 60)
    print("Order with Custom Nonce")
    print("-" * 60)
    import time
    custom_nonce_order = client.place_order(
        token_id="token-789",
        side="sell",
        price=0.58,
        size=15.0,
        order_type="limit",
        nonce=int(time.time() * 1000),
    )
    print(f"  Order ID: {custom_nonce_order['order_id']}")
    print(f"  Custom nonce used")
    
    # Multiple orderbook queries
    print("\n" + "-" * 60)
    print("Multiple Orderbook Queries")
    print("-" * 60)
    tokens = ["token-1", "token-2", "token-3"]
    for token in tokens:
        orderbook = client.get_orderbook(token)
        best_bid = orderbook["bids"][0] if orderbook["bids"] else None
        best_ask = orderbook["asks"][0] if orderbook["asks"] else None
        print(f"  {token}:")
        if best_bid:
            print(f"    Best Bid: ${best_bid[0]:.4f} × {best_bid[1]:.2f}")
        if best_ask:
            print(f"    Best Ask: ${best_ask[0]:.4f} × {best_ask[1]:.2f}")
    
    # Bulk order placement
    print("\n" + "-" * 60)
    print("Bulk Order Placement")
    print("-" * 60)
    orders = []
    for i in range(3):
        order = client.place_order(
            token_id=f"token-{i}",
            side="buy",
            price=0.50 + (i * 0.01),
            size=10.0,
            order_type="limit",
        )
        orders.append(order)
        print(f"  Order {i+1}: {order['order_id']}")
    
    # Cancel all orders
    print("\n" + "-" * 60)
    print("Cancel All Orders")
    print("-" * 60)
    for order in orders:
        client.cancel_order(order["order_id"])
        print(f"  Cancelled: {order['order_id']}")
    
    client.close()
    print("\n✓ Advanced example completed")


def error_handling_example():
    """Demonstrate error handling in CLOB client."""
    
    print("\n" + "=" * 60)
    print("Error Handling Example")
    print("=" * 60)
    
    client = ClobClient(
        api_key="your-api-key",
        private_key="your-private-key",
        rpc_url="https://polygon-rpc.com",
        simulate=True,
    )
    
    # Invalid side
    print("\n" + "-" * 60)
    print("Invalid Order Side")
    print("-" * 60)
    try:
        client.place_order(
            token_id="token-123",
            side="invalid",
            price=0.55,
            size=10.0,
        )
    except ValueError as e:
        print(f"  ✓ Caught ValueError: {e}")
    
    # Invalid order type
    print("\n" + "-" * 60)
    print("Invalid Order Type")
    print("-" * 60)
    try:
        client.place_order(
            token_id="token-123",
            side="buy",
            price=0.55,
            size=10.0,
            order_type="invalid",
        )
    except ValueError as e:
        print(f"  ✓ Caught ValueError: {e}")
    
    client.close()
    print("\n✓ Error handling example completed")


if __name__ == "__main__":
    # Run basic example
    main()
    
    # Run advanced example
    advanced_example()
    
    # Run error handling example
    error_handling_example()
