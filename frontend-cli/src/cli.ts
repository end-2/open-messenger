import process from "node:process";
import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

import {
  BackendClient,
  BackendError,
  type FrontendChannel,
  type FrontendMessage,
  type FrontendThreadContext
} from "./backend.ts";

type CliState = {
  accessToken: string;
  userId: string | null;
  username: string | null;
  activeChannel: FrontendChannel | null;
};

export type CliCommandContext = {
  client: BackendClient;
  state: CliState;
  writeLine: (message?: string) => void;
};

export function splitCommand(inputLine: string): string[] {
  const parts = inputLine.match(/"[^"]*"|'[^']*'|\S+/g) ?? [];
  return parts.map((part) => {
    if (
      (part.startsWith("\"") && part.endsWith("\"")) ||
      (part.startsWith("'") && part.endsWith("'"))
    ) {
      return part.slice(1, -1);
    }
    return part;
  });
}

function formatMessage(message: FrontendMessage): string {
  const threadLabel = message.thread_id ? ` thread=${message.thread_id}` : "";
  return `${message.message_id} [${message.sender_user_id}]${threadLabel}: ${message.text}`;
}

function formatThreadContext(context: FrontendThreadContext): string[] {
  const lines = [
    `thread ${context.thread.thread_id} root=${context.thread.root_message_id} replies=${context.thread.reply_count}`,
    `root: ${formatMessage(context.root_message)}`
  ];

  if (context.replies.length === 0) {
    lines.push("replies: none");
    return lines;
  }

  lines.push("replies:");
  for (const reply of context.replies) {
    lines.push(`- ${formatMessage(reply)}`);
  }
  if (context.has_more_replies) {
    lines.push("more replies are available");
  }
  return lines;
}

function requireAccessToken(state: CliState): string {
  if (!state.accessToken) {
    throw new Error("No access token is configured. Use `token <value>` or `bootstrap <username>` first.");
  }
  return state.accessToken;
}

function requireActiveChannel(state: CliState): FrontendChannel {
  if (state.activeChannel === null) {
    throw new Error("No active channel. Use `create-channel <name>` or `use-channel <channel_id>` first.");
  }
  return state.activeChannel;
}

