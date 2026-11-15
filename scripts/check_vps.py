"""Authenticated deployment monitor. Exit nonzero on auth, database or model failure."""

import argparse
import base64
import json
import os
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Unexpected redirect", headers, fp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTPS origin of your private instance")
    parser.add_argument("--allow-local-http", action="store_true")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    from urllib.parse import urlsplit

    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Pass an origin without credentials, a query or a fragment")
    if parsed.scheme != "https" and not (
        args.allow_local_http
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        parser.error("Use HTTPS; HTTP is allowed only for explicit local testing")
    opener = build_opener(NoRedirect)
    try:
        with opener.open(base + "/api/health", timeout=15):
            raise RuntimeError("Authentication is not enforced")
    except HTTPError as exc:
        if exc.code != 401:
            raise
    token = base64.b64encode(
        (os.environ["AUTH_USER"] + ":" + os.environ["AUTH_PASSWORD"]).encode()
    ).decode()
    for path in ("/api/health", "/api/ready", "/api/papers?limit=1"):
        request = Request(base + path, headers={"Authorization": "Basic " + token})
        with opener.open(request, timeout=15) as response:
            json.load(response)
        print("PASS", path)


if __name__ == "__main__":
    main()
