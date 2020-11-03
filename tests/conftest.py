import email
import inspect
import os
import pathlib
import socket
import tempfile

from email.policy import default

import pytest

from aiosmtplib import SMTP as SMTPClient

import mailboxzero
from mailboxzero import WebApplication


TESTS_HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))


def pytest_collection_modifyitems(items):
    """Add asyncio marker to all async tests"""
    for item in items:
        if inspect.iscoroutinefunction(item.obj):
            item.add_marker("asyncio")


def _random_port():
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def http_port():
    return _random_port()


@pytest.fixture
def smtp_port():
    return _random_port()


@pytest.fixture
def base_url(http_port):
    return f"http://127.0.0.1:{http_port}/api"


@pytest.fixture
async def smtp_client(smtp_port):
    client = SMTPClient(source_address="localhost")
    await client.connect(hostname="localhost", port=smtp_port)

    yield client

    await client.quit()


@pytest.fixture
def web_app():
    with tempfile.TemporaryDirectory() as d:
        print(f"Using {d} as mailbox directory")
        app = WebApplication(d)
        yield app


@pytest.fixture
def mailbox_server(request, event_loop, http_port, smtp_port):
    with tempfile.TemporaryDirectory() as d:
        mailboxzero.start_all(base_maildir=d, http_port=http_port, smtp_port=smtp_port)
        yield


@pytest.fixture
def large_email():
    """A large email with several images as attachments"""
    with open(TESTS_HERE / "data/1604232551.M582355P21675Q3.hubhero-demo", "rb") as fp:
        msg = email.message_from_binary_file(fp, policy=default)

    yield msg


xxx = """
@pytest.fixture
def http_server(request, web_app, event_loop, http_port):
    ""Start a mailboxzero HTTP server""

    print("HTTP port:", http_port)

    server = tornado.httpserver.HTTPServer(app)
    # server.add_socket(http_port[0])
    server.listen(http_port)

    def _stop():
        server.stop()

        if hasattr(server, "close_all_connections"):
            event_loop.run_until_complete(server.close_all_connections())

    request.addfinalizer(_stop)
    return server


@pytest.fixture
def smtp_server(request, event_loop, smtp_port):
    print("SMTP port:", smtp_port)"""
