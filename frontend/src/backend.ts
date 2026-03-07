export type FrontendInfo = {
  service: string;
  version: string;
  environment: string;
  content_backend: string;
  metadata_backend: string;
  file_storage_backend: string;
  content_store_impl: string;
  metadata_store_impl: string;
  file_store_impl: string;
};

export type FrontendUser = {
  user_id: string;
  username: string;
  display_name: string | null;
  created_at: string;
};

export type FrontendToken = {
  token_id: string;
  user_id: string;
  token_type: string;
  scopes: string[];
  created_at: string;
  revoked_at: string | null;
  token: string;
};

export type FrontendChannel = {
  channel_id: string;
  name: string;
  created_at: string;
};

export type FrontendMessage = {
  message_id: string;
  channel_id: string;
  thread_id: string | null;
  sender_user_id: string;
  content_ref: string;
  text: string;
  attachments: string[];
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  compat_origin: string;
  idempotency_key: string | null;
  metadata: Record<string, unknown>;
};

type FetchLike = typeof fetch;

export class BackendError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "BackendError";
    this.status = status;
    this.details = details;
  }
}

export class BackendClient {
  readonly baseUrl: string;
  readonly adminToken: string;
  readonly fetchImpl: FetchLike;

  constructor(baseUrl: string, adminToken: string, fetchImpl: FetchLike = fetch) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.adminToken = adminToken;
    this.fetchImpl = fetchImpl;
  }

  async getInfo(): Promise<FrontendInfo> {
    return this.request<FrontendInfo>("/v1/info", {
      method: "GET"
    });
  }

  async bootstrapUser(input: {
    username: string;
    displayName?: string;
    scopes: string[];
    tokenType: string;
  }): Promise<{ user: FrontendUser; token: FrontendToken }> {
    const user = await this.request<FrontendUser>("/admin/v1/users", {
      method: "POST",
      admin: true,
      body: {
        username: input.username,
        display_name: input.displayName || null
      }
    });

    const token = await this.request<FrontendToken>("/admin/v1/tokens", {
      method: "POST",
      admin: true,
      body: {
        user_id: user.user_id,
        token_type: input.tokenType,
        scopes: input.scopes
      }
    });

    return { user, token };
  }

  async createChannel(accessToken: string, name: string): Promise<FrontendChannel> {
    return this.request<FrontendChannel>("/v1/channels", {
      method: "POST",
      accessToken,
      body: { name }
    });
  }

  async getChannel(accessToken: string, channelId: string): Promise<FrontendChannel> {
    return this.request<FrontendChannel>(`/v1/channels/${channelId}`, {
      method: "GET",
      accessToken
    });
  }

  async listMessages(accessToken: string, channelId: string, cursor?: string): Promise<{
    items: FrontendMessage[];
    next_cursor: string | null;
  }> {
    const search = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    return this.request(`/v1/channels/${channelId}/messages${search}`, {
      method: "GET",
      accessToken
    });
  }

  async createMessage(accessToken: string, channelId: string, payload: {
    text: string;
    sender_user_id?: string;
    thread_id?: string;
    idempotency_key?: string;
  }): Promise<FrontendMessage> {
    return this.request<FrontendMessage>(`/v1/channels/${channelId}/messages`, {
      method: "POST",
      accessToken,
      body: payload
    });
  }

  async request<T>(path: string, options: {
    method: string;
    admin?: boolean;
    accessToken?: string;
    body?: unknown;
  }): Promise<T> {
    const headers = new Headers();
    if (options.body !== undefined) {
      headers.set("content-type", "application/json");
    }
    if (options.admin) {
      headers.set("x-admin-token", this.adminToken);
    }
    if (options.accessToken) {
      headers.set("authorization", `Bearer ${options.accessToken}`);
    }

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: options.method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body)
    });

    if (!response.ok) {
      let details: unknown = null;
      try {
        details = await response.json();
      } catch {
        details = await response.text();
      }
      throw new BackendError(`Backend request failed with status ${response.status}`, response.status, details);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }
}
