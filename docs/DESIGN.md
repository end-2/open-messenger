# Open Messenger Design Document

- 문서 버전: `v0.2`
- 작성일: `2026-03-03`
- 대상: Slack/Telegram/Discord 스타일의 멀티채널 메신저 플랫폼

## 1. 목표

본 시스템은 다음을 만족하는 범용 메신저 플랫폼을 목표로 한다.

1. Slack, Telegram, Discord의 **기본 메시징/파일 API**와 호환되는 인터페이스 제공
2. **채널(Channel)** 중심 구조와 채널 내부 **쓰레드(Thread)** 지원
3. 인증 방식은 **API Token only**
4. Front-end는 **Node.js**, Back-end는 **Python 3** 기반
5. 메시지 내용 저장소는 `memory | file | redis` 중 선택 가능
6. 메타데이터 저장소는 `memory | file | mysql` 중 선택 가능
7. AI Agent가 사용하기 쉬운 일관된 API 제공

## 2. 범위

### 2.1 In-Scope (MVP)

- 사용자/봇 토큰 인증
- 채널 생성/조회/참여
- 메시지 전송/조회/수정/삭제
- 쓰레드 생성(부모 메시지 기반)/답글 조회
- 파일 업로드/다운로드/메시지 첨부
- 실시간 이벤트(WebSocket/SSE) 전달
- Slack/Telegram/Discord 기본 API 호환 레이어
- 저장소 백엔드 교체 가능한 Storage Abstraction

### 2.2 Out-of-Scope (초기 버전 제외)

- E2E 암호화
- 음성/영상 통화
- 고급 권한 정책 엔진(RBAC/ABAC 세분화)
- 대규모 멀티리전 active-active

## 3. 아키텍처 개요

### 3.1 상위 구성

1. Front-end (Node.js)
2. API Server (Python 3, FastAPI)
3. Compatibility Adapters (Slack/Telegram/Discord 요청 변환)
4. Core Messaging Service (도메인 로직)
5. Realtime Gateway (WebSocket/SSE)
6. Storage Layer
7. Token Auth Service

### 3.2 기술 선택

- Front-end: `Node.js + TypeScript + Next.js` (또는 Express 기반 BFF)
- Back-end: `Python 3.12 + FastAPI + Uvicorn`
- 비동기 처리: `asyncio`
- 파일 저장: 로컬 파일 시스템(초기), 이후 Object Storage 확장 가능

## 4. 논리 아키텍처

```text
[Web/CLI/AI Agent Client]
          |
          v
[API Gateway / Router]
   | Native API (/v1)
   | Admin API (/admin/v1)
   | Slack Compat (/compat/slack)
   | Telegram Compat (/compat/telegram)
   | Discord Compat (/compat/discord)
          |
          v
[Auth Token Middleware]
          |
          v
[Messaging Core Service]
   | Channel Service
   | Thread Service
   | Message Service
   | File Service
   | Event Service
          |
          v
[Storage Abstraction Layer]
   | MessageContentStore: memory/file/redis
   | MetadataStore: memory/file/mysql
   | FileBinaryStore: local (extensible)
```

## 5. 데이터 모델

메시지 본문(content)과 메타데이터를 분리 저장한다.

### 5.1 엔티티

- `User`
- `Token`
- `Channel`
- `ChannelMember`
- `Message`
- `Thread`
- `FileObject`
- `EventLog`

### 5.2 핵심 스키마 (개념)

#### `Message` (metadata store)

- `message_id` (ULID)
- `channel_id`
- `thread_id` (nullable)
- `sender_user_id`
- `content_ref` (message content 저장소 포인터)
- `attachments` (file_id 배열)
- `created_at`, `updated_at`, `deleted_at`
- `compat_origin` (`native|slack|telegram|discord`)
- `idempotency_key` (nullable)

#### `Thread` (metadata store)

- `thread_id`
- `channel_id`
- `root_message_id`
- `reply_count`
- `last_message_at`

#### `FileObject` (metadata store)

