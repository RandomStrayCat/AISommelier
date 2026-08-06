import sqlite3
import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DB_PATH = 'wine.db'

def get_db_connection():
    """Creates and returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns dict-like rows for easier JSON conversion
    return conn

def get_user_by_email(email):
    """
    Fetches user details and merges their specific B2B or B2C profile data.
    Returns a comprehensive dictionary for Gemini's context window.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Step 1: Get the base user identity
        cursor.execute("SELECT id, email, user_role, is_active FROM users WHERE email = ?", (email,))
        user_row = cursor.fetchone()
        
        if not user_row or user_row['is_active'] == 0:
            return None  # User not found
            
        # Convert to a dictionary so we can add to it
        user_data = dict(user_row)
        
        # Step 2: Fetch the child entity based on the role
        if user_data['user_role'] == 'B2B':
            cursor.execute("SELECT company_name, contact_person_name, wholesale_tier, shipping_address FROM b2b_profiles WHERE user_id = ?", (user_data['id'],))
            profile_row = cursor.fetchone()
            if profile_row:
                user_data.update(dict(profile_row)) # Merges the B2B columns into user_data
                
        elif user_data['user_role'] == 'B2C':
            cursor.execute("SELECT first_name, last_name, preferred_wine_style, loyalty_points, shipping_address FROM b2c_profiles WHERE user_id = ?", (user_data['id'],))
            profile_row = cursor.fetchone()
            if profile_row:
                user_data.update(dict(profile_row)) # Merges the B2C columns into user_data
                
        return user_data

def search_inventory(search_term: str = "", user_role: str = "B2C", max_price: float = 9999.0):
    """
    Searches inventory based on name, varietal, region, wine type, flavor, or pairings.
    Returns a list of dictionaries for the AI Agent.
    Args:
        search_term: The search term for wine variety, flavor, pairing, etc. (e.g., "red", "steak", "fruity").
        user_role: The role of the user (e.g., "B2B" or "B2C") used to calculate pricing.
        max_price: The maximum price the user is willing to pay.
        
    Returns:
        A list of dictionaries containing the matching wines.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # SQLite does not have native semantic search (without FTS5).
        # We simulate it using a robust LIKE query across multiple descriptive columns.
        query = """
            SELECT id, sku, name, wine_type, varietal, region, flavor_profile, pairings, retail_price, wholesale_price, stock_level 
            FROM inventory 
            WHERE (name LIKE ?
               OR varietal LIKE ?
               OR region LIKE ?
               OR wine_type LIKE ? 
               OR flavor_profile LIKE ? 
               OR pairings LIKE ?)
        """
        search_term = f"%{search_term}%"
        params = [search_term, search_term, search_term, search_term, search_term, search_term]
        
        if max_price is not None:
            if user_role == 'B2B':
                query += " AND wholesale_price <= ?"
            else:
                query += " AND retail_price <= ?"
            
            params.append(max_price)
            
        cursor.execute(query, tuple(params))
        
        results = [dict(row) for row in cursor.fetchall()]
        return results

def save_order(user_email: str, total_amount: float, cart_items: list[dict], shipping_address: str):
    """
    Executes a database transaction to save the order and order items.
    Args:
        user_email: The ID/email of the user.
        total_amount: The total cost of the order.
        cart_items: A list of dictionaries containing id, sku, wine name, quantity, and unit_price.
        shipping_address: The full delivery address provided by the user.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        try:
            # 1. Insert into orders table
            cursor.execute(
                "INSERT INTO orders (user_email, total_amount, status, order_date, shipping_address) VALUES (?, ?, ?, ?, ?)",
                (user_email, total_amount, 'CONFIRMED', datetime.now().isoformat(), shipping_address)
            )
            order_id = cursor.lastrowid
            
            # 2. Insert into order_items and update inventory stock
            for item in cart_items:
                # SAFEGUARD: Check current stock first
                cursor.execute("SELECT stock_level FROM inventory WHERE id = ?", (item['id'],))
                row = cursor.fetchone()

                if not row:
                    raise ValueError(f"Item ID {item['id']} does not exist in inventory.")

                current_stock = row['stock_level']

                if current_stock < item['quantity']:
                    raise ValueError(f"Insufficient stock for item ID {item['id']}. Available: {current_stock}, Requested: {item['quantity']}")
                
                cursor.execute(
                    "INSERT INTO order_items (order_id, inventory_id, sku, name, quantity, unit_price) VALUES (?, ?, ?, ?, ?, ?)",
                    (order_id, item['id'], item['sku'], item['name'], item['quantity'], item['unit_price'])
                )
                
                # Deduct stock based on quantity purchased
                cursor.execute(
                    "UPDATE inventory SET stock_level = stock_level - ? WHERE id = ?",
                    (item['quantity'], item['id'])
                )
            
            conn.commit()
            
            user_info = get_user_by_email(user_email) 
            
            if user_info['user_role'] == 'B2B':
                customer_name = user_info.get('contact_person_name', 'Unknown')
                company = user_info.get('company_name', 'Unknown Company')
            else:
                customer_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
                company = "N/A (Individual Consumer)"           
            # ---------------------------------------------------------
            # NEW: MAKE.COM WEBHOOK TRIGGER
            # ---------------------------------------------------------
            # 1. Grab your unique Make.com Webhook URL (we'll set this up next)
            WEBHOOK_URL = os.getenv("MAKE_WEBHOOK_URL")
            
            # 2. Package the order data into a clean dictionary
            payload = {
                "order_id": order_id,
                "order_date": datetime.now().isoformat(),
                "customer": {
                    "name": customer_name,
                    "email": user_email,
                    "role": user_info['user_role'],
                    "company_name": company
                },
                "shipping": {
                    "address": shipping_address,
                    "status": "PENDING"
                },
                "financials": {
                    "total_amount": total_amount
                },
                "items": cart_items
            }
            
            # 3. Fire it off in the background
            try:
                # We use a quick timeout so it doesn't freeze the chat UI if Make.com is slow
                response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
                response.raise_for_status() # Raises an error if the webhook rejects it
                print(f"[DEBUG] Webhook sent successfully! Status: {response.status_code}")
            except requests.exceptions.RequestException as e:
                # We print the error but we DON'T raise it. 
                # The DB saved successfully, so we shouldn't ruin the user's chat experience!
                print(f"[WARNING] Order {order_id} saved, but webhook failed: {e}")
            
            return order_id
            
        except sqlite3.Error as e:
            # Rollback is automatic on exception, but we log and re-raise it
            print(f"Database transaction failed: {e}")
            raise e