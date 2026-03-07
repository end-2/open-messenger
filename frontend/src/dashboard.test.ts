import assert from "node:assert/strict";
import test from "node:test";

import { renderChatPage, renderHomePage } from "./dashboard.ts";

test("renderHomePage includes service and user bootstrap sections", () => {
  const html = renderHomePage({
    port: 3001,
    apiBaseUrl: "http://127.0.0.1:8000",
    adminToken: "dev-admin-token"
  });

  assert.match(html, /Open Messenger Frontend/);
  assert.match(html, /Service Snapshot/);
  assert.match(html, /User Creation/);
  assert.doesNotMatch(html, /Channels and Messages/);
  assert.match(html, /http:\/\/127\.0\.0\.1:8000/);
  assert.match(html, /class="card-list identity-output"/);
  assert.match(html, /\.preformatted \{/);
  assert.match(html, /function escapeClientHtml\(value\)/);
  assert.match(html, /escapeClientHtml\(formatJson\(payload\.user\)\)/);
  assert.match(html, /escapeClientHtml\(formatJson\(payload\.token\)\)/);
});

test("renderChatPage includes dedicated chat workflow sections", () => {
  const html = renderChatPage();

  assert.match(html, /Create Channel/);
  assert.match(html, /Live Event Stream/);
  assert.match(html, /Authenticated sender/);
  assert.match(html, /id="thread-sidebar" hidden/);
  assert.match(html, /id="close-thread"/);
  assert.match(html, /id="thread-panel"/);
  assert.match(html, /class="chat-layout chat-shell" id="chat-layout"/);
  assert.match(html, /class="scroll-region message-stream" id="message-list"/);
  assert.match(html, /class="feed scroll-region" id="event-feed"/);
  assert.match(html, /class="break-anywhere" name="accessToken"/);
  assert.match(html, /class="composer-shell"/);
  assert.match(html, /class="workspace-name">Open Messenger</);
  assert.doesNotMatch(html, /Sender user ID/);
  assert.doesNotMatch(html, /Idempotency key/);
  assert.doesNotMatch(html, /<h1/);
  assert.match(html, /function escapeClientHtml\(value\)/);
  assert.match(html, /function formatSenderLabel\(message\)/);
  assert.match(html, /function formatIdentityLabel\(identity\)/);
  assert.match(html, /function toggleThreadSidebar\(isOpen\)/);
  assert.match(html, /sender_display_name/);
  assert.match(html, /items\.filter\(\(item\) => !item\.thread_id\)/);
  assert.match(html, /Open the room to read messages and start threads\./);
  assert.match(html, /escapeClientHtml\(event\.data\)/);
});