- `file_id`
- `uploader_user_id`
- `filename`
- `mime_type`
- `size_bytes`
- `storage_backend`
- `storage_path`
- `sha256`

#### Message Content (content store)

- key: `content_ref`
- value: `{ text, blocks, mentions, raw_payload }`

## 6. 저장소 구성 (Configurable)

### 6.1 메시지 내용 저장소

- `memory`: 개발/테스트 용도
- `file`: 단일 노드 운영, JSONL 또는 key-value 파일
- `redis`: 고속 조회/TTL/실시간 시스템 연계

공통 인터페이스:

```python
class MessageContentStore(Protocol):
    async def put(self, content_id: str, payload: dict) -> None: ...
    async def get(self, content_id: str) -> dict | None: ...
    async def delete(self, content_id: str) -> None: ...
```

### 6.2 메타데이터 저장소

- `memory`: 개발/테스트
- `file`: 로컬 임베디드 운영 (소규모)
- `mysql`: 운영 기본 권장

공통 인터페이스:

```python
class MetadataStore(Protocol):
    async def create_message(self, msg: dict) -> dict: ...
    async def get_message(self, message_id: str) -> dict | None: ...
    async def list_channel_messages(self, channel_id: str, cursor: str | None, limit: int) -> list[dict]: ...
    async def create_channel(self, channel: dict) -> dict: ...
```

### 6.3 권장 조합

- 로컬 개발: `memory + memory`
- 단일 인스턴스: `file + file`
- 운영: `redis + mysql`

### 6.4 File Binary Storage

- Default backend: `local`
- Config key: `file_storage_backend`
- Local backend root: `files_root_dir`
- Message attachments store file IDs in message metadata and must reference existing `FileObject` records.
- Binary persistence is separated from metadata persistence so future object storage backends can be added without changing message or file metadata APIs.

## 7. 인증/인가

요구사항에 따라 인증은 API Token만 사용한다.

### 7.1 토큰 유형

- `user_token`: 사용자 동작용
- `bot_token`: 봇/AI Agent 자동화용
- `service_token`: 내부 서비스 연동용

### 7.2 토큰 포맷/검증

- 헤더: `Authorization: Bearer <token>`
- Token format: JWT-like (`<base64url(header)>.<base64url(payload)>.<base64url(signature)>`)
- Header claims: `alg=HS256`, `typ=JWT-LIKE`
- Payload claims: `tid` (token_id), `sub` (user_id), `token_type`, `scopes`, `iat`
- Signature: `HMAC-SHA256(base64url(header) + "." + base64url(payload), signing_secret)`
- 토큰 저장 시 평문 저장 금지 (`sha256` 해시)
- 스코프 예시: `channels:read`, `channels:write`, `messages:read`, `messages:write`, `files:write`

### 7.3 보안 기준

- 토큰 생성 시 1회만 평문 노출
- 토큰 회전(rotation) 및 폐기(revoke) API 제공
- Native API 인증/인가는 JWT-like Bearer 토큰 검증 + scope 검사로 처리
- IP allowlist(선택), rate limit 기본 적용
- `user/token` 생성은 관리자 전용 `/admin/v1` 경로에서만 허용

## 8. API 설계

### 8.1 Native API (권장)

Base path: `/v1`

핵심 엔드포인트:

1. `POST /channels`
2. `GET /channels/{channel_id}`
3. `POST /channels/{channel_id}/messages`
4. `GET /channels/{channel_id}/messages?cursor=&limit=`
5. `POST /channels/{channel_id}/threads` (root_message_id 기반)
6. `POST /threads/{thread_id}/messages`
7. `POST /files` (multipart)
8. `GET /files/{file_id}`
9. `POST /messages:batchGet`
10. `POST /messages:batchCreate`
11. `GET /threads/{thread_id}/context?limit=`

일반 `/v1` 경로에서는 `user/token` 생성 API를 제공하지 않는다.

Message list pagination contract:

