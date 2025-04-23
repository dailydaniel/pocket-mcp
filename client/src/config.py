import json
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self, config_path: str = "servers_config.json") -> None:
        """Initialize the configuration manager.

        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path
        self.load_env()
        self.config = self.load_config()

    @staticmethod
    def load_env() -> None:
        """Load environment variables from .env file."""
        load_dotenv()

    def load_config(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from the JSON file.

        Args:
            file_path: Optional path to the configuration file (overrides config_path)

        Returns:
            Dictionary containing the configuration
        """
        try:
            path = file_path or self.config_path
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
            return {"mcpServers": {}}
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return {"mcpServers": {}}

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to the JSON file.

        Args:
            config: Configuration dictionary to save
        """
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            self.config = config
        except Exception as e:
            print(f"Error saving configuration: {e}")

    def get_server_config(self, server_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific server.

        Args:
            server_name: Name of the server

        Returns:
            Server configuration or None if not found
        """
        return self.config.get("mcpServers", {}).get(server_name)

    def get_servers(self) -> Dict[str, Dict[str, Any]]:
        """Get all server configurations.

        Returns:
            Dictionary of server configurations
        """
        return self.config.get("mcpServers", {})
