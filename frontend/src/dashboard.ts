import type { FrontendConfig } from "./config.ts";

export function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function renderBasePage(title: string, bodyClass: string, content: string): string {
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${title}</title>
    <style>
      :root {
        --bg: linear-gradient(135deg, #f3efe4 0%, #d7e3f1 48%, #f0c9ae 100%);
        --panel: rgba(255, 252, 248, 0.8);
        --panel-strong: rgba(255, 255, 255, 0.92);
        --border: rgba(54, 71, 91, 0.18);
        --text: #1d2a37;
        --muted: #55687d;
        --accent: #d0572f;
        --accent-strong: #8f2f1e;
        --accent-soft: rgba(208, 87, 47, 0.12);
        --success: #0f7b50;
        --shadow: 0 20px 50px rgba(43, 55, 72, 0.18);
        --radius: 24px;
      }
      * { box-sizing: border-box; }
      html { height: 100%; }
      body {
        margin: 0;
        font-family: Georgia, "Times New Roman", serif;
        color: var(--text);
        background: var(--bg);
        min-height: 100dvh;
      }
      a { color: inherit; }
      .shell {
        max-width: 1320px;
        margin: 0 auto;
        padding: 32px 20px 48px;
      }
      .shell > * {
        min-width: 0;
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
      }
      h2, h3, p { margin-top: 0; }
      p {
        color: var(--muted);
        font-size: 1rem;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        backdrop-filter: blur(20px);
        box-shadow: var(--shadow);
        border-radius: var(--radius);
        padding: 20px;
        min-width: 0;
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
        min-width: 0;
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
      button:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
      .ghost {
        background: rgba(255,255,255,0.62);
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
      .break-anywhere {
        overflow-wrap: anywhere;
        word-break: break-word;
      }
      .preformatted {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        word-break: break-word;
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
      .message-actions {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        margin-top: 12px;
      }
      .thread-shell {
        display: grid;
        grid-template-rows: auto minmax(0, 1fr) auto;
        gap: 14px;
        min-height: 0;
      }
      .thread-root,
      .thread-reply {
        border-radius: 18px;
        padding: 14px;
        background: rgba(255,255,255,0.58);
      }
      .thread-root {
        border: 1px solid rgba(208, 87, 47, 0.24);
      }
      .thread-feed {
        display: grid;
        gap: 10px;
        align-content: start;
      }
      .pill {
        display: inline-flex;
        align-items: center;
        min-height: 28px;
        padding: 0 10px;
        border-radius: 999px;
        background: var(--accent-soft);
        color: var(--accent-strong);
        font-size: 0.8rem;
        font-weight: 700;
      }
      .button-link {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 48px;
        padding: 0 20px;
        border-radius: 16px;
        text-decoration: none;
        background: var(--accent);
        color: #fff9f4;
        font-weight: 700;
      }
      .button-link.ghost {
        background: rgba(255,255,255,0.62);
        color: var(--text);
      }
      .home-grid,
      .chat-layout {
        display: grid;
        gap: 18px;
        min-width: 0;
      }
      .home-grid {
        grid-template-columns: 1.02fr 0.98fr;
        align-items: start;
      }
      .identity-output {
        overflow: auto;
        max-height: min(32rem, 42dvh);
      }
      .viewport-panel {
        height: clamp(32rem, calc(100dvh - 18rem), 52rem);
        min-height: 0;
      }
      .sidebar-panel,
      .stream-panel,
      .chat-panel {
        min-height: 0;
        overflow: hidden;
      }
      .sidebar-panel {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .chat-panel {
        display: grid;
        grid-template-rows: auto minmax(0, 1fr) auto;
        gap: 16px;
      }
      .stream-panel {
        display: flex;
        flex-direction: column;
        gap: 16px;
      }
      .scroll-region {
        min-height: 0;
        overflow: auto;
        padding-right: 4px;
      }
      .channel-list {
        min-height: 0;
        overflow: auto;
      }
      .chat-layout {
        grid-template-columns: 320px minmax(0, 1fr) 320px;
        align-items: stretch;
      }
      body.chat-body .shell {
        max-width: 1440px;
        padding-bottom: 24px;
      }
      body.chat-body main.shell {
        min-height: 100dvh;
      }
      @media (max-width: 980px) {
        .row, .metrics, .home-grid, .chat-layout, .hero { grid-template-columns: 1fr; }
        .chat-layout {
          grid-auto-rows: minmax(18rem, 1fr);
        }
      }
    </style>
  </head>
  <body class="${bodyClass}">
${content}
  </body>
</html>`;
}

export function renderHomePage(config: FrontendConfig): string {
  const apiBaseUrl = escapeHtml(config.apiBaseUrl);

  return renderBasePage(
    "Open Messenger Console",
    "home-body",
    `    <main class="shell">
      <section class="hero">
        <span class="eyebrow">Open Messenger Frontend</span>
        <h1>Prepare the workspace, then enter the chat console.</h1>
        <p>
          Start here to inspect the service and mint a user token. Channel management and the message
          experience now live in a dedicated chat page with a room-style layout.
        </p>
      </section>
      <section class="home-grid">
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
            <h2>Open Chat Workspace</h2>
            <p>
              Move to the dedicated chat page to create channels, load room history, send messages,
              and watch the live event stream in a chat-style interface.
            </p>
            <div class="row">
              <a class="button-link" href="/chat">Enter chat console</a>
              <button type="button" class="ghost" id="chat-link-with-token">Open with saved token</button>
            </div>
            <p class="hint">If you bootstrap a user here, the returned token is stored locally and can be reused on the chat page.</p>
          </article>
        </div>
        <div class="stack">
          <article class="panel viewport-panel">
            <h2>User Creation</h2>
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
              <div class="row">
                <button type="submit">Create user and token</button>
                <a class="button-link ghost" href="/chat">Go to channels and messages</a>
              </div>
            </form>
            <div class="status" id="bootstrap-status"></div>
            <ul class="card-list identity-output" id="identity-list"></ul>
          </article>
        </div>
      </section>
    </main>
    <script type="module">
      const serviceName = document.querySelector("#service-name");
      const serviceVersion = document.querySelector("#service-version");
      const serviceEnvironment = document.querySelector("#service-environment");
      const serviceDetails = document.querySelector("#service-details");
      const bootstrapForm = document.querySelector("#bootstrap-form");
      const bootstrapStatus = document.querySelector("#bootstrap-status");
      const identityList = document.querySelector("#identity-list");
      const chatLinkWithToken = document.querySelector("#chat-link-with-token");

      function setStatus(element, message, isSuccess = false) {
        element.textContent = message;
        element.className = isSuccess ? "status success" : "status";
      }

      function formatJson(value) {
        return JSON.stringify(value, null, 2);
      }

      function saveIdentity(payload) {
        localStorage.setItem("openMessenger.identity", JSON.stringify(payload));
      }

      async function loadInfo() {
        try {
          const response = await fetch("/api/info");
          if (!response.ok) {
            throw new Error("Unable to load service info");
          }
          const info = await response.json();
          serviceName.textContent = info.service;
          serviceVersion.textContent = info.version;
          serviceEnvironment.textContent = info.environment;
          serviceDetails.textContent =
            info.content_backend + " content / " +
            info.metadata_backend + " metadata / " +
            info.file_storage_backend + " files";
        } catch (error) {
          serviceDetails.textContent = error instanceof Error ? error.message : "Unknown error";
        }
      }

      chatLinkWithToken.addEventListener("click", () => {
        const rawIdentity = localStorage.getItem("openMessenger.identity");
        if (!rawIdentity) {
          window.location.href = "/chat";
          return;
        }

        try {
          const identity = JSON.parse(rawIdentity);
          const token = typeof identity.token?.token === "string" ? identity.token.token : "";
          window.location.href = token ? "/chat?access_token=" + encodeURIComponent(token) : "/chat";
        } catch {
          window.location.href = "/chat";
        }
      });

      bootstrapForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(bootstrapForm);
        const username = String(form.get("username") || "").trim();
        const displayName = String(form.get("displayName") || "").trim();
        const tokenType = String(form.get("tokenType") || "user_token");
        const scopes = String(form.get("scopes") || "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);

        setStatus(bootstrapStatus, "Creating user and token...");
        identityList.innerHTML = "";

        try {
          const response = await fetch("/api/bootstrap", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ username, displayName, tokenType, scopes })
          });

          const payload = await response.json();
          if (!response.ok) {
            throw new Error(formatJson(payload));
          }

          saveIdentity(payload);
          setStatus(bootstrapStatus, "User and token created. The token is saved for the chat page.", true);
          identityList.innerHTML = [
            "<li><strong>User</strong><pre class=\\"mono preformatted\\">" + formatJson(payload.user) + "</pre></li>",
            "<li><strong>Token</strong><pre class=\\"mono preformatted\\">" + formatJson(payload.token) + "</pre></li>"
          ].join("");
        } catch (error) {
          setStatus(bootstrapStatus, error instanceof Error ? error.message : "Unknown error");
        }
      });

      loadInfo();
    </script>`
  );
}

export function renderChatPage(): string {
  return renderBasePage(
    "Open Messenger Chat Console",
    "chat-body",
    `    <main class="shell">
      <section class="hero" style="grid-template-columns: 1.2fr auto; align-items:end;">
        <div>
          <span class="eyebrow">Channels and Messages</span>
          <h1 style="max-width: 12ch;">Enter rooms, read history, and send messages.</h1>
          <p>
            This page isolates the message workflow into a more typical chat-room layout with a channel rail,
            a room transcript, a composer, and the live event stream.
          </p>
        </div>
        <div style="display:grid; gap:12px;">
          <a class="button-link ghost" href="/">Back to service setup</a>
        </div>
      </section>
      <section class="chat-layout viewport-panel">
        <aside class="panel sidebar-panel">
          <div>
            <h2>Session</h2>
            <p class="hint">Use the token from the first page or paste another Native API token.</p>
          </div>
          <label>Access token
            <input class="break-anywhere" name="accessToken" id="access-token-input" placeholder="Paste access token" required />
          </label>
          <div class="row">
            <button type="button" id="save-session">Save token</button>
            <button type="button" class="ghost" id="clear-session">Clear</button>
          </div>
          <div class="status" id="session-status"></div>
          <hr style="border:none; border-top:1px solid var(--border); width:100%; margin:0;" />
          <div>
            <h2>Create Channel</h2>
            <form class="stack" id="channel-form">
              <label>Channel name
                <input name="channelName" placeholder="general" required />
              </label>
              <button type="submit">Create channel</button>
            </form>
            <div class="status" id="channel-status"></div>
          </div>
          <div class="stack" style="min-height:0;">
            <div style="display:flex; justify-content:space-between; gap:12px; align-items:center;">
              <h2 style="margin-bottom:0;">Rooms</h2>
              <button type="button" class="ghost" id="refresh-messages">Refresh room</button>
            </div>
            <p class="hint">Created rooms are kept in local storage for quick re-entry.</p>
            <ul class="card-list channel-list" id="channel-list"></ul>
          </div>
        </aside>
        <section class="panel chat-panel">
          <header style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start; border-bottom:1px solid var(--border); padding-bottom:16px;">
            <div>
              <p class="eyebrow" style="margin-bottom:6px;">Active Room</p>
              <h2 id="active-channel-name" style="margin-bottom:4px;">Select a channel</h2>
              <p class="mono hint break-anywhere" id="active-channel-id">No channel selected.</p>
            </div>
            <div style="min-width: 220px;">
              <div class="hint">Authenticated sender</div>
              <div class="mono break-anywhere" id="session-user-id">Unknown user</div>
            </div>
          </header>
          <div class="scroll-region" id="message-list" style="display:grid; gap:12px; align-content:start;"></div>
          <form class="stack" id="message-form" style="border-top:1px solid var(--border); padding-top:16px;">
            <input type="hidden" name="channelId" id="channel-id-input" />
            <label>Message
              <textarea name="text" placeholder="Write to the room" style="min-height:100px;"></textarea>
            </label>
            <div class="row">
              <label>Idempotency key
                <input name="idempotencyKey" placeholder="optional-request-key" />
              </label>
              <div style="display:grid; align-content:end;">
                <button type="submit">Send message</button>
              </div>
            </div>
            <div class="status" id="message-status"></div>
          </form>
        </section>
        <aside class="panel stream-panel">
          <section class="thread-shell" style="flex:1;">
            <div>
              <h2>Thread</h2>
              <p class="hint">Open a message thread to inspect replies and continue the conversation.</p>
            </div>
            <div class="scroll-region" id="thread-panel">
              <article class="thread-root">
                <strong>No thread selected.</strong>
                <p class="hint" style="margin:8px 0 0;">Use the transcript actions to start or open a thread.</p>
              </article>
            </div>
            <form class="stack" id="thread-form" style="border-top:1px solid var(--border); padding-top:14px;">
              <label>Thread reply
                <textarea name="text" placeholder="Reply in the active thread" style="min-height:92px;"></textarea>
              </label>
              <div class="row">
                <label>Idempotency key
                  <input name="idempotencyKey" placeholder="optional-thread-request-key" />
                </label>
                <div style="display:grid; align-content:end;">
                  <button type="submit">Send reply</button>
                </div>
              </div>
              <div class="status" id="thread-status"></div>
            </form>
          </section>
          <section class="stack" style="min-height: 18rem; flex:1;">
            <div>
              <h2>Live Event Stream</h2>
              <p class="hint">The browser connects through the frontend SSE proxy.</p>
            </div>
            <div class="row">
              <button type="button" id="start-stream">Start stream</button>
              <button type="button" class="ghost" id="stop-stream">Stop stream</button>
            </div>
            <div class="status" id="stream-status"></div>
            <ul class="feed scroll-region" id="event-feed"></ul>
          </section>
        </aside>
      </section>
    </main>
    <script type="module">
      const accessTokenInput = document.querySelector("#access-token-input");
      const sessionStatus = document.querySelector("#session-status");
      const saveSessionButton = document.querySelector("#save-session");
      const clearSessionButton = document.querySelector("#clear-session");
      const channelForm = document.querySelector("#channel-form");
      const channelStatus = document.querySelector("#channel-status");
      const channelList = document.querySelector("#channel-list");
      const activeChannelName = document.querySelector("#active-channel-name");
      const activeChannelId = document.querySelector("#active-channel-id");
      const channelIdInput = document.querySelector("#channel-id-input");
      const sessionUserId = document.querySelector("#session-user-id");
      const messageForm = document.querySelector("#message-form");
      const messageStatus = document.querySelector("#message-status");
      const messageList = document.querySelector("#message-list");
      const threadPanel = document.querySelector("#thread-panel");
      const threadForm = document.querySelector("#thread-form");
      const threadStatus = document.querySelector("#thread-status");
      const refreshMessagesButton = document.querySelector("#refresh-messages");
      const startStreamButton = document.querySelector("#start-stream");
      const stopStreamButton = document.querySelector("#stop-stream");
      const streamStatus = document.querySelector("#stream-status");
      const eventFeed = document.querySelector("#event-feed");

      let activeChannel = null;
      let activeThread = null;
      let eventSource = null;

      function setStatus(element, message, isSuccess = false) {
        element.textContent = message;
        element.className = isSuccess ? "status success" : "status";
      }

      function formatJson(value) {
        return JSON.stringify(value, null, 2);
      }

      function formatTimestamp(value) {
        try {
          return new Date(value).toLocaleString();
        } catch {
          return value;
        }
      }

      function escapeClientHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll("\"", "&quot;")
          .replaceAll("'", "&#39;");
      }

      function readStoredIdentity() {
        try {
          return JSON.parse(localStorage.getItem("openMessenger.identity") || "null");
        } catch {
          return null;
        }
      }

      function readStoredChannels() {
        try {
          const channels = JSON.parse(localStorage.getItem("openMessenger.channels") || "[]");
          return Array.isArray(channels) ? channels : [];
        } catch {
          return [];
        }
      }

      function writeStoredChannels(channels) {
        localStorage.setItem("openMessenger.channels", JSON.stringify(channels));
      }

      function getAccessToken() {
        return accessTokenInput.value.trim();
      }

      function addOrUpdateChannel(channel) {
        const channels = readStoredChannels();
        const nextChannels = [channel, ...channels.filter((item) => item.channel_id !== channel.channel_id)].slice(0, 12);
        writeStoredChannels(nextChannels);
        renderChannelList();
      }

      function renderChannelList() {
        const channels = readStoredChannels();
        channelList.innerHTML = "";

        if (channels.length === 0) {
          channelList.innerHTML = "<li><strong>No rooms yet.</strong><div class=\\"hint\\">Create one to start chatting.</div></li>";
          return;
        }

        for (const channel of channels) {
          const item = document.createElement("li");
          item.style.cursor = "pointer";
          item.style.border = activeChannel && activeChannel.channel_id === channel.channel_id
            ? "1px solid rgba(208, 87, 47, 0.35)"
            : "1px solid transparent";
          item.innerHTML = [
            "<strong># " + channel.name + "</strong>",
            "<div class=\\"mono hint\\">" + channel.channel_id + "</div>",
            "<div class=\\"hint\\">Created " + formatTimestamp(channel.created_at) + "</div>"
          ].join("");
          item.addEventListener("click", () => {
            setActiveChannel(channel);
            void loadMessages();
          });
          channelList.appendChild(item);
        }
      }

      function setActiveChannel(channel) {
        activeChannel = channel;
        activeThread = null;
        channelIdInput.value = channel.channel_id;
        activeChannelName.textContent = "# " + channel.name;
        activeChannelId.textContent = channel.channel_id;
        renderChannelList();
        renderThreadPanel();
      }

      function renderMessages(items) {
        messageList.innerHTML = "";

        if (!items.length) {
          messageList.innerHTML = "<article class=\\"panel\\" style=\\"padding:16px; background:var(--panel-strong);\\"><strong>No messages yet.</strong><p class=\\"hint\\" style=\\"margin-bottom:0;\\">Send the first message to this room.</p></article>";
          return;
        }

        for (const item of items) {
          const bubble = document.createElement("article");
          bubble.className = "panel";
          bubble.style.padding = "16px";
          bubble.style.background = "var(--panel-strong)";
          const threadButtonLabel = item.thread_id ? "Open thread" : "Start thread";
          bubble.innerHTML = [
            "<div style=\\"display:flex; justify-content:space-between; gap:12px; align-items:center;\\">",
            "<strong>" + escapeClientHtml(item.sender_user_id || "unknown sender") + "</strong>",
            "<time class=\\"hint\\">" + formatTimestamp(item.created_at) + "</time>",
            "</div>",
            "<p class=\\"preformatted\\" style=\\"color:var(--text); margin:12px 0 10px;\\">" + escapeClientHtml(item.text) + "</p>",
            "<div class=\\"mono hint break-anywhere\\">" + escapeClientHtml(item.message_id) + "</div>",
            "<div class=\\"message-actions\\">",
            "<span class=\\"pill\\">" + (item.thread_id ? "thread reply" : "channel message") + "</span>",
            "<button type=\\"button\\" class=\\"ghost\\" data-message-id=\\"" + escapeClientHtml(item.message_id) + "\\" data-thread-id=\\"" + escapeClientHtml(item.thread_id || "") + "\\">" + threadButtonLabel + "</button>",
            "</div>"
          ].join("");
          const threadButton = bubble.querySelector("button[data-message-id]");
          threadButton?.addEventListener("click", async () => {
            try {
              await openThreadForMessage(item);
            } catch (error) {
              setStatus(threadStatus, error instanceof Error ? error.message : "Unknown error");
            }
          });
          messageList.appendChild(bubble);
        }

        messageList.scrollTop = messageList.scrollHeight;
      }

      function renderThreadPanel(context = activeThread) {
        if (!context) {
          threadPanel.innerHTML = [
            "<article class=\\"thread-root\\">",
            "<strong>No thread selected.</strong>",
            "<p class=\\"hint\\" style=\\"margin:8px 0 0;\\">Use the transcript actions to start or open a thread.</p>",
            "</article>"
          ].join("");
          return;
        }

        const rootMessage = context.root_message;
        const replies = context.replies || [];
        const sections = [
          "<article class=\\"thread-root\\">",
          "<div style=\\"display:flex; justify-content:space-between; gap:12px; align-items:center;\\">",
          "<strong>" + escapeClientHtml(rootMessage.sender_user_id || "unknown sender") + "</strong>",
          "<span class=\\"pill\\">root</span>",
          "</div>",
          "<p class=\\"preformatted\\" style=\\"color:var(--text); margin:12px 0 10px;\\">" + escapeClientHtml(rootMessage.text) + "</p>",
          "<div class=\\"mono hint break-anywhere\\">" + escapeClientHtml(context.thread.thread_id) + "</div>",
          "<div class=\\"hint\\" style=\\"margin-top:8px;\\">" + String(context.thread.reply_count) + " replies, last activity " + formatTimestamp(context.thread.last_message_at) + "</div>",
          "</article>"
        ];

        if (!replies.length) {
          sections.push("<article class=\\"thread-reply\\"><strong>No replies yet.</strong><p class=\\"hint\\" style=\\"margin:8px 0 0;\\">Send the first reply in this thread.</p></article>");
        } else {
          sections.push("<div class=\\"thread-feed\\">");
          for (const reply of replies) {
            sections.push([
              "<article class=\\"thread-reply\\">",
              "<div style=\\"display:flex; justify-content:space-between; gap:12px; align-items:center;\\">",
              "<strong>" + escapeClientHtml(reply.sender_user_id || "unknown sender") + "</strong>",
              "<time class=\\"hint\\">" + formatTimestamp(reply.created_at) + "</time>",
              "</div>",
              "<p class=\\"preformatted\\" style=\\"color:var(--text); margin:12px 0 10px;\\">" + escapeClientHtml(reply.text) + "</p>",
              "<div class=\\"mono hint break-anywhere\\">" + escapeClientHtml(reply.message_id) + "</div>",
              "</article>"
            ].join(""));
          }
          sections.push("</div>");
        }

        if (context.has_more_replies) {
          sections.push("<p class=\\"hint\\" style=\\"margin:0;\\">Additional replies exist beyond the current thread view limit.</p>");
        }

        threadPanel.innerHTML = sections.join("");
      }

      async function loadThreadContext(threadId) {
        const accessToken = getAccessToken();
        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }

        setStatus(threadStatus, "Loading thread...");

        const response = await fetch("/api/threads/context", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ accessToken, threadId })
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(formatJson(payload));
        }

        activeThread = payload;
        renderThreadPanel(payload);
        setStatus(threadStatus, "Thread loaded.", true);
      }

      async function openThreadForMessage(message) {
        const accessToken = getAccessToken();
        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }

        if (message.thread_id) {
          await loadThreadContext(message.thread_id);
          return;
        }

        setStatus(threadStatus, "Opening thread...");
        const response = await fetch("/api/threads", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            accessToken,
            channelId: activeChannel?.channel_id || "",
            rootMessageId: message.message_id
          })
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(formatJson(payload));
        }

        await loadThreadContext(payload.thread_id);
      }

      async function loadMessages() {
        if (!activeChannel) {
          setStatus(messageStatus, "Select a room first.");
          return;
        }

        const accessToken = getAccessToken();
        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }

        setStatus(messageStatus, "Loading messages...");

        try {
          const response = await fetch("/api/messages/list", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              accessToken,
              channelId: activeChannel.channel_id
            })
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(formatJson(payload));
          }

          renderMessages(payload.items || []);
          setStatus(messageStatus, "Messages loaded.", true);
        } catch (error) {
          setStatus(messageStatus, error instanceof Error ? error.message : "Unknown error");
        }
      }

      function restoreSession() {
        const params = new URLSearchParams(window.location.search);
        const tokenFromUrl = params.get("access_token");
        const storedIdentity = readStoredIdentity();
        const storedToken = typeof storedIdentity?.token?.token === "string" ? storedIdentity.token.token : "";
        const storedUserId = typeof storedIdentity?.user?.user_id === "string" ? storedIdentity.user.user_id : "";
        accessTokenInput.value = tokenFromUrl || storedToken;
        sessionUserId.textContent = storedUserId || "Unknown user";

        if (accessTokenInput.value) {
          setStatus(sessionStatus, "Session restored from saved identity.", true);
        }
      }

      saveSessionButton.addEventListener("click", () => {
        const token = getAccessToken();
        if (!token) {
          setStatus(sessionStatus, "Paste a token before saving.");
          return;
        }

        const identity = readStoredIdentity();
        const nextIdentity = {
          user: identity?.user || null,
          token: {
            ...(identity?.token || {}),
            token
          }
        };
        localStorage.setItem("openMessenger.identity", JSON.stringify(nextIdentity));
        setStatus(sessionStatus, "Token saved for this browser.", true);
      });

      clearSessionButton.addEventListener("click", () => {
        accessTokenInput.value = "";
        sessionUserId.textContent = "Unknown user";
        localStorage.removeItem("openMessenger.identity");
        setStatus(sessionStatus, "Saved token cleared.", true);
      });

      channelForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = new FormData(channelForm);
        const name = String(form.get("channelName") || "").trim();
        const accessToken = getAccessToken();

        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }

        setStatus(channelStatus, "Creating channel...");

        try {
          const response = await fetch("/api/channels", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ accessToken, name })
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(formatJson(payload));
          }

          addOrUpdateChannel(payload);
          setActiveChannel(payload);
          channelForm.reset();
          setStatus(channelStatus, "Channel created.", true);
          await loadMessages();
        } catch (error) {
          setStatus(channelStatus, error instanceof Error ? error.message : "Unknown error");
        }
      });

      messageForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const accessToken = getAccessToken();
        const form = new FormData(messageForm);
        const channelId = String(form.get("channelId") || "").trim();
        const text = String(form.get("text") || "").trim();
        const idempotencyKey = String(form.get("idempotencyKey") || "").trim();

        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }
        if (!channelId) {
          setStatus(messageStatus, "Select a room before sending.");
          return;
        }

        setStatus(messageStatus, "Sending message...");

        try {
          const response = await fetch("/api/messages", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              accessToken,
              channelId,
              text,
              idempotencyKey
            })
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(formatJson(payload));
          }

          messageForm.reset();
          channelIdInput.value = channelId;
          setStatus(messageStatus, "Message sent.", true);
          await loadMessages();
        } catch (error) {
          setStatus(messageStatus, error instanceof Error ? error.message : "Unknown error");
        }
      });

      threadForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const accessToken = getAccessToken();
        const form = new FormData(threadForm);
        const text = String(form.get("text") || "").trim();
        const idempotencyKey = String(form.get("idempotencyKey") || "").trim();

        if (!accessToken) {
          setStatus(sessionStatus, "An access token is required.");
          return;
        }
        if (!activeThread?.thread?.thread_id) {
          setStatus(threadStatus, "Open a thread before replying.");
          return;
        }

        setStatus(threadStatus, "Sending thread reply...");

        try {
          const response = await fetch("/api/threads/messages", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              accessToken,
              threadId: activeThread.thread.thread_id,
              text,
              idempotencyKey
            })
          });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(formatJson(payload));
          }

          threadForm.reset();
          setStatus(threadStatus, "Thread reply sent.", true);
          await Promise.all([
            loadThreadContext(activeThread.thread.thread_id),
            loadMessages()
          ]);
        } catch (error) {
          setStatus(threadStatus, error instanceof Error ? error.message : "Unknown error");
        }
      });

      refreshMessagesButton.addEventListener("click", () => {
        void loadMessages();
      });

      startStreamButton.addEventListener("click", () => {
        const accessToken = getAccessToken();
        if (!accessToken) {
          setStatus(streamStatus, "An access token is required.");
          return;
        }

        if (eventSource) {
          eventSource.close();
        }

        eventFeed.innerHTML = "";
        eventSource = new EventSource("/api/events?access_token=" + encodeURIComponent(accessToken));
        setStatus(streamStatus, "Listening for events...");

        eventSource.onmessage = (event) => {
          const item = document.createElement("li");
          item.innerHTML = "<time>" + new Date().toLocaleTimeString() + "</time><pre class=\\"mono preformatted\\" style=\\"margin:8px 0 0;\\">" + event.data.replaceAll("<", "&lt;").replaceAll(">", "&gt;") + "</pre>";
          eventFeed.prepend(item);
        };

        eventSource.onerror = () => {
          setStatus(streamStatus, "Event stream disconnected.");
        };
      });

      stopStreamButton.addEventListener("click", () => {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        setStatus(streamStatus, "Event stream stopped.", true);
      });

      restoreSession();
      renderChannelList();
      renderThreadPanel();
      const channels = readStoredChannels();
      if (channels.length > 0) {
        setActiveChannel(channels[0]);
      }
    </script>`
  );
}
