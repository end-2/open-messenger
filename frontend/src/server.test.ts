import assert from "node:assert/strict";
import test from "node:test";

import { createFrontendServer } from "./server.ts";

test("frontend server exposes health endpoint", async () => {
  const server = createFrontendServer(
    {
      getInfo: async () => ({
        service: "open-messenger",
        version: "0.1.0",
        environment: "test",
        content_backend: "memory",
        metadata_backend: "memory",
        file_storage_backend: "local",
        content_store_impl: "MemoryContentStore",
        metadata_store_impl: "MemoryMetadataStore",
        file_store_impl: "LocalFileStore"
      })
    },
    {
      home: "<html><body>home</body></html>",
      chat: "<html><body>chat</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");
    const response = await fetch(`http://127.0.0.1:${address.port}/healthz`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});

test("frontend server serves home and chat pages", async () => {
  const server = createFrontendServer(
    {
      getInfo: async () => {
        throw new Error("not used");
      }
    },
    {
      home: "<html><body>home-page</body></html>",
      chat: "<html><body>chat-page</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");

    const homeResponse = await fetch(`http://127.0.0.1:${address.port}/`);
    assert.equal(homeResponse.status, 200);
    assert.match(await homeResponse.text(), /home-page/);

    const chatResponse = await fetch(`http://127.0.0.1:${address.port}/chat`);
    assert.equal(chatResponse.status, 200);
    assert.match(await chatResponse.text(), /chat-page/);
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});

test("frontend server proxies thread routes", async () => {
  const server = createFrontendServer(
    {
      createThread: async (accessToken: string, channelId: string, rootMessageId: string) => {
        assert.equal(accessToken, "token");
        assert.equal(channelId, "ch_1");
        assert.equal(rootMessageId, "msg_root");
        return {
          thread_id: "th_1",
          channel_id: channelId,
          root_message_id: rootMessageId,
          reply_count: 0,
          last_message_at: "2026-03-07T00:00:00Z",
          created_at: "2026-03-07T00:00:00Z"
        };
      },
      getThreadContext: async (accessToken: string, threadId: string) => {
        assert.equal(accessToken, "token");
        assert.equal(threadId, "th_1");
        return {
          thread: {
            thread_id: threadId,
            channel_id: "ch_1",
            root_message_id: "msg_root",
            reply_count: 1,
            last_message_at: "2026-03-07T00:00:01Z",
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
        };
      },
      createThreadMessage: async (accessToken: string, threadId: string, payload: { text: string }) => {
        assert.equal(accessToken, "token");
        assert.equal(threadId, "th_1");
        assert.equal(payload.text, "reply");
        return {
          message_id: "msg_reply",
          channel_id: "ch_1",
          thread_id: threadId,
          sender_user_id: "usr_1",
          sender_username: "alice",
          sender_display_name: "Alice",
          content_ref: "cnt_reply",
          text: payload.text,
          attachments: [],
          created_at: "2026-03-07T00:00:01Z",
          updated_at: "2026-03-07T00:00:01Z",
          deleted_at: null,
          compat_origin: "native",
          idempotency_key: null,
          metadata: {}
        };
      }
    },
    {
      home: "<html><body>home</body></html>",
      chat: "<html><body>chat</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");
    const baseUrl = `http://127.0.0.1:${address.port}`;

    const createThreadResponse = await fetch(`${baseUrl}/api/threads`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        accessToken: "token",
        channelId: "ch_1",
        rootMessageId: "msg_root"
      })
    });
    assert.equal(createThreadResponse.status, 201);
    assert.equal((await createThreadResponse.json()).thread_id, "th_1");

    const contextResponse = await fetch(`${baseUrl}/api/threads/context`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        accessToken: "token",
        threadId: "th_1"
      })
    });
    assert.equal(contextResponse.status, 200);
    assert.equal((await contextResponse.json()).thread.thread_id, "th_1");

    const replyResponse = await fetch(`${baseUrl}/api/threads/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        accessToken: "token",
        threadId: "th_1",
        text: "reply"
      })
    });
    assert.equal(replyResponse.status, 201);
    assert.equal((await replyResponse.json()).thread_id, "th_1");
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});

test("frontend server validates session tokens", async () => {
  const server = createFrontendServer(
    {
      validateAccessToken: async (accessToken: string) => {
        assert.equal(accessToken, "token");
      }
    },
    {
      home: "<html><body>home</body></html>",
      chat: "<html><body>chat</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");
    const response = await fetch(`http://127.0.0.1:${address.port}/api/session/validate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ accessToken: "token" })
    });

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { valid: true });
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});

test("frontend server proxies channel list route", async () => {
  const server = createFrontendServer(
    {
      listChannels: async (accessToken: string) => {
        assert.equal(accessToken, "token");
        return {
          items: [
            {
              channel_id: "ch_1",
              name: "general",
              created_at: "2026-03-07T00:00:00Z"
            }
          ]
        };
      }
    },
    {
      home: "<html><body>home</body></html>",
      chat: "<html><body>chat</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");
    const response = await fetch(`http://127.0.0.1:${address.port}/api/channels/list`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ accessToken: "token" })
    });

    assert.equal(response.status, 200);
    assert.equal((await response.json()).items[0].channel_id, "ch_1");
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});

test("frontend server proxies file upload and download routes", async () => {
  const server = createFrontendServer(
    {
      uploadFile: async (accessToken: string, file: Blob, filename: string) => {
        assert.equal(accessToken, "token");
        assert.equal(filename, "hello.txt");
        assert.equal(await file.text(), "hello world");
        return {
          file_id: "fil_1",
          uploader_user_id: "usr_1",
          filename,
          mime_type: "text/plain",
          size_bytes: 11,
          sha256: "abc",
          created_at: "2026-03-07T00:00:00Z"
        };
      },
      downloadFile: async (accessToken: string, fileId: string) => {
        assert.equal(accessToken, "token");
        assert.equal(fileId, "fil_1");
        return new Response("hello world", {
          status: 200,
          headers: {
            "content-type": "text/plain",
            "content-disposition": "attachment; filename=\"hello.txt\""
          }
        });
      }
    },
    {
      home: "<html><body>home</body></html>",
      chat: "<html><body>chat</body></html>"
    }
  );

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

  try {
    const address = server.address();
    assert(address && typeof address === "object");
    const baseUrl = `http://127.0.0.1:${address.port}`;

    const formData = new FormData();
    formData.set("file", new File(["hello world"], "hello.txt", { type: "text/plain" }));
    const uploadResponse = await fetch(`${baseUrl}/api/files`, {
      method: "POST",
      headers: { "x-access-token": "token" },
      body: formData
    });

    assert.equal(uploadResponse.status, 201);
    assert.equal((await uploadResponse.json()).file_id, "fil_1");

    const downloadResponse = await fetch(`${baseUrl}/api/files/fil_1`, {
      headers: { "x-access-token": "token" }
    });

    assert.equal(downloadResponse.status, 200);
    assert.equal(downloadResponse.headers.get("content-type"), "text/plain");
    assert.match(downloadResponse.headers.get("content-disposition") || "", /hello\.txt/);
    assert.equal(await downloadResponse.text(), "hello world");
  } finally {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
  }
});
