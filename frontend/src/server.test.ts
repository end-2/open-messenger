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
