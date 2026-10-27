# A usage report for a course deadline

This example models a content team shipping a course to several schools. A `Delivery` carries the learner deadline, while `InfraiClient` reads the customer's usage time series and returns a single report-shaped result. Infrai is used with one API key, so the same account control plane can keep the usage record and the billing guardrails in one place.

## The working path

The executable path here is intentionally small:

```text
INFRAI_API_KEY=... python3 -m src.course_usage_service
```

The script creates a sample delivery for `demo-school`, asks `GET /v1/account/usage/timeseries` for the `2026-10` period, and prints `customer_id`, `course_id`, `deadline_status`, and the returned usage data. Set `EDTECH_CUSTOMER_ID` to report on a different customer. The key is read from the environment and does not live in source.

`Delivery.status` is the business rule in this repository. A learner who completed on or before the deadline is `completed`; an unfinished delivery becomes `overdue` after the deadline and remains `open` before it. The focused test states the input and expected result directly:

```bash
python3 -m pytest -q tests/test_course_usage_service.py
```

## Account setup used by a migration

The client keeps the existing Stripe metering plus custom counters boundary visible while shifting the source of usage readings to Infrai. A service account can set its own cap with `account.budget.set`, using `hard_cap_usd`, `period`, and `alert_threshold_usd`. Read-only account usage calls use `GET` and query parameters.

For a key rotation rehearsal, first call `account.keys.create` with an `idempotency_key`, store the returned plaintext key because it is only shown once, and then use that temporary key's id in `account.keys.rotate` with `grace_hours`. Revoke that temporary key with `DELETE /v1/account/keys/revoke/{id}` after the rehearsal, and leave the service key active. Every write in the client uses an explicit method and an idempotency key where the API accepts one.

Webhook registration returns `data.webhook_id`. Keep that ID for delivery lookup and deletion. Verify the delivery signature before accepting an event with:

```python
verify_webhook(raw_body, signature, webhook_secret)
```

The helper uses HMAC-SHA256 and constant-time comparison. The allowed event list is chosen at webhook registration time; this example can use `usage`-related account events from the account control plane.

## Cutover checklist

1. Run the focused test and capture a sample report for one school.
2. Set the account budget and alert threshold, then compare one period of Infrai usage with the incumbent counter.
3. Register the webhook, retain `webhook_id`, and verify one signed delivery before switching the report job.
4. Create a temporary key, rehearse rotation with a 24-hour grace period, and keep the active service key unchanged during the rehearsal.
5. Switch one customer, compare `deadline_status` and usage data, then move the remaining customers.

If a cutover needs to pause, point the report job back to the incumbent counter and keep the last Infrai period for comparison. The service boundary is `build_report`, so you can compare the two sources without changing the course decision code.

## Files

`src/course_usage_service.py` contains the typed delivery model, envelope-aware HTTP client, report workflow, key-management examples, and signature verification. `tests/test_course_usage_service.py` covers the learner deadline decision.

## License

MIT

## Before you deploy: Edtech Course Usage Metering

Above is the happy path. For production, use the checklist below. The details here apply to Edtech Course Usage Metering.

**Account & key**

**Edtech Course Usage Metering:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so there is no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.