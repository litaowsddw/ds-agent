# Task 1 report: durable LLM usage-event storage

## Status

DONE_WITH_CONCERNS. The Task 1 metering persistence tests pass. The requested
existing provider-store test file is absent, and the closest provider runtime
test cannot collect because of an unrelated pre-existing Redis type annotation
error.

## Files changed

- `apps/api/app/models/metering.py` — immutable usage-event and versioned
  model-price SQLAlchemy models.
- `apps/api/app/models/__init__.py` — model registration for metadata/Alembic.
- `apps/api/app/services/db/metering_db.py` — immutable idempotent recording
  and scoped aggregation service with input DTOs.
- `apps/api/alembic/versions/20260714_0002_add_llm_usage_events.py` — MySQL
  compatible event/price schemas, unique key, and required event indexes.
- `apps/api/tests/test_metering_db.py` — focused persistence and aggregation
  tests using an isolated async SQLite session.

## TDD evidence

### RED

Command:

```powershell
pytest apps/api/tests/test_metering_db.py -q
```

Expected feature-missing failure after the test harness configured SQLite:

```text
ModuleNotFoundError: No module named 'app.models.metering'
```

An earlier harness-only attempt failed before test collection because the
existing database module defaults to MySQL and this environment has no
`aiomysql`; the test configures SQLite before importing application models so
the final RED failure identifies the missing metering API.

### GREEN

Command:

```powershell
pytest apps/api/tests/test_metering_db.py -q
```

Output:

```text
.... [100%]
4 passed, 1 warning in 0.65s
```

The warning is the existing `pyproject.toml` `asyncio_mode` setting while the
active environment lacks pytest-asyncio; the tests intentionally use
`asyncio.run` and are not skipped.

## Tests covered

- Idempotent replay returns the original event and preserves `NULL` unknown
  usage/cache fields.
- Replay cannot overwrite provider-reported token/cache facts.
- Aggregation groups by model, sums only known values, and counts unknown
  usage calls.
- Time filtering and an additional supported grouping dimension work.
- `python -m compileall` on all Task 1 Python files and `git diff --check`
  passed before the final test run.

## Existing provider test check

`apps/api/tests/test_model_provider_store.py` is absent. There is no separate
runtime/provider storage test. The closest provider runtime test was run:

```powershell
pytest apps/api/tests/test_metering_db.py apps/api/tests/test_llm_gateway.py -q
```

It failed during collection of `test_llm_gateway.py`, before metering test
execution, with:

```text
TypeError: unsupported operand type(s) for |: 'NoneType' and 'NoneType'
apps/api/app/core/redis.py:22: _pool: ConnectionPool | None = None
```

No Gateway, Chat, Workflow, frontend, Redis, or dependency files were changed.

## Self-review

- Event storage has the required `(org_id, gateway_call_id)` unique key and
  returns the existing fact without update on replay.
- All provider token/cache and estimated-cost fields are nullable; missing
  values remain `NULL` and aggregates use SQL `SUM`, which ignores `NULL`.
- Event columns contain attribution, provider/lifecycle, safe prefix
  diagnostics, costs, and safe error metadata, but no prompt, completion,
  API-key, Authorization, or prefix-hash field.
- Migration creates the three required event indexes and versioned
  `model_prices`; it contains no credits, invoice, refund, or budget logic.
- Only the Task 1 files listed above and this required Task 1 report are
  included in the commit.

## Commit

Pending at report creation; committed immediately after final scope check as:

```text
feat: persist LLM usage events
```

## Concerns

- Full cross-test validation is blocked by the pre-existing Redis annotation
  collection failure described above.
- The test command has one pre-existing pytest configuration warning because
  pytest-asyncio is unavailable in this environment.

---

## Follow-up: immutable usage facts

### Root cause

The original unique key only prevented duplicate inserts. Persisted
`LLMUsageEventModel` instances had no ORM update guard, so any caller holding
an ORM instance could modify a token or `created_at` and `flush()` it.

### RED

Command:

```powershell
pytest apps/api/tests/test_metering_db.py -q
```

Output before the fix:

```text
....F [100%]
Failed: DID NOT RAISE ValueError
```

The new cross-session test wrote an event, loaded it in a different session,
set `input_tokens` to `99`, and confirmed that the old implementation allowed
`flush()`.

### GREEN

Command:

```powershell
pytest apps/api/tests/test_metering_db.py -q
```

Output:

```text
..... [100%]
5 passed, 1 warning in 0.73s
```

### Follow-up change and review

- `LLMUsageEventModel` now rejects every ORM `before_update` with
  `ImmutableUsageEventError`.
- The MySQL Alembic migration adds a `BEFORE UPDATE` trigger that raises SQL
  state `45000`, protecting against UPDATE statements that bypass the ORM.
- The cross-session regression test changes both `input_tokens` and
  `created_at`; each `flush()` raises, and a fresh session verifies the stored
  token and timestamp still match their original values.
- An older aggregation test was adjusted to stop directly updating
  `created_at`, because such an update is now correctly prohibited.

### Follow-up commit

```text
fix: enforce immutable usage events
```
