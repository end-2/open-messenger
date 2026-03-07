export type FrontendConfig = {
  port: number;
  apiBaseUrl: string;
  adminToken: string;
};

function parsePort(rawPort: string | undefined): number {
  const value = Number.parseInt(rawPort ?? "3001", 10);
  return Number.isFinite(value) && value > 0 ? value : 3001;
}

export function getFrontendConfig(env: NodeJS.ProcessEnv = process.env): FrontendConfig {
  return {
    port: parsePort(env.FRONTEND_PORT),
    apiBaseUrl: (env.OPEN_MESSENGER_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, ""),
    adminToken: env.OPEN_MESSENGER_ADMIN_API_TOKEN ?? "dev-admin-token"
  };
}
