import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
  Tool,
  ListToolsResultSchema,
  ListPromptsResultSchema,
  ListResourcesResultSchema,
  ReadResourceResultSchema,
  ListResourceTemplatesRequestSchema,
  ListResourceTemplatesResultSchema,
  ResourceTemplate,
  CompatibilityCallToolResultSchema,
  GetPromptResultSchema
} from "@modelcontextprotocol/sdk/types.js";
import { createClients, ConnectedClient } from './client.js';
import { Config, loadConfig } from './config.js';
import { z } from 'zod';
import * as eventsource from 'eventsource';

global.EventSource = eventsource.EventSource

export const createServer = async (apiKey?: string) => {
  const config = await loadConfig(apiKey);
  
  if (config.servers.length === 0) {
    console.warn('Warning: No servers found.');
  } else {
    console.log(`Found servers: ${config.servers.length}`);
  }
  
  const connectedClients = await createClients(config.servers);
  console.log(`Connected to ${connectedClients.length} server`);

  // Maps to track which client owns which resource
  const toolToClientMap = new Map<string, ConnectedClient>();
  const resourceToClientMap = new Map<string, ConnectedClient>();
  const promptToClientMap = new Map<string, ConnectedClient>();

  const server = new Server(
    {
      name: "mcp-proxy-server",
      version: "1.0.0",
    },
    {
      capabilities: {
        prompts: {},
        resources: { subscribe: true },
        tools: {},
      },
    },
  );

  // List Tools Handler
  server.setRequestHandler(ListToolsRequestSchema, async (request) => {
    const allTools: Tool[] = [];
    toolToClientMap.clear();

    for (const connectedClient of connectedClients) {
      try {
        const result = await connectedClient.client.request(
          {
            method: 'tools/list',
            params: {
              _meta: request.params?._meta
            }
          },
          ListToolsResultSchema
        );

        if (result.tools) {
          const toolsWithSource = result.tools.map(tool => {
            toolToClientMap.set(tool.name, connectedClient);
            return {
              ...tool,
              description: `[${connectedClient.name}] ${tool.description || ''}`
            };
          });
          allTools.push(...toolsWithSource);
        }
      } catch (error) {
        console.error(`Error fetching tools from ${connectedClient.name}:`, error);
      }
    }

    return { tools: allTools };
  });

  // Call Tool Handler
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const clientForTool = toolToClientMap.get(name);

    if (!clientForTool) {
      throw new Error(`Unknown tool: ${name}`);
    }

    try {
      console.log('Forwarding tool call:', name);

      // Use the correct schema for tool calls
      return await clientForTool.client.request(
        {
          method: 'tools/call',
          params: {
            name,
            arguments: args || {},
            _meta: {
              progressToken: request.params._meta?.progressToken
            }
          }
        },
        CompatibilityCallToolResultSchema
      );
    } catch (error) {
      console.error(`Error calling tool through ${clientForTool.name}:`, error);
      throw error;
    }
  });

  // Get Prompt Handler
  server.setRequestHandler(GetPromptRequestSchema, async (request) => {
    const { name } = request.params;
    const clientForPrompt = promptToClientMap.get(name);

    if (!clientForPrompt) {
      throw new Error(`Unknown prompt: ${name}`);
    }

    try {
      console.log('Forwarding prompt request:', name);

      // Match the exact structure from the example code
      const response = await clientForPrompt.client.request(
        {
          method: 'prompts/get' as const,
          params: {
            name,
            arguments: request.params.arguments || {},
            _meta: request.params._meta || {
              progressToken: undefined
            }
          }
        },
        GetPromptResultSchema
      );

      console.log('Prompt result:', response);
      return response;
    } catch (error) {
      console.error(`Error getting prompt from ${clientForPrompt.name}:`, error);
      throw error;
    }
  });

  // List Prompts Handler
  server.setRequestHandler(ListPromptsRequestSchema, async (request) => {
    const allPrompts: z.infer<typeof ListPromptsResultSchema>['prompts'] = [];
    promptToClientMap.clear();

    for (const connectedClient of connectedClients) {
      try {
        const result = await connectedClient.client.request(
          {
            method: 'prompts/list' as const,
            params: {
              cursor: request.params?.cursor,
              _meta: request.params?._meta || {
                progressToken: undefined
              }
            }
          },
          ListPromptsResultSchema
        );

        if (result.prompts) {
          const promptsWithSource = result.prompts.map(prompt => {
            promptToClientMap.set(prompt.name, connectedClient);
            return {
              ...prompt,
              description: `[${connectedClient.name}] ${prompt.description || ''}`
            };
          });
          allPrompts.push(...promptsWithSource);
        }
      } catch (error) {
        console.error(`Error fetching prompts from ${connectedClient.name}:`, error);
      }
    }

    return {
      prompts: allPrompts,
      nextCursor: request.params?.cursor
    };
  });

  // List Resources Handler
  server.setRequestHandler(ListResourcesRequestSchema, async (request) => {
    const allResources: z.infer<typeof ListResourcesResultSchema>['resources'] = [];
    resourceToClientMap.clear();

    for (const connectedClient of connectedClients) {
      try {
        const result = await connectedClient.client.request(
          {
            method: 'resources/list',
            params: {
              cursor: request.params?.cursor,
              _meta: request.params?._meta
            }
          },
          ListResourcesResultSchema
        );

        if (result.resources) {
          const resourcesWithSource = result.resources.map(resource => {
            resourceToClientMap.set(resource.uri, connectedClient);
            return {
              ...resource,
              name: `[${connectedClient.name}] ${resource.name || ''}`
            };
          });
          allResources.push(...resourcesWithSource);
        }
      } catch (error) {
        console.error(`Error fetching resources from ${connectedClient.name}:`, error);
      }
    }

    return {
      resources: allResources,
      nextCursor: undefined
    };
  });

  // Read Resource Handler
  server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
    const { uri } = request.params;
    const clientForResource = resourceToClientMap.get(uri);

    if (!clientForResource) {
      throw new Error(`Unknown resource: ${uri}`);
    }

    try {
      return await clientForResource.client.request(
        {
          method: 'resources/read',
          params: {
            uri,
            _meta: request.params._meta
          }
        },
        ReadResourceResultSchema
      );
    } catch (error) {
      console.error(`Error reading resource from ${clientForResource.name}:`, error);
      throw error;
    }
  });

  // List Resource Templates Handler
  server.setRequestHandler(ListResourceTemplatesRequestSchema, async (request) => {
    const allTemplates: ResourceTemplate[] = [];

    for (const connectedClient of connectedClients) {
      try {
        const result = await connectedClient.client.request(
          {
            method: 'resources/templates/list' as const,
            params: {
              cursor: request.params?.cursor,
              _meta: request.params?._meta || {
                progressToken: undefined
              }
            }
          },
          ListResourceTemplatesResultSchema
        );

        if (result.resourceTemplates) {
          const templatesWithSource = result.resourceTemplates.map(template => ({
            ...template,
            name: `[${connectedClient.name}] ${template.name || ''}`,
            description: template.description ? `[${connectedClient.name}] ${template.description}` : undefined
          }));
          allTemplates.push(...templatesWithSource);
        }
      } catch (error) {
        console.error(`Error fetching resource templates from ${connectedClient.name}:`, error);
      }
    }

    return {
      resourceTemplates: allTemplates,
      nextCursor: request.params?.cursor
    };
  });

  const cleanup = async () => {
    await Promise.all(connectedClients.map(({ cleanup }) => cleanup()));
  };

  return { server, cleanup };
};
