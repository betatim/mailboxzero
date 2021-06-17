import argparse
import asyncio
import email
import email.policy
import html
import json
import logging
import mailbox
import os
import pathlib
import random
import string
import time

from email.message import EmailMessage

from functools import partial

from textwrap import dedent

import bleach

import tornado
import tornado.options
from tornado.ioloop import IOLoop
from tornado.log import app_log
from tornado.web import RequestHandler, HTTPError

from aiosmtpd.smtp import SMTP as SMTPServer
from aiosmtpd.handlers import COMMASPACE

from urlextract import URLExtract

from . import services
from . import utils


HERE = pathlib.Path(__file__).parent.absolute()


def remove_old_email(domain, max_age, base_maildir, gc_interval):
    """Remove old emails for a given domain"""
    app_log.info(f"Cleaning up old email for {domain}")
    try:
        maildir = os.path.join(base_maildir, utils.domain_to_path(domain))
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


class WelcomeHandler(RequestHandler):
    def get(self):
        email = self.get_argument("email", default="")
        if email:
            self.redirect(f"/view/{email}/")

        else:
            self.render("welcome.html")


class BaseHandler(RequestHandler):
    @property
    def base_maildir(self):
        return self.settings["base_maildir"]

    @property
    def url_extractor(self):
        return self.settings["url_extractor"]

    def force_trailing_slash(self):
        if not self.request.uri.endswith("/"):
            self.redirect(self.request.uri + "/", status=301)
            raise tornado.web.Finish()


class ViewMailBoxHandler(BaseHandler):
    def get(self, address):
        self.force_trailing_slash()

        mailboxes = services.Mailboxes(self.base_maildir)
        emails = mailboxes.email_ids(address)

        self.render("mailbox.html", email_ids=emails, address=address)


class ViewEMailHandler(BaseHandler):
    def get(self, address, message_id):
        mailboxes = services.Mailboxes(self.base_maildir)

        error_message = {"message": "This email doesn't exist."}

        if not mailboxes.exists(address):
            self.set_status(404)
            self.write(error_message)
            return

        mbox = mailboxes.mbox(address)
        if message_id not in mbox:
            self.set_status(404)
            self.write(error_message)
            return

        message = mailboxes.get_message(address, message_id)
        attachments = mailboxes.get_attachment_summaries(address, message_id)

        content_base_url = f"/content/{address}/{message_id}/"

        if message["richestBody"]["content-type"] == "text/html":

            message_html = utils.rewrite_html(
                message["richestBody"]["content"], content_base_url
            )

        else:
            message_html = bleach.linkify(
                bleach.clean(message["richestBody"]["content"], strip=True)
            )

        escaped_message = html.escape(message_html)

        # Try and make loading untrusted content from the email a little less
        # risky and private
        self.set_header("Referrer-Policy", "no-referrer")
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("X-XSS-Protection", "1; mode=block")

        self.render(
            "email.html",
            subject=message["subject"],
            raw_message_html=escaped_message,
            content_base_url=content_base_url,
            attachments=attachments,
        )


class ContentHandler(BaseHandler):
    async def get(self, address, message_id, content_id):
        """Serve content from message_id referred to by content_id"""
        mailboxes = services.Mailboxes(self.base_maildir)

        # if the client has an etag they must have visited before and the
        # content won't have changed for the same message_id and content_id
        # so we can take a shortcut here and reply "not modified"
        if "If-None-Match" in self.request.headers:
            self.set_status(304)
            return

        content = mailboxes.get_content(address, message_id, content_id)
        if content is None:
            self.set_status(404)
            self.write({"message": "Content does not exist."})
            return

        self.set_header("cache-control", "public, max-age=0, must-revalidate")
        self.set_header("age", "0")
        self.set_header("content-type", content.get_content_type())
        self.write(content.get_content())


class BaseAPIHandler(BaseHandler):
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
    async def get(self, address):
        mailboxes = services.Mailboxes(self.base_maildir)
        emails = mailboxes.email_ids(address)

        self.write({"emails": emails})


class EMailHandler(BaseAPIHandler):
    def add_urls(self, body):
        """Add list of URLs parsed from the body to the object"""
        urls = self.url_extractor.find_urls(body["content"])
        body["urls"] = urls

    async def get(self, address, message_id):
        mailboxes = services.Mailboxes(self.base_maildir)

        error_message = {"message": "This email doesn't exist."}

        if not mailboxes.exists(address):
            self.set_status(404)
            self.write(error_message)
            return

        mbox = mailboxes.mbox(address)
        if message_id not in mbox:
            self.set_status(404)
            self.write(error_message)
            return

        message = mailboxes.get_message(address, message_id)
        for body in (message["richestBody"], message["simplestBody"]):
            self.add_urls(body)

        self.write(message)


class WebApplication(tornado.web.Application):
    def __init__(self, base_maildir, debug=False):
        handlers = [
            (r"/", WelcomeHandler),
            (r"/api", PingHandler),
            (r"/api/([^/]+)", MailBoxHandler),
            (r"/api/([^/]+)/([^/]+)", EMailHandler),
            (r"/view/([^/]+)/?", ViewMailBoxHandler),
            (r"/view/([^/]+)/([^/]+)", ViewEMailHandler),
            (r"/content/([^/]+)/([^/]+)/([^/]+)", ContentHandler),
        ]

        # This performs network I/O when instantiated so we start it once
        # at the very begining and then keep a reference to it instead of
        # creating a new instance each time we need it
        url_extractor = URLExtract()

        settings = dict(
            base_maildir=base_maildir,
            debug=debug,
            url_extractor=url_extractor,
            template_path=os.path.join(HERE, "templates"),
            static_path=os.path.join(HERE, "static"),
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


def generate_id():
    return "".join(
        [random.choice(string.ascii_lowercase + string.digits) for _ in range(8)]
    )


def ensure_attachment_cids(message):
    """Ensure that every attachment has a Content-ID header

    We use the value of the Content-ID to refer to an attachment in download
    links so we need every attachment to have one.
    """
    for attachment in message.iter_attachments():
        if attachment.get_content_disposition() == "attachment":
            if "content-id" not in attachment:
                cid = generate_id()
                attachment["content-id"] = f"<{cid}>"


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
        ensure_attachment_cids(message)

        for recipient in message["X-RcptTo"].split(COMMASPACE):
            mail_dir = os.path.join(
                self.base_maildir, utils.adddress_to_path(recipient)
            )
            mbox = mailbox.Maildir(mail_dir)
            mbox.add(message)


# configuration per domain for which we will accept emails
_DEFAULT_DOMAINS = {
    "mb0.wtte.ch": {"max_email_age": 600},
    "qmq.ch": {"max_email_age": 600},
}


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
        os.makedirs(
            os.path.join(base_maildir, utils.domain_to_path(domain)), exist_ok=True
        )

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
