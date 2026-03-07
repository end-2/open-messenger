package cli

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"open-messenger/frontend-cli-golang/backend"
)

// BackendClient is the interface satisfied by *backend.Client.
type BackendClient interface {
	GetInfo() (*backend.Info, error)
	BootstrapUser(input backend.BootstrapUserInput) (*backend.BootstrapResult, error)
	CreateChannel(accessToken, name string) (*backend.Channel, error)
	GetChannel(accessToken, channelID string) (*backend.Channel, error)
	ListMessages(accessToken, channelID, cursor string) (*backend.MessageList, error)
	CreateMessage(accessToken, channelID string, payload map[string]interface{}) (*backend.Message, error)
	CreateThread(accessToken, channelID, rootMessageID string) (*backend.Thread, error)
	GetThreadContext(accessToken, threadID string) (*backend.ThreadContext, error)
	CreateThreadMessage(accessToken, threadID string, payload map[string]interface{}) (*backend.Message, error)
}

type State struct {
	AccessToken   string
	UserID        string
	Username      string
	ActiveChannel *backend.Channel
}

type CommandContext struct {
	Client    BackendClient
	State     *State
	WriteLine func(string)
}

// SplitCommand splits an input line into tokens, respecting single- and double-quoted strings.
func SplitCommand(line string) []string {
	var tokens []string
	var current strings.Builder
	inSingle := false
	inDouble := false

	for i := 0; i < len(line); i++ {
		ch := line[i]
		switch {
		case ch == '\'' && !inDouble:
			inSingle = !inSingle
		case ch == '"' && !inSingle:
			inDouble = !inDouble
		case ch == ' ' && !inSingle && !inDouble:
			if current.Len() > 0 {
				tokens = append(tokens, current.String())
				current.Reset()
			}
		default:
			current.WriteByte(ch)
		}
	}
	if current.Len() > 0 {
		tokens = append(tokens, current.String())
	}
	return tokens
}

func formatMessage(msg *backend.Message) string {
	threadLabel := ""
	if msg.ThreadID != nil {
		threadLabel = fmt.Sprintf(" thread=%s", *msg.ThreadID)
	}
	return fmt.Sprintf("%s [%s]%s: %s", msg.MessageID, msg.SenderUserID, threadLabel, msg.Text)
}

func formatThreadContext(ctx *backend.ThreadContext) []string {
	lines := []string{
		fmt.Sprintf("thread %s root=%s replies=%d", ctx.Thread.ThreadID, ctx.Thread.RootMessageID, ctx.Thread.ReplyCount),
		fmt.Sprintf("root: %s", formatMessage(&ctx.RootMessage)),
	}
	if len(ctx.Replies) == 0 {
		lines = append(lines, "replies: none")
		return lines
	}
	lines = append(lines, "replies:")
	for i := range ctx.Replies {
		lines = append(lines, fmt.Sprintf("- %s", formatMessage(&ctx.Replies[i])))
	}
	if ctx.HasMoreReplies {
		lines = append(lines, "more replies are available")
	}
	return lines
}

func requireAccessToken(state *State) (string, error) {
	if state.AccessToken == "" {
		return "", fmt.Errorf("no access token is configured. Use `token <value>` or `bootstrap <username>` first")
	}
	return state.AccessToken, nil
}

func requireActiveChannel(state *State) (*backend.Channel, error) {
	if state.ActiveChannel == nil {
		return nil, fmt.Errorf("no active channel. Use `create-channel <name>` or `use-channel <channel_id>` first")
	}
	return state.ActiveChannel, nil
}

