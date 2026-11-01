from types import SimpleNamespace

import pytest
import requests

from bot import telegram


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN-SECRETO")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")


def test_split_message_respects_limit():
    text = "\n".join(["x" * 100] * 100)
    chunks = telegram.split_message(text, limit=1000)
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "\n".join(chunks).count("x") == 100 * 100


def test_split_message_cuts_giant_line():
    assert telegram.split_message("hola\n" + "x" * 25, limit=10) == ["hola", "x" * 10, "x" * 10, "x" * 5]


def test_send_posts_every_chunk(monkeypatch, credentials):
    sent = []

    def fake_post(url, json, timeout):
        sent.append(json)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    telegram.send("\n".join(["x" * 3000] * 2))
    assert len(sent) == 2
    assert sent[0]["chat_id"] == "123"


@pytest.mark.parametrize(
    ("response", "expected"),
    [(SimpleNamespace(status_code=401), "401"), (None, "sin respuesta")],
)
def test_send_error_never_exposes_the_token(monkeypatch, credentials, response, expected):
    def fake_post(url, json, timeout):
        raise requests.RequestException(f"error en {url}", response=response)

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    with pytest.raises(telegram.TelegramError) as error:
        telegram.send("hola")
    assert expected in str(error.value)
    assert "TOKEN-SECRETO" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


def test_html_is_sent_with_parse_mode(monkeypatch, credentials):
    sent = []

    def fake_post(url, json, timeout):
        sent.append(json)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    telegram.send("<b>hola</b>", html=True)
    assert sent[0]["parse_mode"] == "HTML"


def test_rejected_html_falls_back_to_plain_text(monkeypatch, credentials):
    sent = []

    def fake_post(url, json, timeout):
        sent.append(json)
        if "parse_mode" in json:
            raise requests.HTTPError("400", response=SimpleNamespace(status_code=400))
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    telegram.send("<b>S&amp;P</b> <i>baja</i>", html=True)
    assert sent[-1]["text"] == "S&P baja"
    assert "parse_mode" not in sent[-1]


def test_other_http_errors_do_not_retry(monkeypatch, credentials):
    sent = []

    def fake_post(url, json, timeout):
        sent.append(json)
        raise requests.HTTPError("401", response=SimpleNamespace(status_code=401))

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    with pytest.raises(telegram.TelegramError, match="401"):
        telegram.send("<b>hola</b>", html=True)
    assert len(sent) == 1
