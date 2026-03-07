package cli_test

import (
	"testing"

	"open-messenger/frontend-cli-golang/backend"
	"open-messenger/frontend-cli-golang/cli"
)

// mockClient selectively overrides backend methods for testing.
type mockClient struct {
	getInfo             func() (*backend.Info, error)
	bootstrapUser       func(input backend.BootstrapUserInput) (*backend.BootstrapResult, error)
	createChannel       func(accessToken, name string) (*backend.Channel, error)
	getChannel          func(accessToken, channelID string) (*backend.Channel, error)
	listMessages        func(accessToken, channelID, cursor string) (*backend.MessageList, error)
	createMessage       func(accessToken, channelID string, payload map[string]interface{}) (*backend.Message, error)
	createThread        func(accessToken, channelID, rootMessageID string) (*backend.Thread, error)
	getThreadContext    func(accessToken, threadID string) (*backend.ThreadContext, error)
	createThreadMessage func(accessToken, threadID string, payload map[string]interface{}) (*backend.Message, error)
}

func (m *mockClient) GetInfo() (*backend.Info, error) {
	return m.getInfo()
}
func (m *mockClient) BootstrapUser(input backend.BootstrapUserInput) (*backend.BootstrapResult, error) {
	return m.bootstrapUser(input)
}
func (m *mockClient) CreateChannel(accessToken, name string) (*backend.Channel, error) {
	return m.createChannel(accessToken, name)
}
func (m *mockClient) GetChannel(accessToken, channelID string) (*backend.Channel, error) {
	return m.getChannel(accessToken, channelID)
}
func (m *mockClient) ListMessages(accessToken, channelID, cursor string) (*backend.MessageList, error) {
	return m.listMessages(accessToken, channelID, cursor)
}
func (m *mockClient) CreateMessage(accessToken, channelID string, payload map[string]interface{}) (*backend.Message, error) {
	return m.createMessage(accessToken, channelID, payload)
}
func (m *mockClient) CreateThread(accessToken, channelID, rootMessageID string) (*backend.Thread, error) {
	return m.createThread(accessToken, channelID, rootMessageID)
}
func (m *mockClient) GetThreadContext(accessToken, threadID string) (*backend.ThreadContext, error) {
	return m.getThreadContext(accessToken, threadID)
}
func (m *mockClient) CreateThreadMessage(accessToken, threadID string, payload map[string]interface{}) (*backend.Message, error) {
	return m.createThreadMessage(accessToken, threadID, payload)
}

func newContext(mock *mockClient) (cli.CommandContext, *[]string) {
	lines := &[]string{}
	return cli.CommandContext{
		Client: mock,
		State:  &cli.State{},
		WriteLine: func(line string) {
			*lines = append(*lines, line)
		},
	}, lines
}

func TestSplitCommandPreservesQuotedText(t *testing.T) {
	got := cli.SplitCommand(`send "hello open messenger"`)
	want := []string{"send", "hello open messenger"}
	if len(got) != len(want) {
		t.Fatalf("SplitCommand returned %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("token[%d] = %q, want %q", i, got[i], want[i])
		}
	}

	got2 := cli.SplitCommand(`bootstrap alice "Alice Doe"`)
	want2 := []string{"bootstrap", "alice", "Alice Doe"}
	if len(got2) != len(want2) {
		t.Fatalf("SplitCommand returned %v, want %v", got2, want2)
	}
	for i := range want2 {
		if got2[i] != want2[i] {
			t.Errorf("token[%d] = %q, want %q", i, got2[i], want2[i])
		}
	}
}

func TestBootstrapStoresTokenInState(t *testing.T) {
	mock := &mockClient{
		bootstrapUser: func(input backend.BootstrapUserInput) (*backend.BootstrapResult, error) {
			return &backend.BootstrapResult{
				User: backend.User{
					UserID:    "usr_1",
					Username:  "alice",
					CreatedAt: "2026-03-07T00:00:00Z",
				},
				Token: backend.Token{
					TokenID:   "tok_1",
					UserID:    "usr_1",
					TokenType: "user_token",
					Scopes:    []string{"channels:read"},
					CreatedAt: "2026-03-07T00:00:00Z",
					Token:     "secret",
				},
			}, nil
		},
	}

	ctx, lines := newContext(mock)

	keepRunning, err := cli.ExecuteCommand(ctx, `bootstrap alice "Alice Doe"`)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !keepRunning {
		t.Error("expected keepRunning=true")
	}
	if ctx.State.AccessToken != "secret" {
		t.Errorf("AccessToken = %q, want %q", ctx.State.AccessToken, "secret")
	}
	if ctx.State.Username != "alice" {
		t.Errorf("Username = %q, want %q", ctx.State.Username, "alice")
	}
	if len(*lines) < 2 {
		t.Fatalf("expected at least 2 output lines, got %d", len(*lines))
	}
	if !containsAll((*lines)[0], "bootstrapped", "user=alice", "token=secret") {
		t.Errorf("unexpected output line[0]: %q", (*lines)[0])
	}
	if !containsAll((*lines)[1], "logged in", "alice") {
		t.Errorf("unexpected output line[1]: %q", (*lines)[1])
	}
}

