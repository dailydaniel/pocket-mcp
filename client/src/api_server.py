import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional
import socket

from .auth import AuthManager
from .server import ServerManager
from .config import Configuration

API_PORT = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_manager = AuthManager()
config = Configuration()
server_manager = ServerManager()


async def verify_api_key(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="API key required")

    if authorization.startswith("Bearer "):
        api_key = authorization[7:]
    else:
        api_key = authorization

    is_valid, server_names = auth_manager.validate_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return server_names


@app.get("/api/servers")
async def get_servers(server_names: List[str] = Depends(verify_api_key)):
    servers_config = config.get_servers()

    authorized_servers = []
    for name in server_names:
        if name in servers_config:
            sse_port = 3000 + hash(name) % 1000

            authorized_servers.append({
                "name": name,
                "transport": {
                    "type": "sse",
                    "url": f"http://0.0.0.0:{sse_port}/sse"
                }
            })

    return {
        "success": True,
        "servers": authorized_servers
    }


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


def find_free_port(start_port=8000, max_attempts=100):
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise IOError("No free ports found")


def start_api_server(host="0.0.0.0", port=None):
    if port is None:
        port = find_free_port()
    print(f"Starting API server on port {port}")
    global API_PORT
    API_PORT = port
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_api_server()
