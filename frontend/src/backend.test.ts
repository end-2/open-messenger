import assert from "node:assert/strict";
import test from "node:test";

import { BackendClient, BackendError } from "./backend.ts";

test("BackendClient includes admin token when bootstrapping", async () => {
  const calls: Array<{ url: string; headers: Headers; body: string | undefined }> = [];
  const fetchStub: typeof fetch = async (input, init) => {
    calls.push({
      url: String(input),
      headers: new Headers(init?.headers),
      body: init?.body ? String(init.body) : undefined
    });

    if (String(input).endsWith("/admin/v1/users")) {
      return new Response(
        JSON.stringify({
          user_id: "usr_1",
          username: "alice",
          display_name: "Alice",
          created_at: "2026-03-07T00:00:00Z"
        }),
        { status: 201 }
      );
    }

    return new Response(
      JSON.stringify({
        token_id: "tok_1",
        user_id: "usr_1",
        token_type: "user_token",
        scopes: ["messages:read"],
        created_at: "2026-03-07T00:00:00Z",
        revoked_at: null,
        token: "secret"
      }),
      { status: 201 }
    );
  };

  const client = new BackendClient("http://api.example", "dev-admin-token", fetchStub);
  const result = await client.bootstrapUser({
    username: "alice",
    displayName: "Alice",
    scopes: ["messages:read"],
    tokenType: "user_token"
  });

  assert.equal(result.user.user_id, "usr_1");
  assert.equal(result.token.token, "secret");
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/admin\/v1\/users$/);
  assert.equal(calls[0].headers.get("x-admin-token"), "dev-admin-token");
  assert.match(calls[1].body ?? "", /messages:read/);
});

test("BackendClient surfaces structured backend failures", async () => {
  const client = new BackendClient(
    "http://api.example",
    "dev-admin-token",
    async () =>
      new Response(JSON.stringify({ code: "channel_not_found" }), {
        status: 404,
        headers: { "content-type": "application/json" }
      })
  );

  await assert.rejects(
    client.createChannel("token", "general"),
    (error: unknown) =>
      error instanceof BackendError &&
      error.status === 404 &&
      (error.details as { code?: string }).code === "channel_not_found"
  );
});
