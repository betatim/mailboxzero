import email
import email.policy
import html
import mailbox
import os

from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from . import utils


class Mailboxes:
    def __init__(self, base_maildir):
        # Path at which we can find all the domains we host
        self.base_maildir = base_maildir

    def mail_dir_for(self, address):
        mail_dir = os.path.join(self.base_maildir, utils.adddress_to_path(address))
        return mail_dir

    def exists(self, address):
        """Determine if a mailbox for address exists"""
        mail_dir = self.mail_dir_for(address)
        return os.path.exists(mail_dir)

    def mbox(self, address):
        """Get the mailbox for address"""
        return mailbox.Maildir(self.mail_dir_for(address))

    def _get_email(self, address, message_id):
        mbox = self.mbox(address)

        mdir_msg = mbox.get_message(message_id)
        message = email.message_from_bytes(
            mdir_msg.as_bytes(), _class=EmailMessage, policy=email.policy.default
        )
        return message

    def get_content(self, address, message_id, content_id):
        """Extract MIME part labelled with content_id"""
        content_id = f"<{content_id}>"
        message = self._get_email(address, message_id)
        for part in message.walk():
            if part.get("content-id") == content_id:
                return part

    def get_attachment_summaries(self, address, message_id):
        """Get summary information about the attachments of this email"""
        message = self._get_email(address, message_id)
        attachments = []
        for attachment in message.iter_attachments():
            if attachment.get_content_disposition() == "attachment":
                attachments.append(
                    {
                        "content-type": attachment.get_content_type(),
                        "fname": attachment.get_filename(),
                        "size": len(attachment.get_content()),
                        "cid": attachment["content-id"][1:-1],
                    }
                )

        return attachments

    def get_message(self, address, message_id):
        """Extract and parse message"""
        message = self._get_email(address, message_id)

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