- `GET /v1/channels/{channel_id}/messages` uses cursor pagination.
- Results are returned in stable channel order from oldest to newest.
- `limit` defaults to `50` and is constrained to `1..200`.
- `cursor` is the last `message_id` returned by the previous page.
- The response returns `items` and `next_cursor`.
- When `next_cursor` is `null`, there are no more items to read.
- Thread replies are included in the same channel message stream and preserve the same pagination rules.

Response shape:

```json
{
  "items": [
    {
      "message_id": "msg_01H...",
      "channel_id": "ch_01H...",
      "thread_id": null,
      "sender_user_id": "usr_01H...",
      "content_ref": "cnt_01H...",
      "text": "hello",
      "attachments": [],
      "created_at": "2026-03-03T11:22:33Z",
      "updated_at": "2026-03-03T11:22:33Z",
      "deleted_at": null,
      "compat_origin": "native",
      "idempotency_key": null,
      "metadata": {}
    }
  ],
  "next_cursor": "msg_01H..."
}
```

메시지 전송 요청 예시:

```json
{
  "text": "hello",
  "thread_id": "th_01H...",
  "attachments": ["file_01H..."],
  "idempotency_key": "req-20260303-0001",
  "metadata": {
    "source": "agent"
  }
}
```

### 8.2 Admin API (관리자 전용)

Base path: `/admin/v1`

핵심 엔드포인트:

1. `POST /users` (사용자 생성)
2. `POST /tokens` (토큰 생성)
3. `DELETE /tokens/{token_id}` (토큰 폐기)

### 8.3 Compatibility API

호환 레이어는 “완전 복제”가 아니라 기본 기능 호환을 목표로 한다.

#### Slack 호환 (기본)

- `POST /compat/slack/chat.postMessage`
- `POST /compat/slack/files.upload`

매핑:

- `channel` -> `channel_id`
- `thread_ts` -> `thread_id` (내부 변환 테이블 유지)
- `text` -> message content text

#### Telegram 호환 (기본 Bot API 스타일)

- `POST /compat/telegram/bot{token}/sendMessage`
- `POST /compat/telegram/bot{token}/sendDocument`

매핑:

- `chat_id` -> `channel_id`
- `reply_to_message_id` -> thread or reply 관계로 변환
- `document` -> 파일 업로드 처리

#### Discord 호환 (기본)

- `POST /compat/discord/channels/{channel_id}/messages`

매핑:

- `content` -> message text
- `message_reference` -> thread/reply 관계
- multipart attachment -> `FileObject`

### 8.4 AI Agent Friendly API 원칙

1. ID/시간 포맷 일관성 (ULID, ISO8601 UTC)
2. 모든 리스트 API에 cursor pagination
3. Idempotency Key 지원 (재시도 안전)
4. 구조화된 에러 코드 (`code`, `message`, `retryable`)
5. Batch API 제공: `POST /v1/messages:batchGet`, `POST /v1/messages:batchCreate`
6. 대화 컨텍스트 API: `GET /v1/threads/{thread_id}/context?limit=`
7. 이벤트 스트림: `GET /v1/events/stream` (SSE) 또는 WebSocket

Current implementation notes:

- Native message pagination is implemented in `GET /v1/channels/{channel_id}/messages`.
- The API layer computes `next_cursor` from the last item of a full page.
- All metadata store implementations expose `list_channel_messages(channel_id, cursor, limit)`.
- All metadata store implementations expose `list_thread_messages(channel_id, thread_id, limit)` for thread context retrieval.
- `memory`, `file`, and `mysql` metadata backends already implement the same cursor-based contract.
- Realtime delivery is available via both `GET /v1/events/stream` and `GET /v1/events/ws`.
- `POST /v1/messages:batchGet` returns found messages in request order plus `not_found_ids`.
- `POST /v1/messages:batchCreate` accepts multiple native-style messages with per-item `channel_id`; idempotency is applied per item using the existing `idempotency_key`.
- `GET /v1/threads/{thread_id}/context?limit=` returns the thread metadata, the root message, the oldest replies up to `limit`, and `has_more_replies`.

