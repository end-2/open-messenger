import assert from "node:assert/strict";
import test from "node:test";

import { renderDashboard } from "./dashboard.ts";

test("renderDashboard includes documented workflow sections", () => {
  const html = renderDashboard({
    port: 3001,
    apiBaseUrl: "http://127.0.0.1:8000",
    adminToken: "dev-admin-token"
  });

  assert.match(html, /Open Messenger Frontend/);
  assert.match(html, /Admin Bootstrap/);
  assert.match(html, /Channels and Messages/);
  assert.match(html, /Live Event Stream/);
  assert.match(html, /http:\/\/127\.0\.0\.1:8000/);
});
