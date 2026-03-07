import type { FrontendConfig } from "./config.ts";

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

export function renderDashboard(config: FrontendConfig): string {
  const apiBaseUrl = escapeHtml(config.apiBaseUrl);

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Open Messenger Console</title>
    <style>
      :root {
        --bg: linear-gradient(135deg, #f3efe4 0%, #d7e3f1 48%, #f0c9ae 100%);
        --panel: rgba(255, 252, 248, 0.78);
        --border: rgba(54, 71, 91, 0.18);
        --text: #1d2a37;
        --muted: #55687d;
        --accent: #d0572f;
        --accent-strong: #8f2f1e;
        --success: #0f7b50;
        --shadow: 0 20px 50px rgba(43, 55, 72, 0.18);
        --radius: 24px;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--text);
        background: var(--bg);
        min-height: 100vh;
      }
      .shell {
        max-width: 1320px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }
      .hero {
        display: grid;
        gap: 14px;
        margin-bottom: 24px;
      }
      .eyebrow {
        letter-spacing: 0.18em;
        text-transform: uppercase;
        font-size: 0.78rem;
        color: var(--accent-strong);
      }
      h1 {
        font-size: clamp(2.8rem, 7vw, 5.8rem);
        line-height: 0.94;
        margin: 0;
        max-width: 10ch;
      }
      .hero p {
        margin: 0;
        max-width: 58ch;
        color: var(--muted);
        font-size: 1.05rem;
      }
      .grid {
        display: grid;
        grid-template-columns: 1.05fr 0.95fr;
        gap: 18px;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        backdrop-filter: blur(20px);
        box-shadow: var(--shadow);
        border-radius: var(--radius);
        padding: 20px;
      }
      .panel h2 {
        margin: 0 0 12px;
        font-size: 1.2rem;
      }
      .stack { display: grid; gap: 16px; }
      .row { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      label { display: grid; gap: 6px; font-size: 0.95rem; }
      input, select, textarea, button {
        width: 100%;
        border-radius: 16px;
        border: 1px solid rgba(54, 71, 91, 0.16);
        padding: 12px 14px;
        font: inherit;
      }
      textarea { min-height: 120px; resize: vertical; }
      button {
        border: none;
        background: var(--accent);
        color: #fff9f4;
        font-weight: 700;
        cursor: pointer;
        transition: transform 140ms ease, background 140ms ease;
      }
      button:hover { transform: translateY(-1px); background: var(--accent-strong); }
      .ghost {
        background: rgba(255,255,255,0.6);
        color: var(--text);
        border: 1px solid rgba(54, 71, 91, 0.16);
      }
      .metrics {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
      }
      .metric {
        padding: 14px;
        border-radius: 18px;
        background: rgba(255,255,255,0.52);
      }
      .metric strong {
        display: block;
        font-size: 1.5rem;
        margin-bottom: 6px;
      }
      .mono {
        font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        font-size: 0.88rem;
      }
      .status {
        min-height: 24px;
        color: var(--muted);
      }
      .status.success { color: var(--success); }
      .card-list, .feed {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 10px;
      }
      .feed li, .card-list li {
        background: rgba(255,255,255,0.52);
        border-radius: 18px;
        padding: 14px;
      }
      .feed time, .hint { color: var(--muted); font-size: 0.85rem; }
      @media (max-width: 980px) {
        .grid { grid-template-columns: 1fr; }
        .row, .metrics { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <span class="eyebrow">Open Messenger Frontend</span>
        <h1>Operate the platform from one browser console.</h1>
        <p>
          This UI follows the documented Native and Admin API flows: inspect service configuration,
          bootstrap a user token, create channels, post messages, and watch live events from the same screen.
        </p>
      </section>
      <section class="grid">
        <div class="stack">
          <article class="panel">
            <h2>Service Snapshot</h2>
            <div class="metrics" id="service-metrics">
              <div class="metric"><strong id="service-name">...</strong><span>service</span></div>
              <div class="metric"><strong id="service-version">...</strong><span>version</span></div>
              <div class="metric"><strong id="service-environment">...</strong><span>environment</span></div>
            </div>
            <p class="mono hint" id="service-details">Connecting to ${apiBaseUrl}</p>
          </article>
          <article class="panel">
            <h2>Admin Bootstrap</h2>
            <form class="stack" id="bootstrap-form">
              <div class="row">
                <label>Username
                  <input name="username" placeholder="alice" required />
                </label>
                <label>Display name
                  <input name="displayName" placeholder="Alice" />
                </label>
              </div>
              <div class="row">
                <label>Token type
                  <select name="tokenType">
                    <option value="user_token">user_token</option>
                    <option value="bot_token">bot_token</option>
                    <option value="service_token">service_token</option>
                  </select>
                </label>
                <label>Scopes
                  <input name="scopes" value="channels:read,channels:write,messages:read,messages:write" />
                </label>
              </div>
              <button type="submit">Create user and token</button>
            </form>
            <div class="status" id="bootstrap-status"></div>
            <ul class="card-list" id="identity-list"></ul>
          </article>
          <article class="panel">
            <h2>Channels and Messages</h2>
            <form class="stack" id="channel-form">
              <div class="row">
                <label>Access token
                  <input name="accessToken" id="access-token-input" placeholder="Paste token returned by Admin Bootstrap" required />
                </label>
                <label>Channel name
                  <input name="channelName" placeholder="general" required />
                </label>
              </div>
              <button type="submit">Create channel</button>
            </form>
            <div class="status" id="channel-status"></div>
            <form class="stack" id="message-form">
              <div class="row">
                <label>Channel ID
                  <input name="channelId" id="channel-id-input" placeholder="ch_..." required />
                </label>
                <label>Sender user ID
                  <input name="senderUserId" id="sender-user-id-input" placeholder="usr_..." />
                </label>
              </div>
              <label>Message text
                <textarea name="text" placeholder="Ship the update."></textarea>
              </label>
              <div class="row">
                <label>Idempotency key
                  <input name="idempotencyKey" placeholder="optional-request-key" />
                </label>
                <label>Actions
                  <div class="row">
                    <button type="submit">Send message</button>
                    <button type="button" class="ghost" id="refresh-messages">Load messages</button>
                  </div>
                </label>
              </div>
            </form>
            <div class="status" id="message-status"></div>
            <ul class="card-list" id="message-list"></ul>
          </article>
        </div>
        <div class="stack">
          <article class="panel">
            <h2>Live Event Stream</h2>
            <p class="hint">Uses the documented SSE channel through the frontend BFF so browser clients do not need to manage backend auth headers directly.</p>
            <div class="row">
              <button type="button" id="start-stream">Start stream</button>
              <button type="button" class="ghost" id="stop-stream">Stop stream</button>
            </div>
            <div class="status" id="stream-status"></div>
            <ul class="feed" id="event-feed"></ul>
          </article>
        </div>
      </section>
    </main>
    <script type="module">
      const state = {
        accessToken: "",
        stream: null
      };

      const qs = (id) => document.getElementById(id);
      const text = (id, value) => { qs(id).textContent = value; };
      const escapeHtml = (value) =>
        String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      const setStatus = (id, value, success = false) => {
        const node = qs(id);
        node.textContent = value;
        node.className = success ? "status success" : "status";
      };

      async function request(path, options = {}) {
        const response = await fetch(path, {
          method: options.method || "GET",
          headers: {
            "content-type": "application/json"
          },
          body: options.body ? JSON.stringify(options.body) : undefined
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || data.message || "Request failed");
        }
        return data;
      }

      function prependCard(targetId, html) {
        const list = qs(targetId);
        const item = document.createElement("li");
        item.innerHTML = html;
        list.prepend(item);
      }

      async function loadInfo() {
        const info = await request("/api/info");
        text("service-name", info.service);
        text("service-version", info.version);
        text("service-environment", info.environment);
        text(
          "service-details",
          [info.content_backend, info.metadata_backend, info.file_storage_backend, info.content_store_impl, info.metadata_store_impl, info.file_store_impl].join(" / ")
        );
      }

      qs("bootstrap-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setStatus("bootstrap-status", "Creating user and token...");
        try {
          const payload = {
            username: String(form.get("username") || "").trim(),
            displayName: String(form.get("displayName") || "").trim(),
            tokenType: String(form.get("tokenType") || "user_token"),
            scopes: String(form.get("scopes") || "")
              .split(",")
              .map((scope) => scope.trim())
              .filter(Boolean)
          };
          const data = await request("/api/bootstrap", { method: "POST", body: payload });
          state.accessToken = data.token.token;
          qs("access-token-input").value = data.token.token;
          qs("sender-user-id-input").value = data.user.user_id;
          prependCard(
            "identity-list",
            "<strong>" + escapeHtml(data.user.username) + "</strong><div class='mono'>" + escapeHtml(data.user.user_id) + "</div><div class='mono'>" + escapeHtml(data.token.token_id) + "</div><div class='mono'>" + escapeHtml(data.token.token) + "</div>"
          );
          setStatus("bootstrap-status", "Admin bootstrap completed.", true);
        } catch (error) {
          setStatus("bootstrap-status", error.message);
        }
      });

      qs("channel-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setStatus("channel-status", "Creating channel...");
        try {
          const accessToken = String(form.get("accessToken") || "").trim();
          state.accessToken = accessToken;
          const channel = await request("/api/channels", {
            method: "POST",
            body: {
              accessToken,
              name: String(form.get("channelName") || "").trim()
            }
          });
          qs("channel-id-input").value = channel.channel_id;
          prependCard(
            "message-list",
            "<strong>Channel ready:</strong> " + escapeHtml(channel.name) + "<div class='mono'>" + escapeHtml(channel.channel_id) + "</div>"
          );
          setStatus("channel-status", "Channel created.", true);
        } catch (error) {
          setStatus("channel-status", error.message);
        }
      });

      async function loadMessages() {
        const accessToken = qs("access-token-input").value.trim();
        const channelId = qs("channel-id-input").value.trim();
        setStatus("message-status", "Loading messages...");
        try {
          const data = await request("/api/messages/list", {
            method: "POST",
            body: { accessToken, channelId }
          });
          const list = qs("message-list");
          list.innerHTML = "";
          for (const item of data.items) {
            prependCard(
              "message-list",
              "<strong>" + escapeHtml(item.sender_user_id) + "</strong><div>" + escapeHtml(item.text) + "</div><div class='mono'>" + escapeHtml(item.message_id) + "</div>"
            );
          }
          setStatus("message-status", "Messages loaded.", true);
        } catch (error) {
          setStatus("message-status", error.message);
        }
      }

      qs("message-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setStatus("message-status", "Sending message...");
        try {
          const payload = {
            accessToken: String(qs("access-token-input").value || "").trim(),
            channelId: String(form.get("channelId") || "").trim(),
            text: String(form.get("text") || "").trim(),
            senderUserId: String(form.get("senderUserId") || "").trim(),
            idempotencyKey: String(form.get("idempotencyKey") || "").trim()
          };
          const message = await request("/api/messages", { method: "POST", body: payload });
          prependCard(
            "message-list",
            "<strong>" + escapeHtml(message.sender_user_id) + "</strong><div>" + escapeHtml(message.text) + "</div><div class='mono'>" + escapeHtml(message.message_id) + "</div>"
          );
          qs("message-form").reset();
          qs("channel-id-input").value = payload.channelId;
          qs("access-token-input").value = payload.accessToken;
          if (payload.senderUserId) {
            qs("sender-user-id-input").value = payload.senderUserId;
          }
          setStatus("message-status", "Message accepted by backend.", true);
        } catch (error) {
          setStatus("message-status", error.message);
        }
      });

      qs("refresh-messages").addEventListener("click", loadMessages);

      qs("start-stream").addEventListener("click", () => {
        const accessToken = qs("access-token-input").value.trim();
        if (!accessToken) {
          setStatus("stream-status", "Access token is required before opening the stream.");
          return;
        }
        if (state.stream) {
          state.stream.close();
        }
        const url = "/api/events?access_token=" + encodeURIComponent(accessToken);
        const stream = new EventSource(url);
        state.stream = stream;
        setStatus("stream-status", "Connecting to SSE stream...");
        stream.onopen = () => setStatus("stream-status", "SSE stream connected.", true);
        stream.onerror = () => setStatus("stream-status", "SSE stream interrupted.");
        stream.onmessage = (event) => {
          prependCard("event-feed", "<time>" + new Date().toISOString() + "</time><div class='mono'>" + escapeHtml(event.data) + "</div>");
        };
      });

      qs("stop-stream").addEventListener("click", () => {
        if (state.stream) {
          state.stream.close();
          state.stream = null;
        }
        setStatus("stream-status", "SSE stream closed.");
      });

      loadInfo().catch((error) => {
        text("service-details", error.message);
      });
    </script>
  </body>
</html>`;
}
