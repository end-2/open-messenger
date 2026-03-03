# Open Messenger TODO

- 기준 문서: `docs/DESIGN.md` (v0.1, 2026-03-03)
- 목적: 설계 문서를 구현 가능한 작업 단위로 분해

## 1. 프로젝트 부트스트랩

- [x] Python 3 백엔드 프로젝트 골격 생성 (`FastAPI`, `Uvicorn`, `asyncio`)
- [x] Node.js 프론트엔드 프로젝트 골격 생성 (`TypeScript`, `Next.js` 또는 BFF)
- [x] 공통 환경 설정 파일 정의 (`.env`, `config.yaml`, 실행 프로파일)
- [x] 로컬 개발용 기본 실행 스크립트 구성 (`make`, `npm scripts`)

## 2. 도메인/데이터 모델

- [ ] 엔티티 정의: `User`, `Token`, `Channel`, `ChannelMember`, `Message`, `Thread`, `FileObject`, `EventLog`
- [ ] ID 표준 적용: ULID 생성/검증 유틸 구현
- [ ] 시간 포맷 표준화: ISO8601 UTC 유틸 구현
- [ ] 메시지 본문(content)과 메타데이터 분리 모델 구현 (`content_ref`)

## 3. 저장소 추상화 계층

- [x] `MessageContentStore` 인터페이스 정의 (`put/get/delete`)
- [x] `MetadataStore` 인터페이스 정의 (`create/get/list`)
- [x] 메시지 저장소 구현: `memory`
- [x] 메시지 저장소 구현: `file`
- [ ] 메시지 저장소 구현: `redis`
- [x] 메타데이터 저장소 구현: `memory`
- [x] 메타데이터 저장소 구현: `file`
- [ ] 메타데이터 저장소 구현: `mysql`
- [x] 런타임 설정 기반 백엔드 선택 로더 구현 (`message_content_backend`, `metadata_backend`)

## 4. 인증/인가

- [x] `Authorization: Bearer <token>` 파서 및 미들웨어 구현
- [x] 토큰 해시 저장(`sha256`) 및 평문 1회 노출 정책 구현
- [x] 토큰 스코프 검사 구현 (`channels:*`, `messages:*`, `files:*`)
- [ ] 토큰 회전(rotation) API 구현
- [x] 토큰 폐기(revoke) API 구현
- [ ] 기본 rate limit 적용

## 5. Native API (`/v1`)

- [x] `POST /v1/channels`
- [x] `GET /v1/channels/{channel_id}`
- [x] `POST /v1/channels/{channel_id}/messages`
- [x] `GET /v1/channels/{channel_id}/messages`
- [x] `POST /v1/channels/{channel_id}/threads`
- [x] `POST /v1/threads/{thread_id}/messages`
- [ ] `POST /v1/files` (multipart)
- [ ] `GET /v1/files/{file_id}`
- [x] Cursor pagination 공통 처리 구현
- [ ] Idempotency Key 처리(`idempotency_key`) 구현
- [ ] 구조화 에러 응답 표준 구현 (`code`, `message`, `retryable`)

## 6. Admin API (`/admin/v1`)

- [x] `POST /admin/v1/users` (사용자 생성)
- [x] `POST /admin/v1/tokens` (토큰 생성)
- [x] `DELETE /admin/v1/tokens/{token_id}` (토큰 폐기)
- [x] `/v1` 경로에서 user/token 생성 차단 검증
- [x] 관리자 경로 접근 제어 및 감사 로그 추가

## 7. Compatibility API

- [ ] Slack 호환: `POST /compat/slack/chat.postMessage`
- [ ] Slack 호환: `POST /compat/slack/files.upload`
- [ ] Telegram 호환: `POST /compat/telegram/bot{token}/sendMessage`
- [ ] Telegram 호환: `POST /compat/telegram/bot{token}/sendDocument`
- [ ] Discord 호환: `POST /compat/discord/channels/{channel_id}/messages`
- [ ] Slack `thread_ts` <-> 내부 `thread_id` 매핑 테이블 구현
- [ ] Telegram `reply_to_message_id` 매핑 구현
- [ ] Discord `message_reference` 매핑 구현

## 8. 실시간 이벤트

- [ ] 이벤트 타입 정의: `message.created`, `message.updated`, `message.deleted`, `thread.created`, `file.uploaded`
- [ ] 이벤트 발행 파이프라인 구현
- [ ] SSE 엔드포인트 구현: `GET /v1/events/stream`
- [ ] WebSocket 게이트웨이 구현
- [ ] 이벤트 페이로드 표준 스키마 적용 (`event_id`, `type`, `occurred_at`, `data`)

## 9. 파일 첨부

- [ ] 파일 저장 루트 구성: `./data/files`
- [ ] 업로드 크기 제한 구현 (`max_upload_mb`)
- [ ] 파일 무결성 해시(`sha256`) 저장
- [ ] 파일 메타데이터(`FileObject`) 저장소 연동
- [ ] 다운로드 시 토큰 권한 검증 구현

## 10. AI Agent 친화 API

- [ ] Batch 조회 API: `POST /v1/messages:batchGet`
- [ ] Batch 생성 API: `POST /v1/messages:batchCreate`
- [ ] 스레드 컨텍스트 API: `GET /v1/threads/{thread_id}/context`
- [ ] 재시도 안전성 검증(멱등 처리) 테스트
- [ ] 에이전트 사용 예시(요청/응답 샘플) 문서화

## 11. 관측성/운영

- [ ] 구조화 로그(JSON) 적용
- [ ] `x-request-id` 전파 구현
- [ ] 메트릭 수집: p50/p95/p99 지연시간, 에러율, 메시지 처리량, 이벤트 lag
- [ ] 헬스체크/레디니스 엔드포인트 추가

## 12. 테스트

- [ ] Storage backend contract test 작성
- [ ] Native/Admin API 통합 테스트 작성
- [ ] Compatibility API 회귀 테스트 작성 (Slack/Telegram/Discord 기본 시나리오)
- [ ] 토큰 스코프/권한 테스트 작성
- [ ] 대용량 메시지/파일 부하 테스트 작성

## 13. 배포 준비

- [ ] 단일 인스턴스 배포 프로파일 구성 (`file + file`)
- [ ] 운영 배포 프로파일 구성 (`redis + mysql`)
- [ ] 환경별 설정 템플릿 작성 (`dev`, `staging`, `prod`)
- [ ] 롤백 절차/운영 런북 초안 작성

## 14. 완료 기준 (MVP)

- [ ] 채널/메시지/쓰레드/파일 기능이 `/v1`에서 동작
- [ ] user/token 생성이 `/admin/v1`에서만 허용
- [ ] Slack/Telegram/Discord 기본 메시지/파일 API 호환 동작
- [ ] 선택형 저장소 백엔드 전환이 설정만으로 가능
- [ ] SSE 또는 WebSocket을 통한 실시간 이벤트 수신 가능
- [ ] 핵심 테스트 스위트가 CI에서 안정적으로 통과
