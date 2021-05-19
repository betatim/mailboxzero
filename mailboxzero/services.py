import email
import email.policy
import html
import mailbox
import os

from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from . import utils


class Mailbox:
    def __init__(self, base_maildir):
        # Path at which we can find all the domains we host
        self.base_maildir = base_maildir

    def mail_dir_for(self, address):
        mail_dir = os.path.join(self.base_maildir, utils.adddress_to_path(address))
        return mail_dir

    def exists(self, address):
        """Determine if a mailbox for address exists"""
        mail_dir = self.mail_dir_for(address)
        print("Mail dir is:", mail_dir)

        return os.path.exists(mail_dir)

    def mbox(self, address):
        """Get the mailbox for address"""
        return mailbox.Maildir(self.mail_dir_for(address))

    def get_message(self, address, message_id):
        """Extract and parse message"""
        mbox = self.mbox(address)

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

        return {
            "richestBody": richest_body,
            "simplestBody": simplest_body,
            "subject": message["subject"],
            "date": date,
            "from": message["from"],
            "x-mailfrom": message["x-mailfrom"],
            "headers": [(k, v) for k, v in message.items()],
        }

    def email_ids(self, address):
        """Get list of email IDs for address, sorted by age"""
        mail_dir = self.mail_dir_for(address)

        if not os.path.exists(mail_dir):
            return []

        mbox = mailbox.Maildir(mail_dir)
        return list(sorted(mbox.keys()))
