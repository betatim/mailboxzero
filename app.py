import asyncio
import hashlib
import json
import logging
import mailbox
import os

from functools import partial

import tornado
import tornado.options
from tornado.web import RequestHandler, HTTPError
from tornado.log import app_log

from aiosmtpd.smtp import SMTP as SMTPServer
from aiosmtpd.handlers import Debugging, Message, COMMASPACE


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


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/api", PingHandler),
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

        if not address.endswith("@example.com"):
            return "550 not relaying to that domain"

        envelope.rcpt_tos.append(address)
        return "250 OK"

    def handle_message(self, message):
        for recipient in message["X-RcptTo"].split(COMMASPACE):
            mail_dir = os.path.join(self.base_maildir, adddress_to_path(recipient))
            mbox = mailbox.Maildir(mail_dir)
            mbox.add(message)


def main():
    os.makedirs("/tmp/mb0", exist_ok=True)
    tornado.options.parse_command_line()
    logging.getLogger().setLevel(logging.DEBUG)
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(8880)

    loop = asyncio.get_event_loop()

    coro = loop.create_server(
        partial(
            SMTPServer,
            Mailbox0("/tmp/mb0"),
            enable_SMTPUTF8=True,
            hostname="mb0.wtte.ch",
        ),
        "0.0.0.0",
        25,
    )
    server = loop.run_until_complete(coro)

    loop.run_forever()
    # tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
