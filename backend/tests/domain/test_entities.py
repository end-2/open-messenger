from app.domain.entities import (
    Channel,
    ChannelMember,
    EventLog,
    FileObject,
    Message,
    MessageContent,
    Thread,
    Token,
    User,
)


def test_message_and_content_are_separated_by_content_ref() -> None:
    content = MessageContent(text="hello", blocks=[{"type": "section"}], mentions=["usr_1"])
    metadata = Message(
        message_id="msg_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        channel_id="ch_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        thread_id=None,
        sender_user_id="usr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        content_ref="cnt_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        attachments=[],
        metadata={"source": "unit-test"},
    )

    content_payload = content.to_dict()
    metadata_payload = metadata.to_dict()

    assert "content_ref" not in content_payload
    assert metadata_payload["content_ref"].startswith("cnt_")
    assert metadata_payload["metadata"] == {"source": "unit-test"}


def test_all_entities_produce_dict_payloads() -> None:
    samples = [
        User(user_id="usr_01ARZ3NDEKTSV4RRFFQ69G5FAV", username="alice"),
        Token(
            token_id="tok_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            user_id="usr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            token_type="user_token",
            scopes=["messages:read"],
        ),
        Channel(channel_id="ch_01ARZ3NDEKTSV4RRFFQ69G5FAV", name="general"),
        ChannelMember(
            channel_member_id="chm_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            channel_id="ch_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            user_id="usr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            role="member",
        ),
        Thread(
            thread_id="th_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            channel_id="ch_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            root_message_id="msg_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        ),
        FileObject(
            file_id="fil_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            uploader_user_id="usr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            filename="doc.txt",
            mime_type="text/plain",
            size_bytes=4,
            storage_path="/tmp/doc.txt",
            sha256="abc123",
        ),
        EventLog(
            event_id="evt_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            type="message.created",
            data={"message_id": "msg_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
        ),
    ]

    for sample in samples:
        payload = sample.to_dict()
        assert isinstance(payload, dict)
        assert payload
