// src/config.ts
import { readFile } from 'fs/promises';
import { resolve } from 'path';
import { authenticateAndGetServers } from './auth.js';

export type TransportConfigStdio = {
  type?: 'stdio'
  command: string;
  args?: string[];
  env?: string[]
}

export type TransportConfigSSE = {
  type: 'sse'
  url: string
}

export type TransportConfig = TransportConfigSSE | TransportConfigStdio
export interface ServerConfig {
  name: string;
  transport: TransportConfig;
}

export interface Config {
  servers: ServerConfig[];
}

export const loadConfig = async (apiKey?: string): Promise<Config> => {
  if (apiKey) {
    try {
      const servers = await authenticateAndGetServers(apiKey);
      return { servers };
    } catch (error) {
      console.error('Auth error with API key:', error);
      throw error;
    }
  }

  try {
    const configPath = process.env.MCP_CONFIG_PATH || resolve(process.cwd(), 'config.json');
    console.log(`Load config from: ${configPath}`);
    const fileContents = await readFile(configPath, 'utf-8');
    return JSON.parse(fileContents);
  } catch (error) {
    console.error('Error in loading config.json:', error);
    return { servers: [] };
  }
};