// ExecuteCommand processes one input line. Returns (keepRunning, error).
func ExecuteCommand(ctx CommandContext, inputLine string) (bool, error) {
	tokens := SplitCommand(strings.TrimSpace(inputLine))
	if len(tokens) == 0 {
		return true, nil
	}

	command := tokens[0]
	args := tokens[1:]
	writeLine := ctx.WriteLine
	client := ctx.Client
	state := ctx.State

	switch command {
	case "help":
		writeLine("Open Messenger CLI — available commands")
		writeLine("")
		writeLine("Authentication")
		writeLine("  bootstrap <username> [display-name]")
		writeLine("      Create a new user and immediately activate their access token.")
		writeLine("      Example: bootstrap alice \"Alice Smith\"")
		writeLine("")
		writeLine("  token <access-token>")
		writeLine("      Set an existing access token for this session.")
		writeLine("      Example: token eyJhbGciOiJIUzI1NiIsInR5cCI6Ikp...")
		writeLine("")
		writeLine("  whoami")
		writeLine("      Show the current session state (user, token status, active channel).")
		writeLine("")
		writeLine("Server")
		writeLine("  info")
		writeLine("      Show server version and backend configuration.")
		writeLine("")
		writeLine("Channels")
		writeLine("  create-channel <name>")
		writeLine("      Create a new channel and make it the active channel.")
		writeLine("      Example: create-channel general")
		writeLine("")
		writeLine("  use-channel <channel-id>")
		writeLine("      Switch to an existing channel by ID.")
		writeLine("      Example: use-channel ch_01ABC...")
		writeLine("")
		writeLine("Messages  (requires an active channel)")
		writeLine("  list [cursor]")
		writeLine("      List messages in the active channel. Pass cursor for pagination.")
		writeLine("      Example: list")
		writeLine("      Example: list <next_cursor value>")
		writeLine("")
		writeLine("  send <text>")
		writeLine("      Send a message to the active channel. Quote multi-word text.")
		writeLine("      Example: send \"Hello, world!\"")
		writeLine("")
		writeLine("Threads")
		writeLine("  thread <root-message-id>")
		writeLine("      Create a thread starting from an existing message.")
		writeLine("      Example: thread msg_01ABC...")
		writeLine("")
		writeLine("  reply <thread-id> <text>")
		writeLine("      Post a reply to an existing thread.")
		writeLine("      Example: reply th_01ABC... \"This is a reply\"")
		writeLine("")
		writeLine("  context <thread-id>")
		writeLine("      Show the root message and all replies of a thread.")
		writeLine("      Example: context th_01ABC...")
		writeLine("")
		writeLine("Other")
		writeLine("  help    Show this help message.")
		writeLine("  exit    Exit the CLI.")
		writeLine("")
		writeLine("Typical workflow:")
		writeLine("  1. bootstrap alice \"Alice Smith\"   # creates user and activates token")
		writeLine("  2. create-channel general          # creates channel and makes it active")
		writeLine("  3. send \"Hello!\"                   # sends a message to the channel")
		writeLine("  4. list                            # lists messages in the channel")
		return true, nil

	case "info":
		info, err := client.GetInfo()
		if err != nil {
			return true, err
		}
		b, _ := json.MarshalIndent(info, "", "  ")
		writeLine(string(b))
		return true, nil

	case "bootstrap":
		if len(args) == 0 {
			return true, fmt.Errorf("usage: bootstrap <username> [display-name]")
		}
		username := args[0]
		displayName := ""
		if len(args) > 1 {
			displayName = args[1]
		}
		result, err := client.BootstrapUser(backend.BootstrapUserInput{
			Username:    username,
			DisplayName: displayName,
			TokenType:   "user_token",
			Scopes:      []string{"channels:read", "channels:write", "messages:read", "messages:write"},
		})
		if err != nil {
			return true, err
		}
		state.AccessToken = result.Token.Token
		state.UserID = result.User.UserID
		state.Username = result.User.Username
		writeLine(fmt.Sprintf("bootstrapped user=%s token=%s", result.User.Username, result.Token.Token))
		writeLine(fmt.Sprintf("logged in as %s — token is now active. Next: `create-channel <name>`", result.User.Username))
		return true, nil

	case "token":
		if len(args) == 0 {
			return true, fmt.Errorf("usage: token <access-token>")
		}
		state.AccessToken = strings.TrimPrefix(args[0], "token=")
		writeLine("access token updated")
		return true, nil

	case "whoami":
		type whoamiOutput struct {
			Username       string           `json:"username"`
			UserID         string           `json:"user_id"`
			HasAccessToken bool             `json:"has_access_token"`
			ActiveChannel  *backend.Channel `json:"active_channel"`
		}
		out := whoamiOutput{
			Username:       state.Username,
			UserID:         state.UserID,
			HasAccessToken: state.AccessToken != "",
			ActiveChannel:  state.ActiveChannel,
		}
		b, _ := json.MarshalIndent(out, "", "  ")
		writeLine(string(b))
		return true, nil

	case "create-channel":
		name := strings.TrimSpace(strings.Join(args, " "))
		if name == "" {
			return true, fmt.Errorf("usage: create-channel <name>")
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		ch, err := client.CreateChannel(token, name)
		if err != nil {
			return true, err
		}
		state.ActiveChannel = ch
		writeLine(fmt.Sprintf("active channel=%s name=%s", ch.ChannelID, ch.Name))
		return true, nil

	case "use-channel":
		if len(args) == 0 {
			return true, fmt.Errorf("usage: use-channel <channel-id>")
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		ch, err := client.GetChannel(token, args[0])
		if err != nil {
			return true, err
		}
		state.ActiveChannel = ch
		writeLine(fmt.Sprintf("active channel=%s name=%s", ch.ChannelID, ch.Name))
		return true, nil

	case "list":
		ch, err := requireActiveChannel(state)
		if err != nil {
			return true, err
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		cursor := ""
		if len(args) > 0 {
			cursor = args[0]
		}
		msgs, err := client.ListMessages(token, ch.ChannelID, cursor)
		if err != nil {
			return true, err
		}
		if len(msgs.Items) == 0 {
			writeLine("no messages")
		} else {
			for i := range msgs.Items {
				writeLine(formatMessage(&msgs.Items[i]))
			}
		}
		if msgs.NextCursor != nil {
			writeLine(fmt.Sprintf("next_cursor=%s", *msgs.NextCursor))
		}
		return true, nil

	case "send":
		text := strings.TrimSpace(strings.Join(args, " "))
		if text == "" {
			return true, fmt.Errorf("usage: send <text>")
		}
		ch, err := requireActiveChannel(state)
		if err != nil {
			return true, err
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		msg, err := client.CreateMessage(token, ch.ChannelID, map[string]interface{}{"text": text})
		if err != nil {
			return true, err
		}
		writeLine(fmt.Sprintf("sent %s", formatMessage(msg)))
		return true, nil

	case "thread":
		if len(args) == 0 {
			return true, fmt.Errorf("usage: thread <root-message-id>")
		}
		ch, err := requireActiveChannel(state)
		if err != nil {
			return true, err
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		th, err := client.CreateThread(token, ch.ChannelID, args[0])
		if err != nil {
			return true, err
		}
		writeLine(fmt.Sprintf("thread %s created for root=%s", th.ThreadID, th.RootMessageID))
		return true, nil

	case "reply":
		if len(args) < 2 {
			return true, fmt.Errorf("usage: reply <thread-id> <text>")
		}
		threadID := args[0]
		text := strings.TrimSpace(strings.Join(args[1:], " "))
		if text == "" {
			return true, fmt.Errorf("usage: reply <thread-id> <text>")
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		msg, err := client.CreateThreadMessage(token, threadID, map[string]interface{}{"text": text})
		if err != nil {
			return true, err
		}
		writeLine(fmt.Sprintf("replied %s", formatMessage(msg)))
		return true, nil

	case "context":
		if len(args) == 0 {
			return true, fmt.Errorf("usage: context <thread-id>")
		}
		token, err := requireAccessToken(state)
		if err != nil {
			return true, err
		}
		threadCtx, err := client.GetThreadContext(token, args[0])
		if err != nil {
			return true, err
		}
		for _, line := range formatThreadContext(threadCtx) {
			writeLine(line)
		}
		return true, nil

	case "exit", "quit":
		return false, nil

	default:
		return true, fmt.Errorf("unknown command: %s. Use `help` to see available commands", command)
	}
}

// RunCLI starts the interactive CLI read-eval-print loop.
func RunCLI(client BackendClient, initialToken, baseURL string, in io.Reader, out io.Writer) {
	state := &State{
		AccessToken: initialToken,
	}

	writeLine := func(msg string) {
		fmt.Fprintln(out, msg)
	}

	fmt.Fprintf(out, "Open Messenger CLI connected to %s\n", baseURL)
	fmt.Fprintln(out, "Use `help` to see available commands.")
	if state.AccessToken == "" {
		fmt.Fprintln(out, "Tip: Run `bootstrap <username>` to create a user and activate a token.")
	} else {
		fmt.Fprintln(out, "Access token is configured. Run `whoami` to check your session.")
	}

	scanner := bufio.NewScanner(in)
	for {
		if state.ActiveChannel != nil {
			fmt.Fprintf(out, "om:%s> ", state.ActiveChannel.Name)
		} else {
			fmt.Fprint(out, "om> ")
		}

		if !scanner.Scan() {
			break
		}
		line := scanner.Text()

		keepRunning, err := ExecuteCommand(CommandContext{
			Client:    client,
			State:     state,
			WriteLine: writeLine,
		}, line)

		if err != nil {
			var backendErr *backend.BackendError
			if isBackendError(err, &backendErr) {
				fmt.Fprintf(out, "backend error %d: %v\n", backendErr.Status, backendErr.Details)
			} else {
				fmt.Fprintf(out, "error: %s\n", err.Error())
			}
		}

		if !keepRunning {
			break
		}
	}
}

func isBackendError(err error, target **backend.BackendError) bool {
	if be, ok := err.(*backend.BackendError); ok {
		*target = be
		return true
	}
	return false
}

// Run is the top-level entry point called from main.
func Run(osArgs []string) {
	baseURL := os.Getenv("OPEN_MESSENGER_API_URL")
	if baseURL == "" {
		baseURL = "http://127.0.0.1:8000"
	}
	adminToken := os.Getenv("OPEN_MESSENGER_ADMIN_API_TOKEN")
	if adminToken == "" {
		adminToken = "dev-admin-token"
	}
	initialToken := ""
	if len(osArgs) > 0 {
		initialToken = osArgs[0]
	}
	if initialToken == "" {
		initialToken = os.Getenv("OPEN_MESSENGER_ACCESS_TOKEN")
	}

	client := backend.NewClient(baseURL, adminToken)
	RunCLI(client, initialToken, baseURL, os.Stdin, os.Stdout)
}
