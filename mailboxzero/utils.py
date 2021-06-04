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


def rewrite_html(html_document, content_url):
    """Rewrite input HTML to make it more privacy friendly"""
    soup = BeautifulSoup(html_document, "html.parser")

    for node in soup.find_all(["a"]):
        node["target"] = "_blank"

    for img in soup.find_all(["img"]):
        img["loading"] = "lazy"
        img["decoding"] = "async"

        if img["src"].startswith("cid:"):
            img["src"] = content_url + img["src"][4:]

    # Setting this leads to images not loading because of missing CORS headers
    # in the response from the server we fetch them from
    # for node in soup.find_all(["link", "audio", "img", "script", "video"]):
    #    node['crossorigin'] = 'anonymous'

    bs_style = soup.new_tag(
        "link",
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0-beta3/dist/css/bootstrap.min.css",
        rel="stylesheet",
        integrity="sha384-eOJMYsd53ii+scO/bJGFsiCZc+5NDVN2yr8+0RDqr0Ql0h+rP48ckxlpbzKgwra6",
        crossorigin="anonymous",
    )
    """<meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">"""
    #viewport = soup.new_tag("meta", name="viewport")

    if soup.head is None:
        print("adding head tag")
        soup.insert(0, soup.new_tag("head"))

    soup.head.insert(0, bs_style)

    return soup.decode(formatter=None)
