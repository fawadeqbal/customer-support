"""
The lookup_order tool.

The handbook (RAG) answers questions about POLICIES. Questions about ONE customer's
order need live data, so the model gets a tool: "where is order SE10482931?" ->
the model calls lookup_order -> we query the orders table -> the model answers from it.
"""
import json
import re

from app.db.repositories.orders import OrderRepository

ORDER_NUMBER = re.compile(r"\bSE[\s-]?\d{8}\b", re.I)

SPEC = {
    "name": "lookup_order",
    "description": (
        "Look up the current status of a ShopEase order: status, items, total, payment method, "
        "city, expected delivery date, courier and tracking number. Use it whenever the customer "
        "asks about a specific order and has given an order number."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "order_number": {
                "type": "string",
                "description": "Order number: 'SE' followed by 8 digits, e.g. SE10482931",
            }
        },
        "required": ["order_number"],
    },
}

_orders = OrderRepository()


def lookup_order(order_number):
    number = re.sub(r"[\s-]", "", str(order_number)).upper()
    if not re.fullmatch(r"SE\d{8}", number):
        return {"error": "That doesn't look like an order number. It should be SE followed by 8 digits."}
    row = _orders.find(number)
    if not row:
        return {"error": f"No order found with number {number}."}
    row["placed_at"] = row["placed_at"].strftime("%d %b %Y")
    if row["expected_delivery"]:
        row["expected_delivery"] = row["expected_delivery"].strftime("%d %b %Y")
    return row


def run(arguments):
    return lookup_order(arguments.get("order_number", ""))


def prefetch(question):
    """For models WITHOUT tool calling: if the message contains an order number,
    look it up ourselves and hand the result to the model as extra context."""
    found = ORDER_NUMBER.search(question)
    if not found:
        return ""
    return f"Order lookup result for {found.group(0)}: {json.dumps(lookup_order(found.group(0)), default=str)}"
