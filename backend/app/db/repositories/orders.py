"""All SQL for orders."""
from app.db.connection import connect


class OrderRepository:
    def find(self, order_no):
        with connect() as conn:
            return conn.execute("SELECT * FROM orders WHERE order_no = %s", (order_no,)).fetchone()
