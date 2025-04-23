#!/usr/bin/env node

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createServer } from "./mcp-proxy.js";

async function main() {
  const apiKey = process.env.MCP_API_KEY;
  
  const transport = new StdioServerTransport();
  
  try {
    const { server, cleanup } = await createServer(apiKey);

    await server.connect(transport);

    process.on("SIGINT", async () => {
      await cleanup();
      await server.close();
      process.exit(0);
    });
  } catch (error) {
    console.error("Server error:", error);
    process.exit(1);
  }
}

main().catch((error) => {
  console.error("Error:", error);
  process.exit(1);
});
