import argparse
import asyncio
import email
import email.policy
import hashlib
import html
import json
import logging
import mailbox
import os
import random
import time

from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from functools import partial

from textwrap import dedent

import tornado
import tornado.options
from tornado.ioloop import IOLoop
from tornado.log import app_log
from tornado.web import RequestHandler, HTTPError

from aiosmtpd.smtp import SMTP as SMTPServer
from aiosmtpd.handlers import COMMASPACE

from urlextract import URLExtract


def domain_to_path(domain):
    return hashlib.sha1(domain.lower().strip().encode()).hexdigest()


def adddress_to_path(address):
    # XXX maybe remove the "plus" part of the local address?
    local, _, domain = address.partition("@")
    return os.path.join(
        domain_to_path(domain),
        hashlib.sha1(address.lower().strip().encode()).hexdigest(),
    )


def remove_old_email(domain, max_age, base_maildir, gc_interval):
    """Remove old emails for a given domain"""
    app_log.info(f"Cleaning up old email for {domain}")
    try:
        maildir = os.path.join(base_maildir, domain_to_path(domain))
        app_log.debug(f"Checking {maildir} ...")

        now = time.time()

        for entry in os.listdir(maildir):
            mbox = mailbox.Maildir(os.path.join(maildir, entry))

            for msg_id in mbox.keys():
                ts, _ = msg_id.split(".", maxsplit=1)
                ts = int(ts)
                if now - max_age > ts:
                    mbox.discard(msg_id)

    finally:
        jitter = 0.3 * (0.5 - random.random())
        IOLoop.current().call_later(
            (1 + jitter) * gc_interval,
            remove_old_email,
            domain,
            max_age,
            base_maildir,
            gc_interval,
        )


class BaseAPIHandler(RequestHandler):
    def get_json_body(self):
        """Return the body of the request as JSON data."""
        if not self.request.body:
            return None
        body = self.request.body.strip().decode("utf-8")
        try:
            model = json.loads(body)
        except Exception:
            app_log.debug("Bad JSON: %r", body)
            app_log.error("Couldn't parse JSON", exc_info=True)
            raise HTTPError(400, "Invalid JSON in body of request")
        return model

    def options(self):
        self.set_status(204)
        self.finish()


class PingHandler(BaseAPIHandler):
    async def get(self):
        for header, value in self.request.headers.items():
            app_log.info("%s: %s", header, value)
        self.finish("pong")


class MailBoxHandler(BaseAPIHandler):
    @property
    def base_maildir(self):
        return self.settings["base_maildir"]

    async def get(self, address):
        mail_dir = os.path.join(self.base_maildir, adddress_to_path(address))

        app_log.debug("debug mailbox message")
        app_log.info("info mailbox message")
        app_log.error("error mailbox message")

        if not os.path.exists(mail_dir):
            self.write({"emails": []})
            return

        mbox = mailbox.Maildir(mail_dir)
        self.write({"emails": sorted(mbox.keys())})


class EMailHandler(BaseAPIHandler):
    @property
    def base_maildir(self):
        return self.settings["base_maildir"]

    @property
    def url_extractor(self):
        return self.settings["url_extractor"]

    def add_urls(self, body):
        """Add list of URLs parsed from the body to the object"""
        urls = self.url_extractor.find_urls(body["content"])
        body["urls"] = urls

    async def get(self, address, message_id):
        error_message = {"message": "This email doesn't exist."}
        mail_dir = os.path.join(self.base_maildir, adddress_to_path(address))

        if not os.path.exists(mail_dir):
            self.set_status(404)
            self.write(error_message)
            return

        mbox = mailbox.Maildir(mail_dir)
        if message_id not in mbox:
            self.set_status(404)
            self.write(error_message)
            return

        mdir_msg = mbox.get_message(message_id)
        message = email.message_from_bytes(
            mdir_msg.as_bytes(), _class=EmailMessage, policy=email.policy.default
        )

        richest = message.get_body()
        if richest["content-type"].maintype == "text":
            if richest["content-type"].subtype == "plain":
                richest_body = {
                    "content": "\n".join(
                        line for line in richest.get_content().splitlines()
                    ),
                    "content-type": richest.get_content_type(),
                }

            elif richest["content-type"].subtype == "html":
                richest_body = {
                    "content": html.unescape(richest.get_content()),
                    "content-type": richest.get_content_type(),
                }
        elif richest["content-type"].content_type == "multipart/related":
            richest_body = {
                "content": html.unescape(
                    richest.get_body(preferencelist=("html",)).get_content()
                ),
                "content-type": "text/html",
            }
        else:
            richest_body = {
                "content": "Don't know how to display {}".format(
                    richest.get_content_type()
                ),
                "content-type": "text/plain",
            }

        simplest = message.get_body(preferencelist=("plain", "html"))
        simplest_body = {
            "content": "".join(simplest.get_content().splitlines(keepends=True)),
            "content-type": simplest.get_content_type(),
        }
        if simplest_body["content-type"] == "text/html":
            simplest_body["content"] = html.unescape(simplest_body["content"])

        date = parsedate_to_datetime(message["date"])
        if date.tzinfo is None:
            date = date.isoformat() + "+00:00"
        else:
            date = date.isoformat()

        for body in (richest_body, simplest_body):
            self.add_urls(body)

        self.write(
            {
                "richestBody": richest_body,
                "simplestBody": simplest_body,
                "subject": message["subject"],
                "date": date,
                "from": message["from"],
                "x-mailfrom": message["x-mailfrom"],
                "headers": [(k, v) for k, v in message.items()],
            }
        )


