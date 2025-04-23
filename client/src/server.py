import asyncio
import json
import os
import shutil
import subprocess
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Set, Tuple

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class Server:
    """Manages an MCP server connection and execution."""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        """Initialize the server.

        Args:
            name: Server name
            config: Server configuration
        """
        self.name: str = name
        self.config: Dict[str, Any] = config
        self.process: Optional[subprocess.Popen] = None
        self.session: Optional[ClientSession] = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()

    async def start(self) -> bool:
        """Start the server process via mcp-proxy in SSE mode."""
        if self.process and self.is_running():
            print(f"Server {self.name} is already running")
            return True

        try:
            # Prepare command and environment for mcp-proxy
            proxy_command = shutil.which("mcp-proxy")
            if not proxy_command:
                print(f"Command 'mcp-proxy' not found. Please install it.")
                return False

            # Define the SSE port for this server
            sse_port = self.config.get("sse_port", 3000 + hash(self.name) % 1000)

            start_command = shutil.which(self.config["command"])
            print(f"start command: {start_command}")
            if not start_command:
                print(f"Command {self.config['command']} not found. Please install Node.js and npm.")

            args = [
                       "--allow-origin='*'",
                       f"--sse-port={str(sse_port)}",
                       "--sse-host=0.0.0.0",
                       "--pass-environment",
                       "--",
                       start_command
                   ] + self.config["args"]

            # Add server-specific environment variables
            env = os.environ.copy()
            if "env" in self.config:
                env.update(self.config["env"])

            # Start mcp-proxy process
            self.process = subprocess.Popen(
                [proxy_command] + args,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False
            )

            print(f"Started mcp-proxy for {self.name} on port {sse_port}")
            return True

        except Exception as e:
            print(f"Error starting mcp-proxy for {self.name}: {e}")
            return False

    async def stop(self) -> bool:
        """Stop the server.

        Returns:
            True if the server was stopped successfully, False otherwise
        """
        await self.cleanup()

        if not self.process:
            return True

        try:
            self.process.terminate()

            # Wait for the process to terminate
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

            self.process = None
            print(f"Stopped server {self.name}")
            return True

        except Exception as e:
            print(f"Error stopping server {self.name}: {e}")
            return False

    async def cleanup(self) -> None:
        """Clean up resources."""
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
            except Exception as e:
                print(f"Error during cleanup of server {self.name}: {e}")

    def is_running(self) -> bool:
        """Check if the server is running.

        Returns:
            True if the server is running, False otherwise
        """
        if not self.process:
            return False

        # Check if the process is still alive
        if self.process.poll() is not None:
            # Process has terminated
            self.process = None
            return False

        return True


class ServerManager:
    """Manages multiple MCP servers."""

    def __init__(self) -> None:
        """Initialize the server manager."""
        self.servers: Dict[str, Server] = {}
        self.selected_servers: Set[str] = set()

    def select_servers(self, server_names: List[str]) -> None:
        """Select a group of servers.

        Args:
            server_names: List of server names to select
        """
        self.selected_servers = set(server_names)

    def get_selected_servers(self) -> Set[str]:
        """Get the currently selected servers.

        Returns:
            Set of selected server names
        """
        return self.selected_servers

    async def start_server(self, name: str, config: Dict[str, Any]) -> bool:
        """Start an MCP server.

        Args:
            name: Server name
            config: Server configuration

        Returns:
            True if the server was started successfully, False otherwise
        """
        if name not in self.servers:
            self.servers[name] = Server(name, config)

        return await self.servers[name].start()

    async def start_selected_servers(self, server_configs: Dict[str, Dict[str, Any]]) -> List[str]:
        """Start all selected servers.

        Args:
            server_configs: Dictionary of server configurations

        Returns:
            List of successfully started server names
        """
        started_servers = []

        for name in self.selected_servers:
            if name in server_configs:
                success = await self.start_server(name, server_configs[name])
                if success:
                    print(f"Success in starting server {name}")
                    started_servers.append(name)
                else:
                    print(f"Failed to start server {name}")
            else:
                print(f"Server {name} not found in configuration")

        return started_servers

    async def stop_server(self, name: str) -> bool:
        """Stop an MCP server.

        Args:
            name: Server name

        Returns:
            True if the server was stopped successfully, False otherwise
        """
        if name not in self.servers:
            print(f"Server {name} not found")
            return False

        return await self.servers[name].stop()

    async def stop_all_servers(self) -> None:
        """Stop all servers."""
        for name in list(self.servers.keys()):
            await self.stop_server(name)

    def get_running_servers(self) -> List[str]:
        """Get names of all running servers.

        Returns:
            List of running server names
        """
        return [name for name, server in self.servers.items() if server.is_running()]

    def is_server_running(self, name: str) -> bool:
        """Check if a server is running.

        Args:
            name: Server name

        Returns:
            True if the server is running, False otherwise
        """
        if name not in self.servers:
            return False

        return self.servers[name].is_running()
