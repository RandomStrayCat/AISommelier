import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------------------------------------------------
# PHASE 1: CONNECT TO GOOGLE SHEETS
# ---------------------------------------------------------
# This tells Google what permissions our script has (Sheets and Drive)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Load the "password" file you got from Google Cloud
creds = ServiceAccountCredentials.from_json_keyfile_name('google_credentials.json', scope)
client = gspread.authorize(creds)

# Open your specific spreadsheet and select "Sheet1"
sheet = client.open('Content Record').sheet1

# Get all the SKUs currently in the sheet (assuming SKU is in Column A / Index 1)
# This creates a list we can check against later.
existing_skus = sheet.col_values(1) 


# ---------------------------------------------------------
# PHASE 2: CONNECT TO YOUR WINE DATABASE
# ---------------------------------------------------------
# Connect to the local SQLite database where your table lives
conn = sqlite3.connect('wine.db')
cursor = conn.cursor()

# Pull the specific columns we want to send to the content pipeline
# We don't need prices for social media, just the descriptive data!
cursor.execute("SELECT sku, name, wine_type, varietal, region, flavor_profile, pairings FROM inventory")
db_inventory = cursor.fetchall()


# ---------------------------------------------------------
# PHASE 3: YOUR SCENARIO 1 LOGIC 
# ---------------------------------------------------------
new_rows_to_add = []

# This is exactly what you wrote: "For item in items"
for item in db_inventory:
    sku = item[0] # The SKU is the first piece of data in our row
    
    # "If SKU NOT in sheet:"
    if sku not in existing_skus:
        # Add it to our staging list
        new_rows_to_add.append(list(item))


# ---------------------------------------------------------
# PHASE 4: EXECUTE THE UPDATE
# ---------------------------------------------------------
# If we found new rows, push them to the Google Sheet all at once
if new_rows_to_add:
    sheet.append_rows(new_rows_to_add)
    print(f"Success: Added {len(new_rows_to_add)} new wines to Sheet 1!")
else:
    print("Database and Sheet are fully synced. No new SKUs to add.")

# Close the database connection cleanly
conn.close()