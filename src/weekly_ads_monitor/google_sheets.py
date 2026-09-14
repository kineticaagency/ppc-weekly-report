from __future__ import annotations

import base64
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class GoogleSheetsClient:
    def __init__(self, credentials_path: Path):
        self.credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
        self.token = self._access_token()

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def _access_token(self) -> str:
        now = int(time.time())
        header = self._b64(b'{"alg":"RS256","typ":"JWT"}')
        claims = self._b64(json.dumps({
            "iss": self.credentials["client_email"],
            "scope": "https://www.googleapis.com/auth/spreadsheets",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now,
            "exp": now + 3600,
        }, separators=(",", ":")).encode())
        unsigned = f"{header}.{claims}".encode()
        private_key = serialization.load_pem_private_key(self.credentials["private_key"].encode(), password=None)
        signature = private_key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256())
        assertion = f"{unsigned.decode()}.{self._b64(signature)}"
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode()
        request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["access_token"]

    def request(self, method: str, url: str, body: dict | None = None) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        })
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
            return json.loads(payload) if payload else {}

    def metadata(self, spreadsheet_id: str) -> dict:
        fields = urllib.parse.quote("properties.title,sheets.properties")
        return self.request("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields={fields}")

    def batch_update(self, spreadsheet_id: str, requests: list[dict]) -> dict:
        return self.request(
            "POST", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
            {"requests": requests},
        )

    def values_batch_update(self, spreadsheet_id: str, data: list[dict]) -> dict:
        return self.request(
            "POST", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate",
            {"valueInputOption": "USER_ENTERED", "data": data},
        )

    def values_get(self, spreadsheet_id: str, range_name: str) -> list[list]:
        encoded = urllib.parse.quote(range_name, safe="")
        response = self.request(
            "GET", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded}"
        )
        return response.get("values", [])

    def values_append(self, spreadsheet_id: str, range_name: str, values: list[list]) -> dict:
        encoded = urllib.parse.quote(range_name, safe="")
        return self.request(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded}:append"
            "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
            {"values": values},
        )
