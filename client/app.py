import asyncio
import datetime
import json
import os
import pyperclip
from typing import Dict, List, Set

import threading
from src.api_server import start_api_server
import time

import streamlit as st

from src.auth import AuthManager
from src.config import Configuration
from src.server import ServerManager
from src.api import ApiClient

# Set page configuration
st.set_page_config(
    page_title="MCP Server Manager",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "api_server_started" not in st.session_state:
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    time.sleep(1)
    st.session_state.api_server_started = True

# Initialize session state for persistent objects
if "server_manager" not in st.session_state:
    st.session_state.server_manager = ServerManager()
if "config" not in st.session_state:
    st.session_state.config = Configuration()
if "auth_manager" not in st.session_state:
    st.session_state.auth_manager = AuthManager()
if "api_client" not in st.session_state:
    st.session_state.api_client = ApiClient()


# Function to copy text to clipboard
def copy_to_clipboard(text):
    pyperclip.copy(text)
    return True


# Page title and description
st.title("🔌 MCP Server Manager")
st.markdown("""
This application helps you manage your MCP servers, launch them in groups, and generate API keys for use with the MCP proxy server.
""")

# Sidebar navigation
st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Server Dashboard", "Launch Servers", "API Keys Management"]
)

# Server Dashboard page
if page == "Server Dashboard":
    st.header("📋 Server Dashboard")

    servers = st.session_state.config.get_servers()

    if not servers:
        st.warning("No servers configured. Please add servers to your servers_config.json file.")

        st.subheader("Sample Configuration")
        sample_config = {
            "mcpServers": {
                "logseq": {
                    "command": "uvx",
                    "args": ["mcp-server-logseq"],
                    "env": {
                        "LOGSEQ_API_TOKEN": "your_token",
                        "LOGSEQ_API_URL": "http://127.0.0.1:8000"
                    }
                }
            }
        }
        st.code(json.dumps(sample_config, indent=2), language="json")
    else:
        # Display running servers first
        running_servers = st.session_state.server_manager.get_running_servers()
        if running_servers:
            st.subheader("🟢 Running Servers")
            for name in running_servers:
                with st.expander(f"{name}", expanded=True):
                    st.json(st.session_state.config.get_server_config(name))
                    if st.button(f"Stop {name}", key=f"stop_{name}"):
                        with st.spinner(f"Stopping {name}..."):
                            asyncio.run(st.session_state.server_manager.stop_server(name))
                            st.success(f"Server {name} stopped.")
                            st.rerun()

        # Display all servers
        st.subheader("📃 All Configured Servers")
        for name, config in servers.items():
            status = "🟢 Running" if st.session_state.server_manager.is_server_running(name) else "🔴 Stopped"
            with st.expander(f"{name} - {status}"):
                st.json(config)

# Launch Servers page
elif page == "Launch Servers":
    st.header("🚀 Launch Server Group")

    servers = st.session_state.config.get_servers()

    if not servers:
        st.warning("No servers configured. Please add servers to your servers_config.json file.")
    else:
        col1, col2 = st.columns([3, 1])

        with col1:
            # Server selection
            server_names = list(servers.keys())
            selected_servers = st.multiselect(
                "Select servers to launch",
                options=server_names,
                default=list(st.session_state.server_manager.get_selected_servers()),
                help="Select the MCP servers you want to launch as a group"
            )

            # Update selected servers
            if selected_servers:
                st.session_state.server_manager.select_servers(selected_servers)

            # Launch button
            launch_button = st.button("Launch Selected Servers", type="primary", disabled=len(selected_servers) == 0)

            if launch_button:
                with st.spinner("Starting servers..."):
                    # Use asyncio to start servers
                    started_servers = asyncio.run(
                        st.session_state.server_manager.start_selected_servers(servers)
                    )

                    if started_servers:
                        st.success(f"Started servers: {', '.join(started_servers)}")

                        # Generate API key for the started servers
                        api_key = st.session_state.auth_manager.generate_key(started_servers)

                        # Display the API key
                        st.subheader("🔑 Generated API Key")
                        key_col1, key_col2 = st.columns([5, 1])
                        with key_col1:
                            st.code(api_key, language="bash")
                        with key_col2:
                            if st.button("Copy", key="copy_api_key"):
                                copy_to_clipboard(api_key)
                                st.success("Copied to clipboard!")

                        # Instructions for using the API key
                        st.subheader("How to Use the API Key")
                        st.markdown("""
                        To use this API key with the MCP proxy server:

                        1. **Environment Variable:**
                        ```bash
                        export MCP_API_KEY=your_api_key_here
                        ```

                        2. **Start the MCP proxy server:**
                        ```bash
                        mcp-proxy-server
                        ```

                        3. **Or for SSE mode:**
                        ```bash
                        node build/sse.js
                        ```
                        """)
                    else:
                        st.error("Failed to start servers. Check the logs for more information.")

        with col2:
            # Information box
            st.info(
                "💡 **Tip:**\n\nStarting servers as a group allows you to generate a single API key for all of them.")

    # Display running servers
    running_servers = st.session_state.server_manager.get_running_servers()
    if running_servers:
        st.subheader("🟢 Currently Running Servers")
        st.write(", ".join(running_servers))

        # Stop all servers button
        if st.button("Stop All Servers", type="secondary"):
            with st.spinner("Stopping all servers..."):
                asyncio.run(st.session_state.server_manager.stop_all_servers())
                st.success("All servers stopped.")
                st.rerun()

# API Keys Management page
elif page == "API Keys Management":
    st.header("🔑 API Keys Management")

    keys = st.session_state.auth_manager.get_all_keys()

    if not keys:
        st.info("No API keys have been generated yet. Launch a server group to generate an API key.")
    else:
        st.markdown("Below are the API keys you've generated for your MCP server groups.")

        # Display all keys
        for key, details in keys.items():
            created_time = datetime.datetime.fromtimestamp(details['created'])

            with st.expander(f"API Key: {key[:10]}..."):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.code(key, language="bash")
                    st.write(f"🖥️ **Servers:** {', '.join(details['servers'])}")
                    st.write(f"📅 **Created:** {created_time.strftime('%Y-%m-%d %H:%M:%S')}")

                with col2:
                    if st.button("Copy", key=f"copy_{key[:8]}"):
                        copy_to_clipboard(key)
                        st.success("Copied to clipboard!")

                    if st.button("Revoke", key=f"revoke_{key[:8]}"):
                        if st.session_state.auth_manager.revoke_key(key):
                            st.success("API key revoked.")
                            st.rerun()
                        else:
                            st.error("Failed to revoke API key.")

# Footer
st.markdown("---")
st.markdown("© MCP Server Manager - Manage your MCP servers with ease")
