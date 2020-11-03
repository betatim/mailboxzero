import asyncio

from concurrent.futures import ThreadPoolExecutor

import requests


# From JupyterHub, BSD3 license
class _AsyncRequests:
    """Wrapper around requests to return a Future from request methods
    A single thread is allocated to avoid blocking the IOLoop thread.
    """

    def __init__(self):
        self.executor = ThreadPoolExecutor(1)
        real_submit = self.executor.submit
        self.executor.submit = lambda *args, **kwargs: asyncio.wrap_future(
            real_submit(*args, **kwargs)
        )

    def __getattr__(self, name):
        requests_method = getattr(requests, name)
        return lambda *args, **kwargs: self.executor.submit(
            requests_method, *args, **kwargs
        )


async_requests = _AsyncRequests()
