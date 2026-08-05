import sqlite3
from datetime import datetime

DB_PATH = 'wine.db'

def get_db_connection():
    """Creates and returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns dict-like rows for easier JSON conversion
    return conn

def get_user_by_email(email):
    """
    Fetches user details to determine their role (B2B vs B2C).
    This is required for injecting the context into the AI's system prompt.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, user_role FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

def search_inventory(keyword):
    """
    Searches inventory based on variety, flavor, or pairings.
    Returns a list of dictionaries for the AI Agent.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # SQLite does not have native semantic search (without FTS5).
        # We simulate it using a robust LIKE query across multiple descriptive columns.
        query = """
            SELECT sku, name, wine_type, varietal, region, flavor_profile, pairings, retail_price, wholesale_price, stock_level 
            FROM inventory 
            WHERE name LIKE ?
               OR varietal LIKE ?
               OR region LIKE ?
               OR wine_type LIKE ? 
               OR flavor_profile LIKE ? 
               OR pairings LIKE ?
        """
        search_term = f"%{keyword}%"
        cursor.execute(query, (search_term, search_term, search_term, search_term, search_term, search_term))
        
        results = [dict(row) for row in cursor.fetchall()]
        return results

def save_order(user_email, total_amount, cart_items):
    """
    Executes a database transaction to save the order and order items.
    cart_items expected format: [{'sku': 'SYRAH-01', 'quantity': 12, 'price': 25.00}]
    Returns the generated order_id if successful.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        try:
            # 1. Insert into orders table
            cursor.execute(
                "INSERT INTO orders (user_email, total_amount, status, order_date) VALUES (?, ?, ?, ?)",
                (user_email, total_amount, 'PENDING', datetime.now().isoformat())
            )
            order_id = cursor.lastrowid
            
            # 2. Insert into order_items and update inventory stock
            for item in cart_items:
                cursor.execute(
                    "INSERT INTO order_items (order_id, inventory_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (order_id, item['id'], item['quantity'], item['unit_price'])
                )
                
                # Deduct stock based on quantity purchased
                cursor.execute(
                    "UPDATE inventory SET stock_level = stock_level - ? WHERE id = ?",
                    (item['quantity'], item['id'])
                )
            
            # Transaction commits automatically if no exception is raised inside the 'with' block
            return order_id
            
        except sqlite3.Error as e:
            # Rollback is automatic on exception, but we log and re-raise it
            print(f"Database transaction failed: {e}")
            raise e