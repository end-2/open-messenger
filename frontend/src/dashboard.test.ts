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
});

test("renderChatPage includes dedicated chat workflow sections", () => {
  const html = renderChatPage();

  assert.match(html, /Channels and Messages/);
  assert.match(html, /Create Channel/);
  assert.match(html, /Live Event Stream/);
  assert.match(html, /Active Room/);
});
