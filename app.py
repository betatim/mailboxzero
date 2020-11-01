import asyncio
import email
import email.policy
import hashlib
import json
import logging
import mailbox
import os
import random
import time

from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from functools import partial

import tornado
import tornado.options
from tornado.ioloop import IOLoop
from tornado.log import app_log
from tornado.web import RequestHandler, HTTPError

from aiosmtpd.smtp import SMTP as SMTPServer
from aiosmtpd.handlers import Message, COMMASPACE


CONFIG = {"base_dir": "/tmp/mb0", "gc_interval": 180}
# configuration per domain for which we will accept emails
DOMAINS = {"mb0.wtte.ch": {"max_email_age": 600}}


def remove_old_email(domain, max_age):
    """Remove old emails for a given domain"""
    app_log.info(f"Checking {domain} for old email")
    try:
        base_maildir = CONFIG["base_dir"]
        maildir = os.path.join(base_maildir, domain)

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
            (1 + jitter) * DOMAINS[domain].get("gc_interval", CONFIG["gc_interval"]),
            remove_old_email,
            domain,
            max_age,
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
            app_log.error("%s: %s", header, value)
        self.finish("pong")


class MailBoxHandler(BaseAPIHandler):
    def initialize(self, base_maildir):
        self.base_maildir = base_maildir

    async def get(self, address):
        mail_dir = os.path.join(self.base_maildir, adddress_to_path(address))

        if not os.path.exists(mail_dir):
            self.write({"emails": []})
            return

        mbox = mailbox.Maildir(mail_dir)
        self.write({"emails": sorted(mbox.keys())})


class EMailHandler(BaseAPIHandler):
    def initialize(self, base_maildir):
        self.base_maildir = base_maildir

    async def get(self, address, message_id):
        mail_dir = os.path.join(self.base_maildir, adddress_to_path(address))

        if not os.path.exists(mail_dir):
            self.set_status(404)
            self.write({"message": "This mailbox doesn't exist."})
            return

        mbox = mailbox.Maildir(mail_dir)
        if message_id not in mbox:
            self.set_status(404)
            self.write({"message": "This email doesn't exist."})
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
                    "content": richest.get_content(),
                    "content-type": richest.get_content_type(),
                }
        elif richest["content-type"].content_type == "multipart/related":
            richest_body = {
                "content": richest.get_body(preferencelist=("html",)).get_content(),
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

        date = parsedate_to_datetime(message["date"])
        if date.tzinfo is None:
            date = date.isoformat() + "+00:00"
        else:
            date = date.isoformat()

        self.write(
            {
                "richestBody": richest_body,
                "simplestBody": simplest_body,
                "subject": message["subject"],
                "date": date,
                "from": message["from"],
                "x-mailfrom": message["x-mailfrom"],
            }
        )


class Application(tornado.web.Application):
    def __init__(self, base_maildir):
        options = {"base_maildir": base_maildir}
        handlers = [
            (r"/api", PingHandler),
            (r"/api/([^/]+)", MailBoxHandler, options),
            (r"/api/([^/]+)/([^/]+)", EMailHandler, options),
        ]

        settings = dict(debug=True)
        tornado.web.Application.__init__(self, handlers, **settings)


def adddress_to_path(address):
    # XXX maybe remove the "plus" part of the address?
    return hashlib.sha1(address.lower().strip().encode()).hexdigest()


class Mailbox0(Message):
    def __init__(self, base_maildir, message_class=None):
        self.base_maildir = base_maildir
        super().__init__(message_class)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        address = address.lower()

        if not any(address.endswith(f"@{domain}") for domain in DOMAINS.keys()):
            return "550 not relaying to that domain"

        envelope.rcpt_tos.append(address)
        return "250 OK"

    def handle_message(self, message):
        for recipient in message["X-RcptTo"].split(COMMASPACE):
            local, _, domain = recipient.partition("@")
            mail_dir = os.path.join(
                self.base_maildir, domain, adddress_to_path(recipient)
            )
            mbox = mailbox.Maildir(mail_dir)
            mbox.add(message)


def main():
    base_maildir = CONFIG["base_dir"]

    # Setup mailbox directories for all the domains we handle
    for domain in DOMAINS:
        os.makedirs(os.path.join(base_maildir, domain), exist_ok=True)

    tornado.options.parse_command_line()
    logging.getLogger().setLevel(logging.DEBUG)

    http_server = tornado.httpserver.HTTPServer(Application(base_maildir))
    http_server.listen(8880)

    loop = asyncio.get_event_loop()

    coro = loop.create_server(
        partial(
            SMTPServer,
            Mailbox0(base_maildir),
            enable_SMTPUTF8=True,
            hostname="mail.mb0.wtte.ch",
        ),
        "0.0.0.0",
        25,
    )
    server = loop.run_until_complete(coro)

    for domain, config in DOMAINS.items():
        IOLoop.current().call_later(
            config.get("gc_interval", CONFIG["gc_interval"]),
            remove_old_email,
            domain,
            config["max_email_age"],
        )

    loop.run_forever()


if __name__ == "__main__":
    main()
