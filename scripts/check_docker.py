"""Check the running Compose stack through the frontend's API proxy."""

import argparse
import json
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    base = parser.parse_args().url.rstrip("/")
    with urlopen(base, timeout=30) as response:
        if response.status != 200 or b"ScholarGraph" not in response.read():
            raise RuntimeError("Frontend did not serve ScholarGraph")
    for path in ("/api/health", "/api/status", "/api/papers?limit=1", "/api/graph"):
        with urlopen(base + path, timeout=30) as response:
            body = json.load(response)
        if path == "/api/status" and body["storage"] != "postgresql":
            raise RuntimeError("Compose backend must use PostgreSQL")
        if path == "/api/health" and body["status"] != "ok":
            raise RuntimeError("API health check failed")
        print(f"PASS {path}")
    print("Frontend, API proxy, database and graph schema are reachable.")


if __name__ == "__main__":
    main()
