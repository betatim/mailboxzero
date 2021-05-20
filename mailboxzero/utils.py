import hashlib
import os

from bs4 import BeautifulSoup


def domain_to_path(domain):
    return hashlib.sha1(domain.lower().strip().encode()).hexdigest()


def adddress_to_path(address):
    # XXX maybe remove the "plus" part of the local address?
    local, _, domain = address.partition("@")
    return os.path.join(
        domain_to_path(domain),
        hashlib.sha1(address.lower().strip().encode()).hexdigest(),
    )


def rewrite_html(html_document):
    """Rewrite input HTML to make it more privacy friendly"""
    soup = BeautifulSoup(html_document, "html.parser")

    for node in soup.find_all(["a"]):
        node["target"] = "_blank"

    # Setting this leads to images not loading because of missing CORS headers
    # in the response from the server we fetch them from
    # for node in soup.find_all(["link", "audio", "img", "script", "video"]):
    #    node['crossorigin'] = 'anonymous'

    return soup.decode(formatter=None)
