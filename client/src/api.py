import json
import os
from typing import Any, Dict, List, Optional


class ApiClient:
    """Client for generating server configurations for MCP API server."""

    @staticmethod
    def generate_server_config(
            api_key: str,
            server_configs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate MCP Proxy Server configuration based on API key.

        Args:
            api_key: API key for authentication
            server_configs: Dictionary of server configurations

        Returns:
            Dictionary with instructions for proxy server
        """
        return {
            "api_key": api_key,
            "instructions": {
                "env_variable": "MCP_API_KEY",
                "command": "mcp-proxy-server",
                "sse_command": "node build/sse.js"
            }
        }