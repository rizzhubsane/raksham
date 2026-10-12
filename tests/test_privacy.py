"""Log redaction."""

from deckeval.privacy import public_error


def test_public_error_strips_email_and_url():
    exc = RuntimeError(
        "failed for ada@example.com at https://cdn.example.com/deck.pptx?sig=secret-token"
    )
    text = public_error(exc)
    assert "ada@example.com" not in text
    assert "https://" not in text
    assert "secret-token" not in text
    assert "RuntimeError" in text
