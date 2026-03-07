import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { pathToFileURL } from "node:url";

import { BackendClient, BackendError } from "./backend.ts";
import { getFrontendConfig } from "./config.ts";
import { renderDashboard } from "./dashboard.ts";

type JsonRecord = Record<string, unknown>;

function send(response: ServerResponse, statusCode: number, body: string, contentType: string): void {
  response.writeHead(statusCode, { "content-type": contentType });
  response.end(body);
}

function sendJson(response: ServerResponse, statusCode: number, body: JsonRecord): void {
  send(response, statusCode, JSON.stringify(body), "application/json; charset=utf-8");
}

async function readJson(request: IncomingMessage): Promise<JsonRecord> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }

  if (chunks.length === 0) {
    return {};
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as JsonRecord;
}

export function createFrontendServer(client: BackendClient, html: string) {
  return createServer(async (request, response) => {
    if (!request.url) {
      sendJson(response, 400, { error: "Request URL is required" });
      return;
    }

    const url = new URL(request.url, "http://localhost");

    try {
      if (request.method === "GET" && url.pathname === "/healthz") {
        sendJson(response, 200, { status: "ok" });
        return;
      }

      if (request.method === "GET" && url.pathname === "/") {
        send(response, 200, html, "text/html; charset=utf-8");
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/info") {
        sendJson(response, 200, await client.getInfo());
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/bootstrap") {
        const body = await readJson(request);
        const result = await client.bootstrapUser({
          username: String(body.username ?? "").trim(),
          displayName: String(body.displayName ?? "").trim(),
          scopes: Array.isArray(body.scopes) ? body.scopes.map((scope) => String(scope)) : [],
          tokenType: String(body.tokenType ?? "user_token")
        });
        sendJson(response, 201, result);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/channels") {
        const body = await readJson(request);
        const channel = await client.createChannel(String(body.accessToken ?? ""), String(body.name ?? ""));
        sendJson(response, 201, channel);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/messages/list") {
        const body = await readJson(request);
        const messages = await client.listMessages(String(body.accessToken ?? ""), String(body.channelId ?? ""));
        sendJson(response, 200, messages);
        return;
      }

      if (request.method === "POST" && url.pathname === "/api/messages") {
        const body = await readJson(request);
        const message = await client.createMessage(String(body.accessToken ?? ""), String(body.channelId ?? ""), {
          text: String(body.text ?? ""),
          sender_user_id: String(body.senderUserId ?? "") || undefined,
          idempotency_key: String(body.idempotencyKey ?? "") || undefined
        });
        sendJson(response, 201, message);
        return;
      }

      if (request.method === "GET" && url.pathname === "/api/events") {
        const accessToken = url.searchParams.get("access_token");
        if (!accessToken) {
          sendJson(response, 400, { error: "access_token is required" });
          return;
        }

        const upstream = await fetch(`${client.baseUrl}/v1/events/stream`, {
          headers: {
            authorization: `Bearer ${accessToken}`
          }
        });

        if (!upstream.ok || !upstream.body) {
          const details = await upstream.text();
          throw new BackendError(details || "Unable to open upstream event stream", upstream.status, details);
        }

        response.writeHead(200, {
          "content-type": "text/event-stream; charset=utf-8",
          "cache-control": "no-cache",
          connection: "keep-alive"
        });

        for await (const chunk of upstream.body) {
          response.write(chunk);
        }
        response.end();
        return;
      }

      sendJson(response, 404, { error: `Route not found: ${url.pathname}` });
    } catch (error) {
      if (error instanceof BackendError) {
        sendJson(response, error.status, {
          error: error.message,
          details: error.details
        });
        return;
      }
      if (error instanceof SyntaxError) {
        sendJson(response, 400, { error: "Invalid JSON request body" });
        return;
      }
      sendJson(response, 500, {
        error: error instanceof Error ? error.message : "Unknown server error"
      });
    }
  });
}

export function startFrontendServer() {
  const config = getFrontendConfig();
  const client = new BackendClient(config.apiBaseUrl, config.adminToken);
  const server = createFrontendServer(client, renderDashboard(config));
  server.listen(config.port, () => {
    console.log(
      JSON.stringify({
        service: "open-messenger-frontend",
        status: "ready",
        port: config.port,
        apiBaseUrl: config.apiBaseUrl
      })
    );
  });
  return server;
}

const isMainModule =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMainModule) {
  startFrontendServer();
}