class WebApplication(tornado.web.Application):
    def __init__(self, base_maildir, debug=False):
        handlers = [
            (r"/api", PingHandler),
            (r"/api/([^/]+)", MailBoxHandler),
            (r"/api/([^/]+)/([^/]+)", EMailHandler),
        ]

        url_extractor = URLExtract()

        settings = dict(
            base_maildir=base_maildir, debug=debug, url_extractor=url_extractor
        )
        tornado.web.Application.__init__(self, handlers, **settings)


def replace_large_parts(message, limit=1024 * 1024):
    """Replace large MIME parts of the message with a placeholder"""
    replacement = """
    This was a MIME part that was replaced by this placeholder because of its
    size of {size} bytes.

    The original headers follow.

    {headers}
    """
    replacement = dedent(replacement).lstrip()

    for part in message.walk():
        # we can't get the size of a multipart message
        # which means we first need to check for that
        if not part.is_multipart():
            size = len(part.get_content())
            if size > limit:
                part.set_content(
                    replacement.format(
                        size=size,
                        content_type=part.get_content_type(),
                        headers="\n".join(f"{k}: {v}" for k, v in part.items()),
                    )
                )


# Our own copy of aiosmtpd.handlers.Message so we can set the policy
class _Message:
    def __init__(self, message_class=None):
        self.message_class = EmailMessage

    async def handle_DATA(self, server, session, envelope):
        envelope = self.prepare_message(session, envelope)
        self.handle_message(envelope)
        return "250 OK"

    def prepare_message(self, session, envelope):
        # If the server was created with decode_data True, then data will be a
        # str, otherwise it will be bytes.
        data = envelope.content
        if isinstance(data, bytes):
            message = email.message_from_bytes(
                data, self.message_class, policy=email.policy.default
            )
        else:
            assert isinstance(data, str), "Expected str or bytes, got {}".format(
                type(data)
            )
            message = email.message_from_string(
                data, self.message_class, policy=email.policy.default
            )
        message["X-Peer"] = str(session.peer)
        message["X-MailFrom"] = envelope.mail_from
        message["X-RcptTo"] = COMMASPACE.join(envelope.rcpt_tos)
        return message

    def handle_message(self, message):
        raise NotImplementedError


class SMTPMailboxHandler(_Message):
    def __init__(self, base_maildir, domains, message_class=None):
        self.base_maildir = base_maildir
        self.domains = domains
        super().__init__(message_class)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        address = address.lower()

        if not any(address.endswith(f"@{domain}") for domain in self.domains.keys()):
            return "550 not relaying to that domain"

        envelope.rcpt_tos.append(address)
        return "250 OK"

    def handle_message(self, message):
        replace_large_parts(message)

        for recipient in message["X-RcptTo"].split(COMMASPACE):
            mail_dir = os.path.join(self.base_maildir, adddress_to_path(recipient))
            mbox = mailbox.Maildir(mail_dir)
            mbox.add(message)


# configuration per domain for which we will accept emails
_DEFAULT_DOMAINS = {"mb0.wtte.ch": {"max_email_age": 600}}


def start_all(
    base_maildir="/tmp/mb0",
    gc_interval=180,
    debug=False,
    http_port=8880,
    smtp_port=25,
    domains=_DEFAULT_DOMAINS,
):
    # Setup mailbox directories for all the domains we handle
    for domain in domains:
        os.makedirs(os.path.join(base_maildir, domain_to_path(domain)), exist_ok=True)

    tornado.log.enable_pretty_logging()
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    http_server = tornado.httpserver.HTTPServer(
        WebApplication(base_maildir, debug=debug)
    )
    http_server.listen(http_port)

    loop = asyncio.get_event_loop()

    coro = loop.create_server(
        partial(
            SMTPServer,
            SMTPMailboxHandler(base_maildir, domains, message_class=EmailMessage),
            enable_SMTPUTF8=True,
            hostname="mail.mb0.wtte.ch",
        ),
        "0.0.0.0",
        smtp_port,
    )
    loop.run_until_complete(coro)

    for domain, config in domains.items():
        IOLoop.current().call_later(
            config.get("gc_interval", gc_interval),
            remove_old_email,
            domain,
            config["max_email_age"],
            base_maildir,
            gc_interval,
        )


def get_argparser():
    parser = argparse.ArgumentParser(
        description="Mailbox Zero - get to Inbox Zero by creating a new inbox"
    )
    parser.add_argument(
        "--debug", help="Enable debug mode", action="store_true", default=False
    )
    return parser


def main():
    parser = get_argparser()
    args = parser.parse_args()

    start_all(debug=args.debug)

    loop = asyncio.get_event_loop()
    loop.run_forever()