## 9. 이벤트 및 실시간

이벤트 타입:

- `message.created`
- `message.updated`
- `message.deleted`
- `thread.created`
- `file.uploaded`

전달 채널:

- WebSocket: 양방향 인터랙션
- SSE: 서버 -> 클라이언트 단방향 스트림 (AI Agent 친화)

WebSocket gateway contract:

- Endpoint: `GET /v1/events/ws`
- Authentication: `Authorization: Bearer <token>` header or `access_token` query parameter
- Required scope: `messages:read`
- Server events use the same payload schema as the SSE event stream
- Client may send `ping` text frames and receives `{"type":"pong"}`

초기 구현 범위:

- `GET /v1/events/stream` SSE 엔드포인트 제공
- `GET /v1/events/ws` WebSocket 게이트웨이 제공
- 표준 이벤트 스키마를 사용해 `message.created`, `thread.created`, `file.uploaded` 발행
- `message.updated`, `message.deleted` 이벤트는 후속 단계에서 확장

이벤트 페이로드 표준:

```json
{
  "event_id": "evt_01H...",
  "type": "message.created",
  "occurred_at": "2026-03-03T11:22:33Z",
  "data": {
    "channel_id": "ch_01H...",
    "message_id": "msg_01H..."
  }
}
```

## 10. 파일 첨부 설계

1. 클라이언트가 `POST /v1/files`로 multipart 업로드
2. 서버가 파일 저장 후 `file_id` 반환
3. 메시지 전송 시 `attachments`에 `file_id` 포함
4. 다운로드는 토큰 기반 권한 검증 후 제공

초기 구현:

- 실제 바이너리는 `./data/files` 저장
- 메타데이터는 MetadataStore에 저장

## 11. 설정 예시

```yaml
server:
  host: 0.0.0.0
  port: 8080

auth:
  token_only: true
  require_scope: true

storage:
  message_content_backend: redis   # memory | file | redis
  metadata_backend: mysql          # memory | file | mysql

redis:
  url: redis://localhost:6379/0

mysql:
  dsn: mysql+pymysql://messenger:***@localhost:3306/messenger

files:
  root_dir: ./data/files
  max_upload_mb: 50
```

## 12. 배포/확장 전략

### 12.1 초기

- 단일 API 인스턴스 + file backend
- 개발 속도 우선

### 12.2 운영

- API 서버 수평 확장
- Redis(메시지 content + pub/sub), MySQL(metadata)
- 파일 저장소 외부화(S3 호환) 가능하도록 인터페이스 유지

## 13. 관측성/운영

- 구조화 로그(JSON)
- 메트릭: 요청 지연시간(p50/p95/p99), 에러율, 메시지 처리량, 이벤트 lag
- Trace ID 전파 (`x-request-id`)

## 14. 테스트 전략

1. Storage backend contract test (공통 인터페이스 검증)
2. API integration test (native + compat)
3. Token scope/권한 테스트
4. 대용량 메시지/파일 부하 테스트
5. 회귀 테스트: Slack/Telegram/Discord 기본 호출 시나리오

## 15. 구현 단계 제안

1. Domain 모델 + Storage interface 정의
2. Native/Admin API 구현 (채널/메시지/쓰레드/파일/관리자 user-token)
3. Token auth 및 scope enforcement
4. Compatibility adapter 3종 구현
5. Realtime 이벤트 채널
6. AI Agent 전용 배치/컨텍스트 API 추가
7. 성능 튜닝 및 운영 지표 추가

## 16. 결정 사항 요약

1. 채널-쓰레드 2단 구조를 핵심 데이터 모델로 채택
2. 인증은 API Token only
3. 메시지 content와 metadata 저장소 분리
4. Native API + Compatibility API 병행 제공
5. AI Agent 사용성을 위해 idempotency/batch/context/event-stream 기본 제공
6. user/token 생성은 `/admin/v1` 경로로 분리
