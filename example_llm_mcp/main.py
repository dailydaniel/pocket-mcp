import asyncio
import json
import os
import shutil
from contextlib import AsyncExitStack
from typing import Any, Union

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import OpenAI, ChatCompletion


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self) -> None:
        self.load_env()
        self.api_key = os.getenv("OPENAI_API_KEY")

    @staticmethod
    def load_env() -> None:
        load_dotenv()

    @staticmethod
    def load_config(file_path: str = "servers_config.json") -> dict[str, Any]:
        with open(file_path, "r") as f:
            return json.load(f)

    @property
    def llm_api_key(self) -> str:
        if not self.api_key:
            raise ValueError("LLM_API_KEY not found in environment variables")
        return self.api_key


class Server:
    """Manages MCP server connections and tool execution."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name: str = name
        self.config: dict[str, Any] = config
        self.stdio_context: Any | None = None
        self.session: ClientSession | None = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()

    async def initialize(self) -> None:
        command = (
            shutil.which("npx")
            if self.config["command"] == "npx"
            else self.config["command"]
        )
        if command is None:
            raise ValueError("The command must be a valid string and cannot be None.")

        server_params = StdioServerParameters(
            command=command,
            args=self.config["args"],
            env={**os.environ, **self.config["env"]}
            if self.config.get("env")
            else None,
        )
        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.session = session
        except Exception as e:
            print(f"Error initializing server {self.name}: {e}")
            await self.cleanup()
            raise

    async def list_tools(self) -> list[Any]:
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        tools_response = await self.session.list_tools()
        tools = []

        for item in tools_response:
            if isinstance(item, tuple) and item[0] == "tools":
                for tool in item[1]:
                    tools.append(Tool(tool.name, tool.description, tool.inputSchema))

        return tools

    async def execute_tool(
            self,
            tool_name: str,
            arguments: dict[str, Any],
            retries: int = 2,
            delay: float = 1.0,
    ) -> Any:
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        attempt = 0
        while attempt < retries:
            try:
                print(f"Executing tool {tool_name}")
                result = await self.session.call_tool(tool_name, arguments)

                return result

            except Exception as e:
                attempt += 1
                print(f"Error executing tool: {e}. Attempt {attempt} of {retries}.")
                if attempt < retries:
                    print(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    print("Max retries reached. Failing.")
                    raise

    async def cleanup(self) -> None:
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
                self.stdio_context = None
            except Exception as e:
                print(f"Error during cleanup of server {self.name}: {e}")


class Tool:
    """Represents a tool with its properties and formatting."""

    def __init__(
            self, name: str, description: str, input_schema: dict[str, Any]
    ) -> None:
        self.name: str = name
        self.description: str = description
        self.input_schema: dict[str, Any] = input_schema

    def format_for_llm(self, provider_with_func_call: bool = False) -> str | dict:
        if provider_with_func_call:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            param_name: param_info
                            for param_name, param_info in self.input_schema["properties"].items()
                        } if "properties" in self.input_schema else {},
                        "required": self.input_schema.get("required", []),
                        "additionalProperties": self.input_schema.get("additionalProperties", False)
                    }
                }
            }
        else:
            args_desc = []

            if "properties" in self.input_schema:
                for param_name, param_info in self.input_schema["properties"].items():
                    arg_desc = (
                        f"- {param_name}: {param_info.get('description', 'No description')}"
                    )
                    if param_name in self.input_schema.get("required", []):
                        arg_desc += " (required)"
                    args_desc.append(arg_desc)

            return f"""
Tool: {self.name}
Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""


class LLMClient:
    """Manages communication with the LLM provider."""

    def __init__(self, api_key: str = os.getenv("OPENAI_API_KEY")) -> None:
        self.api_key: str = api_key
        self.client = OpenAI(api_key=self.api_key)

    def get_response(
            self,
            messages: list[dict[str, str]],
            temperature: float = 0.3,
            model: str = "gpt-4o",
            max_tokens: int = 4096,
            tools: list[dict[str, Any]] | None = None,
    ) -> Union[str, ChatCompletion]:
        if tools:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )

            if response.choices[0].finish_reason == "tool_calls":
                return response
            else:
                return response.choices[0].message.content
        else:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return response.choices[0].message.content


