import { SSEServerTransport } from "@modelcontextprotocol/sdk/server/sse.js";
import express from "express";
import { createServer } from "./mcp-proxy.js";
import cors from "cors";

const app = express();
app.use(cors());

const apiKey = process.env.MCP_API_KEY;

let transport: SSEServerTransport;
let cleanupFunction: () => Promise<void>;

async function initServer() {
  try {
    const { server, cleanup } = await createServer(apiKey);
    cleanupFunction = cleanup;

    app.get("/sse", async (req, res) => {
      console.log("Got connection");
      transport = new SSEServerTransport("/message", res);
      await server.connect(transport);

      server.onerror = (err) => {
        console.error(`Server error: ${err.stack}`);
      };

      server.onclose = async () => {
        console.log('Server closed');
        if (process.env.KEEP_SERVER_OPEN !== "1") {
          await cleanup();
          await server.close();
          process.exit(0);
        }
      };
    });

    app.post("/message", async (req, res) => {
      console.log("Got message");
      await transport.handlePostMessage(req, res);
    });
  } catch (error) {
    console.error("Error in server initialization:", error);
    process.exit(1);
  }
}

initServer();

const PORT = process.env.PORT || 3006;
app.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
});

process.on("SIGINT", async () => {
  if (cleanupFunction) {
    await cleanupFunction();
  }
  process.exit(0);
});
