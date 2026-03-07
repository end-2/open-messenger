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

test("BackendClient validates access tokens against an authenticated endpoint", async () => {
  const calls: Array<{ url: string; headers: Headers }> = [];
  const client = new BackendClient(
    "http://api.example",
    "dev-admin-token",
    async (input, init) => {
      calls.push({
        url: String(input),
        headers: new Headers(init?.headers)
      });
      return new Response(": connected\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" }
      });
    }
  );

  await client.validateAccessToken("token");

  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/v1\/events\/stream$/);
  assert.equal(calls[0].headers.get("authorization"), "Bearer token");
});

test("BackendClient supports thread workflows", async () => {
  const calls: Array<{ url: string; body: string | undefined }> = [];
  const fetchStub: typeof fetch = async (input, init) => {
    calls.push({
      url: String(input),
      body: init?.body ? String(init.body) : undefined
    });

    if (String(input).endsWith("/v1/channels/ch_1/threads")) {
      return new Response(
        JSON.stringify({
          thread_id: "th_1",
          channel_id: "ch_1",
          root_message_id: "msg_root",
          reply_count: 0,
          last_message_at: "2026-03-07T00:00:00Z",
          created_at: "2026-03-07T00:00:00Z"
        }),
        { status: 201 }
      );
    }

    if (String(input).endsWith("/v1/threads/th_1/context")) {
      return new Response(
        JSON.stringify({
          thread: {
            thread_id: "th_1",
            channel_id: "ch_1",
            root_message_id: "msg_root",
            reply_count: 1,
            last_message_at: "2026-03-07T00:00:05Z",
            created_at: "2026-03-07T00:00:00Z"
          },
          root_message: {
            message_id: "msg_root",
            channel_id: "ch_1",
            thread_id: null,
            sender_user_id: "usr_1",
            sender_username: "alice",
            sender_display_name: "Alice",
            content_ref: "cnt_root",
            text: "root",
            attachments: [],
            created_at: "2026-03-07T00:00:00Z",
            updated_at: "2026-03-07T00:00:00Z",
            deleted_at: null,
            compat_origin: "native",
            idempotency_key: null,
            metadata: {}
          },
          replies: [],
          has_more_replies: false
        }),
        { status: 200 }
      );
    }

    return new Response(
      JSON.stringify({
        message_id: "msg_reply",
        channel_id: "ch_1",
        thread_id: "th_1",
        sender_user_id: "usr_1",
        sender_username: "alice",
        sender_display_name: "Alice",
        content_ref: "cnt_reply",
        text: "reply",
        attachments: [],
        created_at: "2026-03-07T00:00:05Z",
        updated_at: "2026-03-07T00:00:05Z",
        deleted_at: null,
        compat_origin: "native",
        idempotency_key: null,
        metadata: {}
      }),
      { status: 201 }
    );
  };

  const client = new BackendClient("http://api.example", "dev-admin-token", fetchStub);
  const thread = await client.createThread("token", "ch_1", "msg_root");
  const context = await client.getThreadContext("token", thread.thread_id);
  const reply = await client.createThreadMessage("token", thread.thread_id, { text: "reply" });

  assert.equal(thread.thread_id, "th_1");
  assert.equal(context.thread.root_message_id, "msg_root");
  assert.equal(context.root_message.sender_display_name, "Alice");
  assert.equal(reply.thread_id, "th_1");
  assert.match(calls[0].url, /\/v1\/channels\/ch_1\/threads$/);
  assert.match(calls[1].url, /\/v1\/threads\/th_1\/context$/);
  assert.match(calls[2].url, /\/v1\/threads\/th_1\/messages$/);
  assert.match(calls[0].body ?? "", /msg_root/);
  assert.match(calls[2].body ?? "", /reply/);
});

test("BackendClient lists channels", async () => {
  const calls: Array<{ url: string; headers: Headers }> = [];
  const client = new BackendClient(
    "http://api.example",
    "dev-admin-token",
    async (input, init) => {
      calls.push({
        url: String(input),
        headers: new Headers(init?.headers)
      });
      return new Response(
        JSON.stringify({
          items: [
            {
              channel_id: "ch_1",
              name: "general",
              created_at: "2026-03-07T00:00:00Z"
            }
          ]
        }),
        { status: 200 }
      );
    }
  );

  const result = await client.listChannels("token");

  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].name, "general");
  assert.match(calls[0].url, /\/v1\/channels$/);
  assert.equal(calls[0].headers.get("authorization"), "Bearer token");
});

test("BackendClient uploads and downloads files with bearer auth", async () => {
  const calls: Array<{ url: string; method: string; headers: Headers; body?: BodyInit | null }> = [];
  const client = new BackendClient(
    "http://api.example",
    "dev-admin-token",
    async (input, init) => {
      calls.push({
        url: String(input),
        method: String(init?.method || "GET"),
        headers: new Headers(init?.headers),
        body: init?.body
      });

      if (String(input).endsWith("/v1/files")) {
        return new Response(
          JSON.stringify({
            file_id: "fil_1",
            uploader_user_id: "usr_1",
            filename: "photo.png",
            mime_type: "image/png",
            size_bytes: 4,
            sha256: "abc",
            created_at: "2026-03-07T00:00:00Z"
          }),
          { status: 201 }
        );
      }

      return new Response("file-bytes", {
        status: 200,
        headers: {
          "content-type": "image/png",
          "content-disposition": "attachment; filename=\"photo.png\""
        }
      });
    }
  );

  const uploaded = await client.uploadFile("token", new Blob(["data"], { type: "image/png" }), "photo.png");
  const downloaded = await client.downloadFile("token", "fil_1");

  assert.equal(uploaded.file_id, "fil_1");
  assert.equal(downloaded.status, 200);
  assert.equal(await downloaded.text(), "file-bytes");
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/v1\/files$/);
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].headers.get("authorization"), "Bearer token");
  assert(calls[0].body instanceof FormData);
  assert.match(calls[1].url, /\/v1\/files\/fil_1$/);
  assert.equal(calls[1].method, "GET");
  assert.equal(calls[1].headers.get("authorization"), "Bearer token");
});