func TestCreateChannelAndSendUseActiveChannel(t *testing.T) {
	type created struct {
		token     string
		channelID string
		text      string
	}
	var createdMessages []created

	mock := &mockClient{
		createChannel: func(token, name string) (*backend.Channel, error) {
			return &backend.Channel{
				ChannelID: "ch_1",
				Name:      name,
				CreatedAt: "2026-03-07T00:00:00Z",
			}, nil
		},
		createMessage: func(token, channelID string, payload map[string]interface{}) (*backend.Message, error) {
			text, _ := payload["text"].(string)
			createdMessages = append(createdMessages, created{token, channelID, text})
			return &backend.Message{
				MessageID:    "msg_1",
				ChannelID:    channelID,
				SenderUserID: "usr_1",
				ContentRef:   "cnt_1",
				Text:         text,
				Attachments:  []string{},
				CreatedAt:    "2026-03-07T00:00:00Z",
				UpdatedAt:    "2026-03-07T00:00:00Z",
				CompatOrigin: "native",
				Metadata:     map[string]interface{}{},
			}, nil
		},
	}

	ctx, lines := newContext(mock)
	ctx.State.AccessToken = "secret"

	if _, err := cli.ExecuteCommand(ctx, "create-channel general"); err != nil {
		t.Fatalf("create-channel error: %v", err)
	}
	if _, err := cli.ExecuteCommand(ctx, `send "hello world"`); err != nil {
		t.Fatalf("send error: %v", err)
	}

	if ctx.State.ActiveChannel == nil || ctx.State.ActiveChannel.ChannelID != "ch_1" {
		t.Errorf("ActiveChannel = %v, want ch_1", ctx.State.ActiveChannel)
	}
	if len(createdMessages) != 1 {
		t.Fatalf("expected 1 created message, got %d", len(createdMessages))
	}
	m := createdMessages[0]
	if m.token != "secret" || m.channelID != "ch_1" || m.text != "hello world" {
		t.Errorf("unexpected message: %+v", m)
	}
	if len(*lines) < 2 {
		t.Fatalf("expected at least 2 output lines, got %d", len(*lines))
	}
	if !containsAll((*lines)[0], "active channel=ch_1") {
		t.Errorf("unexpected first line: %q", (*lines)[0])
	}
	if !containsAll((*lines)[1], "sent", "msg_1") {
		t.Errorf("unexpected second line: %q", (*lines)[1])
	}
}

func TestContextPrintsRootAndReplies(t *testing.T) {
	threadID := "th_1"
	mock := &mockClient{
		getThreadContext: func(token, tid string) (*backend.ThreadContext, error) {
			return &backend.ThreadContext{
				Thread: backend.Thread{
					ThreadID:      "th_1",
					ChannelID:     "ch_1",
					RootMessageID: "msg_root",
					ReplyCount:    1,
					LastMessageAt: "2026-03-07T00:00:01Z",
					CreatedAt:     "2026-03-07T00:00:00Z",
				},
				RootMessage: backend.Message{
					MessageID:    "msg_root",
					ChannelID:    "ch_1",
					SenderUserID: "usr_1",
					ContentRef:   "cnt_root",
					Text:         "root",
					Attachments:  []string{},
					CreatedAt:    "2026-03-07T00:00:00Z",
					UpdatedAt:    "2026-03-07T00:00:00Z",
					CompatOrigin: "native",
					Metadata:     map[string]interface{}{},
				},
				Replies: []backend.Message{
					{
						MessageID:    "msg_reply",
						ChannelID:    "ch_1",
						ThreadID:     &threadID,
						SenderUserID: "usr_2",
						ContentRef:   "cnt_reply",
						Text:         "reply text",
						Attachments:  []string{},
						CreatedAt:    "2026-03-07T00:00:01Z",
						UpdatedAt:    "2026-03-07T00:00:01Z",
						CompatOrigin: "native",
						Metadata:     map[string]interface{}{},
					},
				},
				HasMoreReplies: false,
			}, nil
		},
	}

	ctx, lines := newContext(mock)
	ctx.State.AccessToken = "secret"

	if _, err := cli.ExecuteCommand(ctx, "context th_1"); err != nil {
		t.Fatalf("context error: %v", err)
	}

	if len(*lines) < 4 {
		t.Fatalf("expected at least 4 output lines, got %d: %v", len(*lines), *lines)
	}
	if (*lines)[0] != "thread th_1 root=msg_root replies=1" {
		t.Errorf("line[0] = %q", (*lines)[0])
	}
	if !containsAll((*lines)[1], "root:", "msg_root") {
		t.Errorf("line[1] = %q", (*lines)[1])
	}
	if (*lines)[2] != "replies:" {
		t.Errorf("line[2] = %q", (*lines)[2])
	}
	if !containsAll((*lines)[3], "msg_reply") {
		t.Errorf("line[3] = %q", (*lines)[3])
	}
}

func TestTokenCommandStripsTokenPrefix(t *testing.T) {
	ctx, lines := newContext(&mockClient{})

	// Simulate user copying "token=<value>" from bootstrap output
	keepRunning, err := cli.ExecuteCommand(ctx, "token token=my-secret")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !keepRunning {
		t.Error("expected keepRunning=true")
	}
	if ctx.State.AccessToken != "my-secret" {
		t.Errorf("AccessToken = %q, want %q (token= prefix should be stripped)", ctx.State.AccessToken, "my-secret")
	}
	if len(*lines) == 0 || (*lines)[0] != "access token updated" {
		t.Errorf("unexpected output: %v", *lines)
	}
}

func TestExitReturnsFalse(t *testing.T) {
	ctx, _ := newContext(&mockClient{})
	keepRunning, err := cli.ExecuteCommand(ctx, "exit")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if keepRunning {
		t.Error("expected keepRunning=false for exit command")
	}
}

func containsAll(s string, substrs ...string) bool {
	for _, sub := range substrs {
		if !contains(s, sub) {
			return false
		}
	}
	return true
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 ||
		func() bool {
			for i := 0; i <= len(s)-len(sub); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
			return false
		}())
}
