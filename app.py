import streamlit as st
from database import get_user_by_email
from agent import initialize_chat_session, send_message_to_sommelier, client, MODEL_ID

# ---------------------------------------------------------
# 1. INITIALIZE SESSION STATE (The Memory)
# ---------------------------------------------------------
# We check if these variables exist in our "save file" yet. 
# If not, we set them to their default starting values.
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if 'user_data' not in st.session_state:
    st.session_state['user_data'] = None

if 'chat_session' not in st.session_state:
    st.session_state['chat_session'] = None

if 'messages' not in st.session_state:
    st.session_state['messages'] = []
    
if 'cart' not in st.session_state:
    st.session_state['cart'] = []
    
# ---------------------------------------------------------
# 2. THE LOGIN UI
# ---------------------------------------------------------
# If the user is NOT logged in, show the login screen.
if not st.session_state['logged_in']:
    st.title("Welcome to Wine Place🍷")
    st.write("Please log in to speak with our AI Sommelier.")
    
    # TRICK TO CENTER ELEMENTS: 
    # We create 3 columns. We leave the left and right empty, 
    # and only put our login box inside the middle column.
    left_col, mid_col, right_col = st.columns([1, 30, 1])
    
    with mid_col:
        # Create a visual box for the login form
        with st.container(border=True):
            st.subheader("Sign In")
            
            # The input field
            email_input = st.text_input("Email Address", placeholder="Enter your email...")
            
            # The login button
            if st.button("Log In", use_container_width=True):
                if email_input:
                    user = get_user_by_email(email_input)
                    
                    if user:
                        # Success! Save the user data and flip the login switch
                        st.session_state['logged_in'] = True
                        st.session_state['user_data'] = user
                        
                        # 1. Boot up the personalized Gemini agent
                        st.session_state['chat_session'] = initialize_chat_session(client, user)
                        
                        # 2. Add a welcome greeting to the empty message list
                        st.session_state['messages'] = [
                            {"role": "assistant", "content": "Hello! I am your AI Sommelier. How can I assist you today?"}
                        ]
                        
                        # Force Streamlit to redraw the page with the new memory!
                        st.rerun()
                    else:
                        st.error("We couldn't find an account with that email or the account is inactive. Please try again.")
                else:
                    st.error("Please enter an email address.")
                    
# ---------------------------------------------------------
# 3. THE MAIN APP (Hidden behind login)
# ---------------------------------------------------------
else:
    # Header and Logout Button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("Wine Place AI Sommelier")
    with col2:
        if st.button("Log Out", use_container_width=True):
            # Wipe everything on logout
            st.session_state.clear() 
            st.rerun()

    st.divider()

    # --- DRAW THE CHAT HISTORY ---
    # Streamlit iterates through our saved messages and draws them on screen
    for msg in st.session_state['messages']:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- HANDLE NEW MESSAGES ---
    # The walrus operator (:=) assigns the input to 'prompt' AND checks if it's not empty
    if prompt := st.chat_input("Ask about our wine selection..."):
        
        # 1. Show the user's message immediately
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # 2. Save it to memory so it doesn't disappear on rerun
        st.session_state['messages'].append({"role": "user", "content": prompt})
        
        # 3. Send it to the Gemini agent and show the response
        with st.chat_message("assistant"):
            # We grab the active session we saved during login
            active_session = st.session_state['chat_session']
            
            # --- THE FIX: Use your wrapper function ---
            with st.spinner("Let me check the cellar..."):  # Optional: Adds a nice loading spinner!
                response_text = send_message_to_sommelier(active_session, prompt)
            
            # Draw Gemini's response
            st.markdown(response_text)
            
        # 4. Save Gemini's response to memory
        st.session_state['messages'].append({"role": "assistant", "content": response_text})