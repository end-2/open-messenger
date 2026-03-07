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

  assert.match(html, /Channels and Messages/);
  assert.match(html, /Create Channel/);
  assert.match(html, /Live Event Stream/);
  assert.match(html, /Active Room/);
  assert.match(html, /Authenticated sender/);
  assert.match(html, /Open a message thread/);
  assert.match(html, /id="thread-panel"/);
  assert.match(html, /class="chat-layout viewport-panel"/);
  assert.match(html, /class="scroll-region" id="message-list"/);
  assert.match(html, /class="feed scroll-region" id="event-feed"/);
  assert.match(html, /class="break-anywhere" name="accessToken"/);
  assert.doesNotMatch(html, /Sender user ID/);
  assert.match(html, /function escapeClientHtml\(value\)/);
  assert.match(html, /function formatSenderLabel\(message\)/);
  assert.match(html, /sender_display_name/);
  assert.match(html, /escapeClientHtml\(event\.data\)/);
});
