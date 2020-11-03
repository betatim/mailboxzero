import pytest

import aiosmtplib
from aiosmtplib import SMTP as SMTPClient

import mailboxzero


async def test_smtp_is_alive(mailbox_server, smtp_port):
    # test the SMTP server is alive
    client = SMTPClient(source_address="localhost")
    await client.connect(hostname="localhost", port=smtp_port)

    await client.noop()
    r = await client.ehlo()

    assert r.code == 250
    assert "SMTPUTF8" in r.message

    await client.quit()


async def test_smtp_rcpt(mailbox_server, smtp_client):
    await smtp_client.mail("someone@remote.example.com")

    # check we get a positive response for a domain the server handles
    r = await smtp_client.rcpt("someone@mb0.wtte.ch")
    assert r.code == 250

    # check we get a negative response for a domain the server doesn't handle
    with pytest.raises(aiosmtplib.errors.SMTPRecipientRefused):
        await smtp_client.rcpt("someone@not-mb0.wtte.ch")


def test_replace_large_parts(large_email):
    mailboxzero.replace_large_parts(large_email)

    expected_structure = [
        "multipart/mixed",
        "multipart/alternative",
        "text/plain",
        "text/html",
        # this image is smaller than the limit so it survives
        "image/jpeg",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
        "text/plain",
    ]
    actual_structure = [p.get_content_type() for p in large_email.walk()]
    assert actual_structure == expected_structure
