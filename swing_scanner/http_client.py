from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    timeout_seconds: int = 20
    backoff_base_seconds: float = 0.6
    backoff_max_seconds: float = 8.0
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)


class HttpRequestError(RuntimeError):
    pass


def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    active_policy = policy or RetryPolicy()
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body = json.dumps(payload).encode("utf-8")
    return _execute_with_retry(url, body, req_headers, active_policy)


def post_form(
    url: str,
    payload: bytes,
    headers: dict[str, str] | None = None,
    policy: RetryPolicy | None = None,
) -> dict[str, Any]:
    active_policy = policy or RetryPolicy()
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_headers.update(headers)
    return _execute_with_retry(url, payload, req_headers, active_policy)


def _execute_with_retry(
    url: str,
    payload: bytes,
    headers: dict[str, str],
    policy: RetryPolicy,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        req = request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=policy.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            return json.loads(raw)
        except error.HTTPError as exc:
            last_error = exc
            if exc.code not in policy.retryable_status_codes or attempt == policy.max_attempts:
                break
        except (error.URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            if attempt == policy.max_attempts:
                break

        sleep_seconds = min(
            policy.backoff_max_seconds,
            policy.backoff_base_seconds * (2 ** (attempt - 1)),
        ) + random.uniform(0, 0.25)
        time.sleep(sleep_seconds)

    raise HttpRequestError(f"Request failed after {policy.max_attempts} attempts: {last_error}")
