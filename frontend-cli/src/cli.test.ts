import assert from "node:assert/strict";
import test from "node:test";

import { executeCommand, splitCommand, type CliCommandContext } from "./cli.ts";
import type {
  BackendClient,
  FrontendChannel,
  FrontendMessage,
  FrontendThread,
  FrontendThreadContext
} from "./backend.ts";

function createContext(client: Partial<BackendClient>): { context: CliCommandContext; lines: string[] } {
  const lines: string[] = [];
  return {
    context: {
      client: client as BackendClient,
      state: {
        accessToken: "",
        userId: null,
        username: null,
        activeChannel: null
      },
      writeLine: (line = "") => {
        lines.push(line);
      }
    },
    lines
  };
}

test("splitCommand preserves quoted text", () => {
  assert.deepEqual(splitCommand(`send "hello open messenger"`), ["send", "hello open messenger"]);
  assert.deepEqual(splitCommand(`bootstrap alice "Alice Doe"`), ["bootstrap", "alice", "Alice Doe"]);
});

test("bootstrap stores issued token in CLI state", async () => {
  const { context, lines } = createContext({
    bootstrapUser: async () => ({
      user: {
        user_id: "usr_1",
        username: "alice",
        display_name: "Alice",
        created_at: "2026-03-07T00:00:00Z"
      },
      token: {
        token_id: "tok_1",
        user_id: "usr_1",
        token_type: "user_token",
        scopes: ["channels:read"],
        created_at: "2026-03-07T00:00:00Z",
        revoked_at: null,
        token: "secret"
      }
    })
  });

  const keepRunning = await executeCommand(context, `bootstrap alice "Alice Doe"`);

  assert.equal(keepRunning, true);
  assert.equal(context.state.accessToken, "secret");
  assert.equal(context.state.username, "alice");
  assert.match(lines[0], /bootstrapped user=alice token=secret/);
});

test("create-channel and send use the active channel", async () => {
  const createdMessages: Array<{ token: string; channelId: string; text: string }> = [];
  const { context, lines } = createContext({
    createChannel: async (_token: string, name: string): Promise<FrontendChannel> => ({
      channel_id: "ch_1",
      name,
      created_at: "2026-03-07T00:00:00Z"
    }),
    createMessage: async (token: string, channelId: string, payload: { text: string }): Promise<FrontendMessage> => {
      createdMessages.push({ token, channelId, text: payload.text });
      return {
        message_id: "msg_1",
        channel_id: channelId,
        thread_id: null,
        sender_user_id: "usr_1",
        content_ref: "cnt_1",
        text: payload.text,
        attachments: [],
        created_at: "2026-03-07T00:00:00Z",
        updated_at: "2026-03-07T00:00:00Z",
        deleted_at: null,
        compat_origin: "native",
        idempotency_key: null,
        metadata: {}
      };
    }
  });

  context.state.accessToken = "secret";
  await executeCommand(context, "create-channel general");
  await executeCommand(context, `send "hello world"`);

  assert.equal(context.state.activeChannel?.channel_id, "ch_1");
  assert.deepEqual(createdMessages, [{ token: "secret", channelId: "ch_1", text: "hello world" }]);
  assert.match(lines[0], /active channel=ch_1/);
  assert.match(lines[1], /sent msg_1/);
});

test("context prints root message and replies", async () => {
  const { context, lines } = createContext({
    getThreadContext: async (): Promise<FrontendThreadContext> => ({
      thread: {
        thread_id: "th_1",
        channel_id: "ch_1",
        root_message_id: "msg_root",
        reply_count: 1,
        last_message_at: "2026-03-07T00:00:01Z",
        created_at: "2026-03-07T00:00:00Z"
      } as FrontendThread,
      root_message: {
        message_id: "msg_root",
        channel_id: "ch_1",
        thread_id: null,
        sender_user_id: "usr_1",
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
      replies: [
        {
          message_id: "msg_reply",
          channel_id: "ch_1",
          thread_id: "th_1",
          sender_user_id: "usr_2",
          content_ref: "cnt_reply",
          text: "reply text",
          attachments: [],
          created_at: "2026-03-07T00:00:01Z",
          updated_at: "2026-03-07T00:00:01Z",
          deleted_at: null,
          compat_origin: "native",
          idempotency_key: null,
          metadata: {}
        }
      ],
      has_more_replies: false
    })
  });

  context.state.accessToken = "secret";
  await executeCommand(context, "context th_1");

  assert.equal(lines[0], "thread th_1 root=msg_root replies=1");
  assert.match(lines[1], /root: msg_root/);
  assert.equal(lines[2], "replies:");
  assert.match(lines[3], /msg_reply/);
});

test("exit returns false", async () => {
  const { context } = createContext({});
  assert.equal(await executeCommand(context, "exit"), false);
});
