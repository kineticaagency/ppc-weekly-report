from __future__ import annotations

import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    pass


def request_json(url: str, *, headers: dict[str, str], body: dict, retries: int = 0) -> dict:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method="POST")
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if attempt < retries and exc.code in {201, 202}:
                time.sleep(min(int(exc.headers.get("retryIn", "2")), 10))
                continue
            raise ApiError(f"HTTP {exc.code}: {detail}") from exc
    raise AssertionError("unreachable")


def request_text(url: str, *, headers: dict[str, str], body: dict, retries: int = 0) -> str:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method="POST")
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=90) as response:
                if response.status in {201, 202}:
                    if attempt >= retries:
                        raise ApiError(f"Report is not ready after {retries + 1} attempts")
                    time.sleep(min(int(response.headers.get("retryIn", "2")), 10))
                    continue
                return response.read().decode("utf-8-sig")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if attempt < retries and exc.code in {201, 202}:
                time.sleep(min(int(exc.headers.get("retryIn", "2")), 10))
                continue
            raise ApiError(f"HTTP {exc.code}: {detail}") from exc
    raise AssertionError("unreachable")
