import pytest

from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils import async_requests


async def test_web_is_alive(mailbox_server, base_url):
    # test the web server is alive
    r = await async_requests.get(base_url)
    assert r.status_code == 200


async def test_empty_mailbox(mailbox_server, base_url):
    # email addresses that have not (yet) received any mail should return a 200
    r = await async_requests.get(base_url + "/nomail@mb0.wtte.ch")

    assert r.status_code == 200
    assert r.json() == {"emails": []}


async def test_has_email(mailbox_server, base_url, smtp_client):
    message = EmailMessage()
    message["From"] = "someone@remote.example.com"
    message["To"] = "hasmail@mb0.wtte.ch"
    message["Subject"] = "Hello World!"
    message.set_content("You have mail!")

    await smtp_client.send_message(message)

    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch")
    assert r.status_code == 200
    data = r.json()
    assert len(data["emails"]) == 1

    # nomail still has no mail in their inbox
    r = await async_requests.get(base_url + "/nomail@mb0.wtte.ch")

    assert r.status_code == 200
    assert r.json() == {"emails": []}


async def test_get_plain_email(mailbox_server, base_url, smtp_client):
    content = "You have mail!"
    message = EmailMessage()
    message["date"] = "Mon, 14 May 1984 12:34:56 +0000"
    message["From"] = "someone@remote.example.com"
    message["To"] = "hasmail@mb0.wtte.ch"
    message["Subject"] = "Hello World!"
    message.set_content(content)

    await smtp_client.send_message(message)

    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch")
    r.raise_for_status()
    assert len(r.json()["emails"]) == 1

    emails = r.json()["emails"]
    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch/" + emails[0])
    r.raise_for_status()
    data = r.json()

    assert data["richestBody"]["content-type"] == "text/plain"
    assert data["richestBody"]["content"] == content

    assert data["simplestBody"]["content-type"] == "text/plain"
    assert data["simplestBody"]["content"] == content

    assert data["from"] == message["from"]
    assert data["subject"] == message["subject"]


async def test_get_html_email(mailbox_server, base_url, smtp_client):
    message = MIMEMultipart("alternative")
    message["date"] = "Mon, 14 May 1984 12:34:56 +0000"
    message["From"] = "someone@remote.example.com"
    message["To"] = "hasmail@mb0.wtte.ch"
    message["Subject"] = "Hello World!"

    message.attach(MIMEText("hello plain text", "plain", "utf-8"))
    message.attach(
        MIMEText("<html><body><h1>Hello HTML</h1></body></html>", "html", "utf-8")
    )

    await smtp_client.send_message(message)

    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch")
    r.raise_for_status()
    assert len(r.json()["emails"]) == 1

    emails = r.json()["emails"]
    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch/" + emails[0])
    r.raise_for_status()
    data = r.json()

    assert data["richestBody"]["content-type"] == "text/html"
    assert (
        data["richestBody"]["content"]
        == "<html><body><h1>Hello HTML</h1></body></html>"
    )

    assert data["simplestBody"]["content-type"] == "text/plain"
    assert data["simplestBody"]["content"] == "hello plain text"

    assert data["from"] == message["from"]
    assert data["subject"] == message["subject"]


async def test_two_emails(mailbox_server, base_url, smtp_client):
    # send two emails to the same mailbox
    message = EmailMessage()
    message["From"] = "someone@remote.example.com"
    message["To"] = "hasmail@mb0.wtte.ch"
    message["Subject"] = "Hello World One!"
    message["date"] = "Mon, 14 May 1984 12:34:56 +0000"
    message.set_content("You have mail one!")
    await smtp_client.send_message(message)

    # second email
    message.replace_header("date", "Mon, 14 May 1984 12:56:56 +0000")
    message.replace_header("Subject", "Hello World Two!")
    message.set_content("You have mail two!")
    await smtp_client.send_message(message)

    r = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch")
    assert r.status_code == 200
    data = r.json()
    email_ids = data["emails"]

    assert len(email_ids) == 2

    # email IDs should be sorted old to new
    r1 = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch/" + email_ids[0])
    r1.raise_for_status()
    data = r1.json()
    assert data["subject"] == "Hello World One!"

    r2 = await async_requests.get(base_url + "/hasmail@mb0.wtte.ch/" + email_ids[1])
    r2.raise_for_status()
    data = r2.json()
    assert data["subject"] == "Hello World Two!"

    # nomail still has no mail in their inbox
    r = await async_requests.get(base_url + "/nomail@mb0.wtte.ch")
    assert r.status_code == 200
    assert r.json() == {"emails": []}


async def test_three_recipients(mailbox_server, base_url, smtp_client):
    # send an email with two recipients and one CC'ed
    message = EmailMessage()
    message["From"] = "someone@remote.example.com"
    message["To"] = "hasmail1@mb0.wtte.ch, hasmail2@mb0.wtte.ch"
    message["cc"] = "hasmail3@mb0.wtte.ch"
    message["Subject"] = "Hello World!"
    message["date"] = "Mon, 14 May 1984 12:34:56 +0000"
    message.set_content("You have mail one!")
    await smtp_client.send_message(message)

    for recipient in (
        "hasmail1@mb0.wtte.ch",
        "hasmail2@mb0.wtte.ch",
        "hasmail3@mb0.wtte.ch",
    ):
        r = await async_requests.get(base_url + f"/{recipient}")
        assert r.status_code == 200
        data = r.json()
        email_ids = data["emails"]
        assert len(email_ids) == 1

        r1 = await async_requests.get(base_url + f"/{recipient}/{email_ids[0]}")
        r1.raise_for_status()
        data = r1.json()
        assert data["subject"] == "Hello World!"
