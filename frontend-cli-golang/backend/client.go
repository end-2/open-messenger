package backend

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type Info struct {
	Service            string `json:"service"`
	Version            string `json:"version"`
	Environment        string `json:"environment"`
	ContentBackend     string `json:"content_backend"`
	MetadataBackend    string `json:"metadata_backend"`
	FileStorageBackend string `json:"file_storage_backend"`
	ContentStoreImpl   string `json:"content_store_impl"`
	MetadataStoreImpl  string `json:"metadata_store_impl"`
	FileStoreImpl      string `json:"file_store_impl"`
}

type User struct {
	UserID      string  `json:"user_id"`
	Username    string  `json:"username"`
	DisplayName *string `json:"display_name"`
	CreatedAt   string  `json:"created_at"`
}

type Token struct {
	TokenID   string   `json:"token_id"`
	UserID    string   `json:"user_id"`
	TokenType string   `json:"token_type"`
	Scopes    []string `json:"scopes"`
	CreatedAt string   `json:"created_at"`
	RevokedAt *string  `json:"revoked_at"`
	Token     string   `json:"token"`
}

type Channel struct {
	ChannelID string `json:"channel_id"`
	Name      string `json:"name"`
	CreatedAt string `json:"created_at"`
}

type Thread struct {
	ThreadID      string `json:"thread_id"`
	ChannelID     string `json:"channel_id"`
	RootMessageID string `json:"root_message_id"`
	ReplyCount    int    `json:"reply_count"`
	LastMessageAt string `json:"last_message_at"`
	CreatedAt     string `json:"created_at"`
}

type Message struct {
	MessageID      string                 `json:"message_id"`
	ChannelID      string                 `json:"channel_id"`
	ThreadID       *string                `json:"thread_id"`
	SenderUserID   string                 `json:"sender_user_id"`
	ContentRef     string                 `json:"content_ref"`
	Text           string                 `json:"text"`
	Attachments    []string               `json:"attachments"`
	CreatedAt      string                 `json:"created_at"`
	UpdatedAt      string                 `json:"updated_at"`
	DeletedAt      *string                `json:"deleted_at"`
	CompatOrigin   string                 `json:"compat_origin"`
	IdempotencyKey *string                `json:"idempotency_key"`
	Metadata       map[string]interface{} `json:"metadata"`
}

type ThreadContext struct {
	Thread         Thread    `json:"thread"`
	RootMessage    Message   `json:"root_message"`
	Replies        []Message `json:"replies"`
	HasMoreReplies bool      `json:"has_more_replies"`
}

type MessageList struct {
	Items      []Message `json:"items"`
	NextCursor *string   `json:"next_cursor"`
}

type BootstrapUserInput struct {
	Username    string
	DisplayName string
	TokenType   string
	Scopes      []string
}

type BootstrapResult struct {
	User  User
	Token Token
}

type BackendError struct {
	Status  int
	Details interface{}
}

func (e *BackendError) Error() string {
	return fmt.Sprintf("backend request failed with status %d: %v", e.Status, e.Details)
}

type Client struct {
	BaseURL    string
	AdminToken string
	httpClient *http.Client
}

func NewClient(baseURL, adminToken string) *Client {
	return &Client{
		BaseURL:    strings.TrimRight(baseURL, "/"),
		AdminToken: adminToken,
		httpClient: &http.Client{},
	}
}

func (c *Client) doRequest(method, path, adminToken, accessToken string, body, result interface{}) error {
	var bodyReader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return err
		}
		bodyReader = bytes.NewReader(b)
	}

	req, err := http.NewRequest(method, c.BaseURL+path, bodyReader)
	if err != nil {
		return err
	}

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if adminToken != "" {
		req.Header.Set("X-Admin-Token", adminToken)
	}
	if accessToken != "" {
		req.Header.Set("Authorization", "Bearer "+accessToken)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var details interface{}
		if jsonErr := json.Unmarshal(respBody, &details); jsonErr != nil {
			details = string(respBody)
		}
		return &BackendError{Status: resp.StatusCode, Details: details}
	}

	if resp.StatusCode == 204 || result == nil {
		return nil
	}

	return json.Unmarshal(respBody, result)
}

func (c *Client) GetInfo() (*Info, error) {
	var info Info
	if err := c.doRequest("GET", "/v1/info", "", "", nil, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

func (c *Client) BootstrapUser(input BootstrapUserInput) (*BootstrapResult, error) {
	var displayName interface{}
	if input.DisplayName != "" {
		displayName = input.DisplayName
	}

	var user User
	if err := c.doRequest("POST", "/admin/v1/users", c.AdminToken, "", map[string]interface{}{
		"username":     input.Username,
		"display_name": displayName,
	}, &user); err != nil {
		return nil, err
	}

	var token Token
	if err := c.doRequest("POST", "/admin/v1/tokens", c.AdminToken, "", map[string]interface{}{
		"user_id":    user.UserID,
		"token_type": input.TokenType,
		"scopes":     input.Scopes,
	}, &token); err != nil {
		return nil, err
	}

	return &BootstrapResult{User: user, Token: token}, nil
}

func (c *Client) CreateChannel(accessToken, name string) (*Channel, error) {
	var ch Channel
	if err := c.doRequest("POST", "/v1/channels", "", accessToken, map[string]string{"name": name}, &ch); err != nil {
		return nil, err
	}
	return &ch, nil
}

func (c *Client) GetChannel(accessToken, channelID string) (*Channel, error) {
	var ch Channel
	if err := c.doRequest("GET", "/v1/channels/"+channelID, "", accessToken, nil, &ch); err != nil {
		return nil, err
	}
	return &ch, nil
}

func (c *Client) ListMessages(accessToken, channelID, cursor string) (*MessageList, error) {
	path := "/v1/channels/" + channelID + "/messages"
	if cursor != "" {
		path += "?cursor=" + cursor
	}
	var list MessageList
	if err := c.doRequest("GET", path, "", accessToken, nil, &list); err != nil {
		return nil, err
	}
	return &list, nil
}

func (c *Client) CreateMessage(accessToken, channelID string, payload map[string]interface{}) (*Message, error) {
	var msg Message
	if err := c.doRequest("POST", "/v1/channels/"+channelID+"/messages", "", accessToken, payload, &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}

func (c *Client) CreateThread(accessToken, channelID, rootMessageID string) (*Thread, error) {
	var th Thread
	if err := c.doRequest("POST", "/v1/channels/"+channelID+"/threads", "", accessToken,
		map[string]string{"root_message_id": rootMessageID}, &th); err != nil {
		return nil, err
	}
	return &th, nil
}

func (c *Client) GetThreadContext(accessToken, threadID string) (*ThreadContext, error) {
	var ctx ThreadContext
	if err := c.doRequest("GET", "/v1/threads/"+threadID+"/context", "", accessToken, nil, &ctx); err != nil {
		return nil, err
	}
	return &ctx, nil
}

func (c *Client) CreateThreadMessage(accessToken, threadID string, payload map[string]interface{}) (*Message, error) {
	var msg Message
	if err := c.doRequest("POST", "/v1/threads/"+threadID+"/messages", "", accessToken, payload, &msg); err != nil {
		return nil, err
	}
	return &msg, nil
}
