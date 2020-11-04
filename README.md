# Mailbox Zero

> Can't reach Inbox Zero? Just create a new one.

MailboxZero is a server that provides you an infinite number of mailboxes that
you can check via a REST API.

It combines a SMTP server that accepts incoming emails and a web server that
provides access to the emails over a REST API.


## How to use it

> mb0.wtte.ch is a demo instance of MailboxZero

1. Send an email to `somerandomstring@mb0.wtte.ch`
1. Visit http://mb0.wtte.ch:8880/api/somerandomstring@mb0.wtte.ch for a list
   of messages in your mailbox
1. Retrieve an individual message by visiting `http://mb0.wtte.ch:8880/api/somerandomstring@mb0.wtte.ch/<messageID>`

Messages get deleted about ten minutes after arriving. You get a parsed version
of the email, not the raw email. MailboxZero will show you:

* the richest body, usually the HTML version
* the simplest body, usually the plain text version
* the URLs in each body
* the headers of the email as a list of `(name, value)` pairs
* the subject, from and date fields


## Deploying your own instance

Quick start:

1. Install Python 3.8 or newer
1. Install MailboxZero `pip install -U mailboxzero`
1. Run `mailboxzero` as `root`.

To run an instance reachable from the public internet you need a public IP,
assign a hostname to it, and setup a MX record to point to that hostname. You
should also use something like systemd to run MailboxZero in order to limit its
privileges and not run it as `root`.


## Development

Setup the development dependencies with `python -m pip install -U -r dev-requirements.txt`.
We use `pytest` to run the tests in `tests/`.

Main libraries used:
* [aiosmtpd](https://aiosmtpd.readthedocs.io/en/latest)
* [tornado](https://www.tornadoweb.org/en/stable/)
