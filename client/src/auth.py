import json
import os
import secrets
import time
from typing import Dict, List, Optional, Set, Tuple, Union


class AuthManager:
    """Manages API keys and server access."""

    def __init__(self, keys_file: str = "api_keys.json") -> None:
        """Initialize the authentication manager.

        Args:
            keys_file: Path to the API keys file
        """
        self.keys_file = keys_file
        self.keys = self.load_keys()

    def load_keys(self) -> Dict[str, Dict[str, Union[List[str], int]]]:
        """Load API keys from the JSON file.

        Returns:
            Dictionary of API keys and their associated servers
        """
        try:
            if os.path.exists(self.keys_file):
                with open(self.keys_file, "r") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error loading API keys: {e}")
            return {}

    def save_keys(self) -> None:
        """Save API keys to the JSON file."""
        try:
            with open(self.keys_file, "w") as f:
                json.dump(self.keys, f, indent=2)
        except Exception as e:
            print(f"Error saving API keys: {e}")

    def generate_key(self, server_names: List[str]) -> str:
        """Generate a new API key for a group of servers.

        Args:
            server_names: List of server names to associate with the key

        Returns:
            Generated API key
        """
        # Generate a random token
        token = secrets.token_urlsafe(32)

        # Store the key with associated servers and creation time
        self.keys[token] = {
            "servers": server_names,
            "created": int(time.time())
        }

        # Save the updated keys
        self.save_keys()

        return token

    def validate_key(self, key: str) -> Tuple[bool, List[str]]:
        """Validate an API key and return associated servers.

        Args:
            key: API key to validate

        Returns:
            Tuple of (is_valid, server_names)
        """
        # print(f"current keys: {self.keys}")
        self.keys = self.load_keys()
        # print(f"current keys after reload: {self.keys}")
        # print(f"validating key: {key}")

        if key in self.keys:
            return True, self.keys[key]["servers"]
        return False, []

    def revoke_key(self, key: str) -> bool:
        """Revoke an API key.

        Args:
            key: API key to revoke

        Returns:
            True if the key was revoked, False otherwise
        """
        if key in self.keys:
            del self.keys[key]
            self.save_keys()
            return True
        return False

    def get_all_keys(self) -> Dict[str, Dict[str, Union[List[str], int]]]:
        """Get all API keys.

        Returns:
            Dictionary of API keys and their details
        """
        return self.keys
