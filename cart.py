def total(prices):
    if any(price < 0 for price in prices):
        raise ValueError("Negative prices are invalid")
    if not prices:
        return 0
    subtotal = sum(prices)
    shipping = 0 if subtotal > 1000 else 50
    return subtotal + shipping