class ChatSession:
    """Orchestrates the interaction between user, LLM, and tools."""

    def __init__(self, servers: list[Server], llm_client: LLMClient) -> None:
        self.servers: list[Server] = servers
        self.llm_client: LLMClient = llm_client

    async def cleanup_servers(self) -> None:
        cleanup_tasks = []
        for server in self.servers:
            cleanup_tasks.append(asyncio.create_task(server.cleanup()))

        if cleanup_tasks:
            try:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            except Exception as e:
                print(f"Warning during final cleanup: {e}")

    async def process_llm_response(self, llm_response: Union[str, ChatCompletion]) -> str | list:
        try:
            if isinstance(llm_response, str):
                tool_call = json.loads(llm_response)
                if "tool" in tool_call and "arguments" in tool_call:
                    print(f"Executing tool: {tool_call['tool']}")
                    print(f"With arguments: {tool_call['arguments']}")

                    for server in self.servers:
                        tools = await server.list_tools()
                        if any(tool.name == tool_call["tool"] for tool in tools):
                            try:
                                result = await server.execute_tool(
                                    tool_call["tool"], tool_call["arguments"]
                                )

                                if isinstance(result, dict) and "progress" in result:
                                    progress = result["progress"]
                                    total = result["total"]
                                    percentage = (progress / total) * 100
                                    print(f"Progress: {progress}/{total} ({percentage:.1f}%)")

                                return f"Tool execution result: {result}"
                            except Exception as e:
                                error_msg = f"Error executing tool: {str(e)}"
                                print(error_msg)
                                return error_msg
                return llm_response
            else:
                if llm_response.choices[0].finish_reason == "tool_calls":
                    for tool_call in llm_response.choices[0].message.tool_calls:
                        function_call = json.loads(tool_call.function.to_json())
                        if "arguments" in function_call and "name" in function_call:
                            function_name = function_call["name"]
                            arguments = json.loads(function_call["arguments"])
                            print(f"Executing function: {function_name} with arguments: {arguments}")
                            results = []

                            for server in self.servers:
                                tools = await server.list_tools()
                                if any(tool.name == function_name for tool in tools):
                                    try:
                                        result = await server.execute_tool(
                                            function_name, arguments
                                        )

                                        if isinstance(result, dict) and "progress" in result:
                                            progress = result["progress"]
                                            total = result["total"]
                                            percentage = (progress / total) * 100
                                            print(f"Progress: {progress}/{total} ({percentage:.1f}%)")

                                        results.append(f"Tool execution result: {result}")
                                    except Exception as e:
                                        error_msg = f"Error executing tool: {str(e)}"
                                        print(error_msg)
                                        results.append(error_msg)

                            return results

            return llm_response
        except json.JSONDecodeError:
            return llm_response

    async def start(self) -> None:
        try:
            for server in self.servers:
                try:
                    await server.initialize()
                except Exception as e:
                    print(f"Failed to initialize server: {e}")
                    await self.cleanup_servers()
                    return

            all_tools = []
            for server in self.servers:
                tools = await server.list_tools()
                all_tools.extend(tools)

            tools_schema = [tool.format_for_llm(provider_with_func_call=True) for tool in all_tools]

            # tools_description = "\n".join([tool.format_for_llm() for tool in all_tools])
            #
            # system_message = (
            #     "You are a helpful assistant with access to these tools:\n\n"
            #     f"{tools_description}\n"
            #     "Choose the appropriate tool based on the user's question. "
            #     "If no tool is needed, reply directly.\n\n"
            #     "IMPORTANT: When you need to use a tool, you must ONLY respond with "
            #     "the exact JSON object format below, nothing else:\n"
            #     "{\n"
            #     '    "tool": "tool-name",\n'
            #     '    "arguments": {\n'
            #     '        "argument-name": "value"\n'
            #     "    }\n"
            #     "}\n\n"
            #     "After receiving a tool's response:\n"
            #     "1. Transform the raw data into a natural, conversational response\n"
            #     "2. Keep responses concise but informative\n"
            #     "3. Focus on the most relevant information\n"
            #     "4. Use appropriate context from the user's question\n"
            #     "5. Avoid simply repeating the raw data\n\n"
            #     "Please use only the tools that are explicitly defined above."
            # )

            system_message = "You are a helpful assistant with access to some tools. Use them only when necessary."

            messages = [{"role": "system", "content": system_message}]

            while True:
                try:
                    user_input = input("You: ").strip().lower()
                    if user_input in ["quit", "exit"]:
                        print("\nExiting...")
                        break

                    messages.append({"role": "user", "content": user_input})

                    # llm_response = self.llm_client.get_response(messages)
                    llm_response = self.llm_client.get_response(messages, tools=tools_schema)
                    print("\nAssistant: %s", llm_response)

                    result = await self.process_llm_response(llm_response)

                    if isinstance(result, list) or result != llm_response:
                        print(f"\nTool execution result: {result}")
                        tool_call_output = json.loads(llm_response.choices[0].message.to_json())
                        messages.append(tool_call_output)
                        messages[-1]['content'] = ""

                        if isinstance(result, str):
                            messages.append({                               # append result message
                                "type": "function_call_output",
                                "tool_call_id": tool_call_output['tool_calls'][0]['id'],
                                "content": result,
                                "role": "tool",
                            })
                        else:
                            for i, res in enumerate(result):
                                messages.append({                               # append result message
                                    "type": "function_call_output",
                                    "tool_call_id": tool_call_output['tool_calls'][i]['id'],
                                    "content": res,
                                    "role": "tool",
                                })
                        # messages.append({"role": "assistant", "content": llm_response})
                        # messages.append({"role": "system", "content": result})

                        final_response = self.llm_client.get_response(messages)
                        print("\nFinal response: %s", final_response)
                        messages.append(
                            {"role": "assistant", "content": final_response}
                        )
                    else:
                        messages.append({"role": "assistant", "content": llm_response})

                except KeyboardInterrupt:
                    print("\nExiting...")
                    break

        finally:
            await self.cleanup_servers()


async def main() -> None:
    """Initialize and run the chat session."""
    config = Configuration()
    server_config = config.load_config("servers_config.json")
    servers = [
        Server(name, srv_config)
        for name, srv_config in server_config["mcpServers"].items()
    ]
    llm_client = LLMClient(config.llm_api_key)
    chat_session = ChatSession(servers, llm_client)
    await chat_session.start()


if __name__ == "__main__":
    asyncio.run(main())