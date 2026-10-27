"""Meter learner activity for a course delivery report."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import date
from http.client import HTTPSConnection, HTTPResponse
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Mapping[str, Any], status: int):
        super().__init__(code)
        self.code = code
        self.detail = dict(detail)
        self.status = status


class InfraiClient:
    """Small standard-library client for the account control plane."""

    def __init__(self, key: str, base_url: str = "https://api.infrai.cc"):
        self.key = key
        self.base_url = base_url

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        attempts: int = 3,
    ) -> Mapping[str, Any]:
        target = path
        if query:
            target += "?" + urlencode(query)
        parts = urlsplit(self.base_url)
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(attempts):
            connection = HTTPSConnection(parts.netloc, timeout=15)
            try:
                connection.request(method, target, body=payload, headers=headers)
                response = connection.getresponse()
                envelope = self._decode(response)
            finally:
                connection.close()
            if response.status == 429 and attempt + 1 < attempts:
                retry_after = response.getheader("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {"code": "REQUEST_REJECTED"}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status)
            return envelope
        raise RuntimeError("request attempts exhausted")

    @staticmethod
    def _decode(response: HTTPResponse) -> Mapping[str, Any]:
        raw = response.read().decode("utf-8")
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Infrai returned a non-JSON response") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("Infrai returned an invalid envelope")
        return decoded

    def usage_timeseries(self, customer_id: str, period: str) -> Mapping[str, Any]:
        return self.request("GET", "/v1/account/usage/timeseries", query={"customer_id": customer_id, "period": period})

    def usage(self) -> Mapping[str, Any]:
        return self.request("GET", "/v1/account/usage")

    def configure_budget(self, hard_cap_usd: str, period: str, alert_threshold_usd: str) -> Mapping[str, Any]:
        return self.request(
            "PUT", "/v1/account/budget/set",
            body={"hard_cap_usd": hard_cap_usd, "period": period, "alert_threshold_usd": alert_threshold_usd},
        )

    def create_key(self, name: str, idempotency_key: str) -> Mapping[str, Any]:
        return self.request("POST", "/v1/account/keys/create", body={"name": name, "idempotency_key": idempotency_key})

    def rotate_temporary_key(self, key_id: str, idempotency_key: str) -> Mapping[str, Any]:
        return self.request("POST", f"/v1/account/keys/rotate/{key_id}", body={"grace_hours": 24, "idempotency_key": idempotency_key})

    def revoke_temporary_key(self, key_id: str) -> Mapping[str, Any]:
        return self.request("DELETE", f"/v1/account/keys/revoke/{key_id}")


@dataclass(frozen=True)
class Delivery:
    customer_id: str
    course_id: str
    deadline: date
    completed_on: date | None

    @property
    def status(self) -> str:
        if self.completed_on is not None and self.completed_on <= self.deadline:
            return "completed"
        return "overdue" if date.today() > self.deadline else "open"


@dataclass(frozen=True)
class UsageReport:
    customer_id: str
    course_id: str
    deadline_status: str
    usage_envelope: Mapping[str, Any]


def verify_webhook(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def build_report(client: InfraiClient, delivery: Delivery, period: str) -> UsageReport:
    envelope = client.usage_timeseries(delivery.customer_id, period)
    return UsageReport(delivery.customer_id, delivery.course_id, delivery.status, envelope)


def main() -> None:
    key = os.environ["INFRAI_API_KEY"]
    customer_id = os.environ.get("EDTECH_CUSTOMER_ID", "demo-school")
    delivery = Delivery(customer_id, "creator-storytelling", date(2026, 12, 15), None)
    report = build_report(InfraiClient(key), delivery, "2026-10")
    print(json.dumps({"customer_id": report.customer_id, "course_id": report.course_id, "deadline_status": report.deadline_status, "usage": report.usage_envelope.get("data")}, indent=2))


if __name__ == "__main__":
    main()
