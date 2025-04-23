// src/auth.ts
import axios from 'axios';
import { ServerConfig } from './config.js';

const CLIENT_API_URL = process.env.CLIENT_API_URL || 'http://localhost:8000/api';

export interface AuthResponse {
  success: boolean;
  servers: ServerConfig[];
  message?: string;
}

export async function authenticateAndGetServers(apiKey: string): Promise<ServerConfig[]> {
  try {
    const response = await axios.get<AuthResponse>(`${CLIENT_API_URL}/servers`, {
      headers: {
        Authorization: `Bearer ${apiKey}`
      }
    });

    if (!response.data.success) {
      throw new Error(response.data.message || 'Auth failed');
    }

    return response.data.servers;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.response?.status === 401) {
        throw new Error('Invalid API key');
      } else if (error.response?.status === 403) {
        throw new Error('No permission');
      }
      throw new Error(`Auth error: ${error.message}`);
    }
    throw error;
  }
}