export async function executeCommand(context: CliCommandContext, inputLine: string): Promise<boolean> {
  const tokens = splitCommand(inputLine.trim());
  if (tokens.length === 0) {
    return true;
  }

  const [command, ...args] = tokens;
  const { client, state, writeLine } = context;

  switch (command) {
    case "help":
      writeLine("Commands:");
      writeLine("  help");
      writeLine("  info");
      writeLine("  bootstrap <username> [display-name]");
      writeLine("  token <access-token>");
      writeLine("  whoami");
      writeLine("  create-channel <name>");
      writeLine("  use-channel <channel-id>");
      writeLine("  list [cursor]");
      writeLine("  send <text>");
      writeLine("  thread <root-message-id>");
      writeLine("  reply <thread-id> <text>");
      writeLine("  context <thread-id>");
      writeLine("  exit");
      return true;

    case "info": {
      const info = await client.getInfo();
      writeLine(JSON.stringify(info, null, 2));
      return true;
    }

    case "bootstrap": {
      const username = args[0];
      if (!username) {
        throw new Error("Usage: bootstrap <username> [display-name]");
      }
      const displayName = args[1];
      const result = await client.bootstrapUser({
        username,
        displayName,
        tokenType: "user_token",
        scopes: ["channels:read", "channels:write", "messages:read", "messages:write"]
      });
      state.accessToken = result.token.token;
      state.userId = result.user.user_id;
      state.username = result.user.username;
      writeLine(`bootstrapped user=${result.user.username} token=${result.token.token}`);
      return true;
    }

    case "token": {
      const accessToken = args[0];
      if (!accessToken) {
        throw new Error("Usage: token <access-token>");
      }
      state.accessToken = accessToken;
      writeLine("access token updated");
      return true;
    }

    case "whoami": {
      writeLine(
        JSON.stringify(
          {
            username: state.username,
            user_id: state.userId,
            has_access_token: state.accessToken.length > 0,
            active_channel: state.activeChannel
          },
          null,
          2
        )
      );
      return true;
    }

    case "create-channel": {
      const name = args.join(" ").trim();
      if (!name) {
        throw new Error("Usage: create-channel <name>");
      }
      const channel = await client.createChannel(requireAccessToken(state), name);
      state.activeChannel = channel;
      writeLine(`active channel=${channel.channel_id} name=${channel.name}`);
      return true;
    }

    case "use-channel": {
      const channelId = args[0];
      if (!channelId) {
        throw new Error("Usage: use-channel <channel-id>");
      }
      const channel = await client.getChannel(requireAccessToken(state), channelId);
      state.activeChannel = channel;
      writeLine(`active channel=${channel.channel_id} name=${channel.name}`);
      return true;
    }

    case "list": {
      const channel = requireActiveChannel(state);
      const cursor = args[0];
      const messages = await client.listMessages(requireAccessToken(state), channel.channel_id, cursor);
      if (messages.items.length === 0) {
        writeLine("no messages");
      } else {
        for (const message of messages.items) {
          writeLine(formatMessage(message));
        }
      }
      if (messages.next_cursor) {
        writeLine(`next_cursor=${messages.next_cursor}`);
      }
      return true;
    }

    case "send": {
      const text = args.join(" ").trim();
      if (!text) {
        throw new Error("Usage: send <text>");
      }
      const channel = requireActiveChannel(state);
      const message = await client.createMessage(requireAccessToken(state), channel.channel_id, { text });
      writeLine(`sent ${formatMessage(message)}`);
      return true;
    }

    case "thread": {
      const rootMessageId = args[0];
      if (!rootMessageId) {
        throw new Error("Usage: thread <root-message-id>");
      }
      const channel = requireActiveChannel(state);
      const thread = await client.createThread(requireAccessToken(state), channel.channel_id, rootMessageId);
      writeLine(`thread ${thread.thread_id} created for root=${thread.root_message_id}`);
      return true;
    }

    case "reply": {
      const threadId = args[0];
      const text = args.slice(1).join(" ").trim();
      if (!threadId || !text) {
        throw new Error("Usage: reply <thread-id> <text>");
      }
      const message = await client.createThreadMessage(requireAccessToken(state), threadId, { text });
      writeLine(`replied ${formatMessage(message)}`);
      return true;
    }

    case "context": {
      const threadId = args[0];
      if (!threadId) {
        throw new Error("Usage: context <thread-id>");
      }
      const contextResult = await client.getThreadContext(requireAccessToken(state), threadId);
      for (const line of formatThreadContext(contextResult)) {
        writeLine(line);
      }
      return true;
    }

    case "exit":
    case "quit":
      return false;

    default:
      throw new Error(`Unknown command: ${command}. Use \`help\` to see available commands.`);
  }
}

export async function runCli(args: string[] = process.argv.slice(2)): Promise<void> {
  const baseUrl = process.env.OPEN_MESSENGER_API_URL ?? "http://127.0.0.1:8000";
  const adminToken = process.env.OPEN_MESSENGER_ADMIN_API_TOKEN ?? "dev-admin-token";
  const initialToken = args[0] ?? process.env.OPEN_MESSENGER_ACCESS_TOKEN ?? "";

  const client = new BackendClient(baseUrl, adminToken);
  const state: CliState = {
    accessToken: initialToken,
    userId: null,
    username: null,
    activeChannel: null
  };

  const rl = readline.createInterface({ input, output });
  const writeLine = (message = ""): void => {
    output.write(`${message}\n`);
  };

  writeLine(`Open Messenger CLI connected to ${baseUrl}`);
  writeLine("Use `help` to see available commands.");

  try {
    let keepRunning = true;
    while (keepRunning) {
      const prompt = state.activeChannel ? `om:${state.activeChannel.name}> ` : "om> ";
      const line = await rl.question(prompt);
      try {
        keepRunning = await executeCommand({ client, state, writeLine }, line);
      } catch (error) {
        if (error instanceof BackendError) {
          writeLine(`backend error ${error.status}: ${JSON.stringify(error.details)}`);
        } else if (error instanceof Error) {
          writeLine(`error: ${error.message}`);
        } else {
          writeLine("error: unknown failure");
        }
      }
    }
  } finally {
    rl.close();
  }
}

if (import.meta.url === new URL(process.argv[1] ?? "", "file:").href) {
  void runCli();
}
