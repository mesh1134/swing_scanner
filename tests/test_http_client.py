import io
import json
import unittest
from unittest.mock import patch
from urllib import error

from swing_scanner.http_client import RetryPolicy, post_json


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HttpClientTests(unittest.TestCase):
    def test_retries_429_then_succeeds(self):
        attempts = {"count": 0}

        def fake_urlopen(req, timeout=20):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise error.HTTPError(req.full_url, 429, "rate limited", None, io.BytesIO(b""))
            return _FakeResponse({"ok": True})

        with patch("swing_scanner.http_client.request.urlopen", side_effect=fake_urlopen):
            data = post_json(
                "https://example.com",
                {"hello": "world"},
                policy=RetryPolicy(max_attempts=4, backoff_base_seconds=0.001, backoff_max_seconds=0.002),
            )
        self.assertTrue(data["ok"])
        self.assertEqual(attempts["count"], 3)


if __name__ == "__main__":
    unittest.main()
