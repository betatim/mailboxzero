import hashlib
import os


def domain_to_path(domain):
    return hashlib.sha1(domain.lower().strip().encode()).hexdigest()


def adddress_to_path(address):
    # XXX maybe remove the "plus" part of the local address?
    local, _, domain = address.partition("@")
    return os.path.join(
        domain_to_path(domain),
        hashlib.sha1(address.lower().strip().encode()).hexdigest(),
    )
