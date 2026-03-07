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
  assert.match(html, /class="panel home-grid-summary"/);
  assert.match(html, /class="panel viewport-panel home-grid-workspace"/);
  assert.match(html, /class="panel home-grid-user"/);
  assert.match(html, /class="detail-dialog" id="identity-detail-dialog"/);
  assert.match(html, /id="identity-detail-content"/);
  assert.match(html, /class="card-list identity-output"/);
  assert.match(html, /id="chat-entry-form"/);
  assert.match(html, /id="chat-entry-token"/);
  assert.match(html, /Use saved token/);
  assert.match(html, /\.preformatted \{/);
  assert.match(html, /function escapeClientHtml\(value\)/);
  assert.match(html, /function enterChatWithToken\(token\)/);
  assert.match(html, /function validateTokenOrWarn\(accessToken\)/);
  assert.match(html, /function renderIdentityOutput\(payload\)/);
  assert.match(html, /function bindIdentityOutputToggles\(\)/);
  assert.match(html, /data-detail-toggle='identity-dialog'/);
  assert.match(html, /identityDetailDialog\.showModal\(\)/);
  assert.match(html, /id="close-identity-detail"/);
  assert.match(html, /\/api\/session\/validate/);
  assert.match(html, /escapeClientHtml\(formatJson\(identity\.user\)\)/);
  assert.match(html, /escapeClientHtml\(formatJson\(identity\.token\)\)/);
  assert.match(html, /<strong>Token metadata<\/strong>/);
});

test("renderChatPage includes dedicated chat workflow sections", () => {
  const html = renderChatPage();

  assert.match(html, /Create Channel/);
  assert.match(html, /Live Event Stream/);
  assert.match(html, /id="stream-toggle"/);
  assert.match(html, /class="sidebar-footer"/);
  assert.match(html, /function startEventStream\(\)/);
  assert.match(html, /function stopEventStream\(statusMessage = "Event stream off\."/);
  assert.match(html, /Authenticated sender/);
  assert.match(html, /id="thread-sidebar" hidden/);
  assert.match(html, /id="close-thread"/);
  assert.match(html, /id="thread-panel"/);
  assert.match(html, /class="chat-layout chat-shell" id="chat-layout"/);
  assert.match(html, /class="scroll-region message-stream" id="message-list"/);
  assert.match(html, /class="feed scroll-region" id="event-feed"/);
  assert.match(html, /class="composer-shell"/);
  assert.match(html, /class="workspace-name">Open Messenger</);
  assert.doesNotMatch(html, /id="start-stream"/);
  assert.doesNotMatch(html, /id="stop-stream"/);
  assert.doesNotMatch(html, /Sender user ID/);
  assert.doesNotMatch(html, /Idempotency key/);
  assert.doesNotMatch(html, /<h1/);
  assert.doesNotMatch(html, /id="save-session"/);
  assert.doesNotMatch(html, /id="clear-session"/);
  assert.doesNotMatch(html, /id="access-token-input"/);
  assert.match(html, /function escapeClientHtml\(value\)/);
  assert.match(html, /function formatSenderLabel\(message\)/);
  assert.match(html, /function formatIdentityLabel\(identity\)/);
  assert.match(html, /function decodeCurrentUserId\(\)/);
  assert.match(html, /function toggleThreadSidebar\(isOpen\)/);
  assert.match(html, /async function loadChannels\(preferredChannelId = ""\)/);
  assert.match(html, /fetch\("\/api\/channels\/list"/);
  assert.match(html, /function validateChatAccessOrRedirect\(\)/);
  assert.match(html, /unvalid token/);
  assert.match(html, /Open chat from the main page after entering a token\./);
  assert.match(html, /sender_display_name/);
  assert.match(html, /items\.filter\(\(item\) => !item\.thread_id\)/);
  assert.match(html, /message-row/);
  assert.match(html, /thread-trigger/);
  assert.doesNotMatch(html, /\.message-card\.own \.message-author \{\s*flex-direction: row-reverse;/);
  assert.doesNotMatch(html, /Rooms stay in local storage for quick re-entry\./);
  assert.match(html, /Open the room to read messages and start threads\./);
  assert.doesNotMatch(html, /channel message/);
  assert.match(html, /escapeClientHtml\(event\.data\)/);
});
