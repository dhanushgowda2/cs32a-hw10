import streamlit as st
import requests
import uuid
from datetime import datetime
import json
import os

st.set_page_config(page_title="My AI Chat", layout="wide")

# Load Hugging Face token
try:
    hf_token = st.secrets["HF_TOKEN"]
    if not hf_token:
        raise ValueError("Token is empty")
except KeyError:
    st.error("Hugging Face token not found. Please add HF_TOKEN to .streamlit/secrets.toml")
    st.stop()
except ValueError:
    st.error("Hugging Face token is empty. Please provide a valid token.")
    st.stop()

# API endpoint and model
endpoint = "https://router.huggingface.co/v1/chat/completions"
model = "meta-llama/Llama-3.2-1B-Instruct"

# Function to get response with streaming
def get_response(messages, placeholder):
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 512,
        "stream": True
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, stream=True)
        response.raise_for_status()
        full_response = ""
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        if "choices" in chunk and chunk["choices"]:
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                full_response += content
                                placeholder.markdown(full_response)
                                import time
                                time.sleep(0.05)  # Add delay for visibility
                    except json.JSONDecodeError:
                        continue
        return full_response
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"

# Function to save chat
def save_chat(chat):
    filename = f"chats/{chat['id']}.json"
    with open(filename, 'w') as f:
        json.dump(chat, f)

# Function to load chats
def load_chats():
    chats = []
    if os.path.exists("chats"):
        for file in os.listdir("chats"):
            if file.endswith(".json"):
                with open(f"chats/{file}", 'r') as f:
                    chat = json.load(f)
                    chats.append(chat)
    return chats

# Function to extract memory
def extract_memory(user_message):
    headers = {"Authorization": f"Bearer {hf_token}"}
    prompt = f"Extract any personal facts or preferences from this user message. Return only a JSON object with keys like 'name', 'interests', etc. If none, return {{}}. Message: {user_message}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Try to parse as JSON
        try:
            return json.loads(content)
        except:
            return {}
    except:
        return {}

# Load memory
def load_memory():
    if os.path.exists("memory.json"):
        with open("memory.json", 'r') as f:
            return json.load(f)
    return {}

# Save memory
def save_memory(memory):
    with open("memory.json", 'w') as f:
        json.dump(memory, f)

# Initialize memory
if "memory" not in st.session_state:
    st.session_state.memory = load_memory()

# Initialize session state
if "chats" not in st.session_state:
    st.session_state.chats = load_chats()
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = st.session_state.chats[0]["id"] if st.session_state.chats else None

# Sidebar
with st.sidebar:
    if st.button("New Chat"):
        chat_id = str(uuid.uuid4())
        new_chat = {
            "id": chat_id,
            "title": f"Chat {len(st.session_state.chats) + 1}",
            "timestamp": datetime.now().isoformat(),
            "messages": []
        }
        st.session_state.chats.append(new_chat)
        save_chat(new_chat)
        st.session_state.active_chat_id = chat_id
        st.rerun()

    st.write("### Chats")
    for i, chat in enumerate(st.session_state.chats):
        col1, col2 = st.columns([3, 1])
        with col1:
            title = f"**{chat['title']}**" if chat["id"] == st.session_state.active_chat_id else chat["title"]
            if st.button(title, key=f"chat_{chat['id']}"):
                st.session_state.active_chat_id = chat["id"]
                st.rerun()
        with col2:
            if st.button("✕", key=f"delete_{chat['id']}"):
                delete_chat_file(chat["id"])
                st.session_state.chats.pop(i)
                if st.session_state.active_chat_id == chat["id"]:
                    st.session_state.active_chat_id = st.session_state.chats[0]["id"] if st.session_state.chats else None
                st.rerun()

    # User Memory
    with st.expander("User Memory"):
        if st.session_state.memory:
            st.json(st.session_state.memory)
        else:
            st.write("No memory stored.")
        if st.button("Clear Memory"):
            st.session_state.memory = {}
            save_memory({})
            st.rerun()

# Get active chat
active_chat = None
if st.session_state.active_chat_id:
    for chat in st.session_state.chats:
        if chat["id"] == st.session_state.active_chat_id:
            active_chat = chat
            break

if active_chat:
    # Display chat messages
    for message in active_chat["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("What is up?"):
        # Add user message to history
        active_chat["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get assistant response with streaming
        messages_for_api = active_chat["messages"].copy()
        if st.session_state.memory:
            system_prompt = f"User preferences: {json.dumps(st.session_state.memory)}"
            messages_for_api.insert(0, {"role": "system", "content": system_prompt})
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            response = get_response(messages_for_api, response_placeholder)
            response_placeholder.markdown(response)  # Final display

        active_chat["messages"].append({"role": "assistant", "content": response})

        # Extract memory from user message
        new_memory = extract_memory(prompt)
        if new_memory:
            st.session_state.memory.update(new_memory)
            save_memory(st.session_state.memory)

        # Update title if first message
        if len(active_chat["messages"]) == 2:  # user and assistant
            active_chat["title"] = prompt[:30] + "..." if len(prompt) > 30 else prompt

        # Save chat
        save_chat(active_chat)
else:
    st.write("No active chat. Create a new chat to start.")