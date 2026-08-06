from dotenv import load_dotenv
from google import genai
import textwrap
import traceback
import streamlit as st
# Import the tools we built
from database import search_inventory, save_order

# Load environment variables from your .env file
load_dotenv()

# Initialize the Gemini Client
# Tell Streamlit to only run this function once and hold it in memory forever
@st.cache_resource
def get_genai_client():
    # Initialize your client however you were doing it before
    return genai.Client()

# Now, grab the cached client instead of creating a new one
client = get_genai_client()

# 1. Define the System Prompt (The Persona and Guardrails)
# This is the absolute law the AI must follow.
BASE_SYSTEM_INSTRUCTION = """
You are the AI Sommelier for Wine Place. Your primary job is to assist customers in finding wines and placing orders.

CRITICAL RULES:
1. You must ONLY recommend wines that are returned by the `search_inventory` tool. NEVER invent, guess, or hallucinate wine names, vintages, or prices.
2. If a customer asks about stock or prices, always use the `search_inventory` tool to get real-time data. Pass the keywords one at a time to the `search_inventory` tool.
3. Make sure to ask for clear confirmation from the user before using the `save_order` tool. When a customer explicitly confirms they want to purchase specific wines and quantities, you MUST use the `save_order` tool to process the transaction. Take the shipping address from the user's data.
4. Be polite, professional, and slightly sophisticated, but keep your answers concise.
5. If a user asks a question completely unrelated to wine, politely decline and steer the conversation back to Wine Place's catalog.
"""



# Define the model
MODEL_ID = "gemini-3.1-flash-lite"


def initialize_chat_session(client, user_data):
    """
    Initializes a stateful chat session dynamically tailored to the logged-in user.
    Accepts the full user_data dictionary returned from get_user_by_email().
    """
    # Guard clause against None or empty user_data
    if not user_data:
        print("Error: user_data is required to initialize chat.")
        return None
    
    try:
        # 1. Extract base identity
        user_id = user_data.get('id')
        role = user_data.get('user_role')
        email = user_data.get('email')
        
        
        # 2. Build the base context string
        context_string = textwrap.dedent(f"""\
                        CURRENT CUSTOMER CONTEXT:
                        - User ID: {user_id}
                        - Email: {email}
                        - Account Tier: {role}
                        """)
                                
        # 3. Conditionally append role-specific details
        if role == 'B2B':
            company = user_data.get('company_name', 'Unknown Company')
            contact = user_data.get('contact_person_name', 'Customer')
            tier = user_data.get('wholesale_tier', 'Standard')
            address = user_data.get('shipping_address')
            
            context_string += textwrap.dedent(f"""\
                            - Company Name: {company}
                            - Contact Person: {contact}
                            - Wholesale Tier: {tier}
                            - Shipping Address: {address}
                            """)
        elif role == 'B2C':
            first_name = user_data.get('first_name', 'Customer')
            last_name = user_data.get('last_name', '')
            style = user_data.get('preferred_wine_style', 'No preference listed')
            points = user_data.get('loyalty_points', 0)
            address = user_data.get('shipping_address')
            
            context_string += textwrap.dedent(f"""\
                            - Name: {first_name} {last_name}
                            - Preferred Wine Style: {style}
                            - Loyalty Points Balance: {points}
                            - Shipping Address: {address}
                            """)

        # 4. Add the strict tooling instruction
        context_string += f"\n(IMPORTANT: You must pass '{role}' exactly as the user_role argument when calling the `search_inventory` tool, and use User ID {user_id} when executing the `save_order` tool.)"

        # 5. Stitch it all onto the base instruction
        dynamic_instruction = BASE_SYSTEM_INSTRUCTION + context_string

        # 6. Build the config and create the chat
        dynamic_config = genai.types.GenerateContentConfig(
            system_instruction=dynamic_instruction,
            tools=[search_inventory, save_order], 
            temperature=0.3
        )

        chat = client.chats.create(
            model=MODEL_ID, 
            config=dynamic_config
        )
        return chat
        
    except Exception as e:
        print(f"Failed to initialize chat session: {e}")
        return None

def send_message_to_sommelier(chat, user_message):
    """
    Sends a message to the chat session and returns the AI's response.
    The SDK automatically handles the tool-calling loop behind the scenes!
    """
    try:
        # Send the message. The SDK will pause, run tools if needed, 
        # and wait for the final text response from the model.
        response = chat.send_message(user_message)
        return response.text
    except Exception as e:
        print("\n" + "="*40 + "\nFULL ERROR TRACEBACK:\n" + "="*40)
        traceback.print_exc() 
        print("="*40 + "\n")
        return f"I apologize, but I am having trouble accessing the cellar right now. ({str(e)})"