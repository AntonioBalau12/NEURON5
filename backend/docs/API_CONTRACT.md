# API contract v1 — NEURON5 offline classification app

Status: binding for the current build (etapa C–G of `frontend/public/PLAN_ARHITECTURA_API_CSV_OFFLINE.md`).
Owner of changes: the Contract/Architecture agent. Backend and frontend code must match this
document; change the document and both sides together.

## 0. Runtime layout

| Piece | Where | Port |
| --- | --- | --- |
| Next.js UI (already running in dev) | `frontend/` | 3000 |
| FastAPI backend | `backend/` | 8000 (uvicorn) |

- API base path: `/api/v1`.
- Frontend calls `http://localhost:8000/api/v1/...` directly (cross-origin, same machine).
  `fetch(..., { credentials: 'include' })` so the session cookie travels.
- CORS on the backend allows exactly `http://localhost:3000` and `http://127.0.0.1:3000`,
  with `allow_credentials=True`, methods GET/POST/PUT/DELETE/OPTIONS, headers
  `Content-Type`, `Idempotency-Key`, `X-Requested-With`.
- Session cookie: name `n5_session`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Secure`
  in local dev, `Max-Age=session_ttl_seconds`. The token is cryptographically random
  (secrets.token_urlsafe(32)). The cookie is an isolation token, not authentication.
- Every response carries `X-Request-Id`. Errors repeat it in the body.

## 1. Conventions

- JSON request/response unless stated otherwise; UTF-8; timestamps are ISO 8601 UTC with
  `Z` suffix.
- Resource ids: `ds_<32 hex>` for datasets, `job_<32 hex>` for jobs. They are opaque.
- Ownership: every dataset/job belongs to the session that created it. A session that does
  not own a resource gets `404 NOT_FOUND` (do not reveal existence).
- Error envelope:

```json
{
  "error": {
    "code": "INVALID_CSV",
    "message": "Human readable, one sentence.",
    "details": {"line": 3}
  },
  "requestId": "req_..."
}
```

- Stable error codes (HTTP status in parentheses):
  `SESSION_REQUIRED` (401), `NOT_FOUND` (404), `INVALID_CSV` (400),
  `UNSUPPORTED_ENCODING` (400), `DATASET_TOO_LARGE` (413), `INVALID_MAPPING` (400),
  `MAPPING_REQUIRED` (409), `JOB_ALREADY_RUNNING` (409), `IDEMPOTENCY_CONFLICT` (409),
  `JOB_NOT_READY` (409), `UNSUPPORTED_MEDIA_TYPE` (415), `INVALID_REQUEST` (400),
  `PAYLOAD_TOO_LARGE` (413), `INTERNAL_ERROR` (500).
- Pagination: `offset` (>=0, default 0), `limit` (1..`page_max_rows`, default 50).
  Paginated responses always look like:

```json
{"items": [...], "offset": 0, "limit": 50, "total": 1234}
```

- All state-changing requests (POST/PUT) require a same-origin `Origin` header when one is
  present; a foreign Origin gets `403` (`error.code = "INVALID_REQUEST"`). `curl` without
  Origin is allowed.

## 2. Sessions

### POST /api/v1/sessions
Creates an anonymous session if the request has no valid cookie, otherwise returns the
existing one. Sets/refreshes the cookie.

```json
{"sessionId": "sess_...", "createdAt": "2026-10-28T11:00:00Z", "expiresAt": "2026-10-28T17:00:00Z"}
```

### GET /api/v1/sessions/current
`200` with the same body, `401 SESSION_REQUIRED` if absent/expired. Never creates one.

All other endpoints below require a valid session cookie.

## 3. Datasets

```json
{
  "id": "ds_0123456789abcdef0123456789abcdef",
  "mode": "manual",
  "format": "practice",
  "createdAt": "2026-10-28T11:00:00Z",
  "byteSize": 1234,
  "encoding": "utf-8-sig",
  "delimiter": ",",
  "hasHeader": true,
  "columns": ["id", "text", "date"],
  "rowCount": 42,
  "mapping": {
    "textColumn": "text",
    "dateColumn": "date",
    "idColumn": "id",
    "resultColumn": "label",
    "confirmed": false,
    "autoDetected": true
  },
  "warnings": [],
  "preview": {
    "columns": ["id", "text", "date"],
    "rows": [["p-1", "Holdan started at Hooly on 12 January 2026.", "2026-01-12"]],
    "offset": 0,
    "limit": 5,
    "total": 42
  }
}
```

- `format`: `"practice"` when the header is exactly `id,text,date,label,form` (the
  input files the team receives; order matters), `"manual"` for manual drafts,
  `"generic"` otherwise. Practice format is validated row by row (id/text non-empty,
  `date` = `yyyy-mm-dd`, `label` empty or true/false/unsure, `form` empty or a JSON
  array of `{subject, attribute, value}`), its mapping is fixed to
  `text/date/id/label` and **already confirmed**, so a job can start right after the
  upload. The `form` column is preserved untouched in the output; malformed rows only
  add the `PRACTICE_ROW_ERRORS` warning (the row-level engine errors still apply).
- `rowCount` may be `null` when it cannot be computed within the upload budget.
- `mapping` may be `null`; `mapping.confirmed` must be `true` before a job can start.
- `warnings` holds stable warning codes: `AMBIGUOUS_DELIMITER`, `BOM_PRESENT`,
  `EMPTY_FILE`, `HEADER_WITHOUT_TEXT_COLUMN`.
- `preview` is included on dataset creation (first `limit=5` rows) and on GET; it is
  paginated through `GET /datasets/{id}/preview`.

### POST /api/v1/datasets/manual
Body:

```json
{
  "columns": ["id", "text", "date"],
  "rows": [
    ["p-1", "Holdan started at Hooly on 12 January 2026.", "2026-01-12"]
  ]
}
```

- `columns` optional; default is `["id","text","date"]` and `rows` are arrays in that
  order when omitted. `rows` items may also be objects keyed by column name.
- Empty draft (0 rows) is valid; a job on an empty dataset produces an empty result.
- Server serializes the draft to a snapshot CSV (UTF-8, comma), checks the 1 MB limit on the
  serialized bytes (`DATASET_TOO_LARGE`), validates column names (non-empty, unique),
  and detects mapping: `text` column by name (case-insensitive match against
  `text`, `sentence`, `proposition`, `claim`, `content`), date column by name
  (`date`, `timestamp`, `day`), id column by name (`id`).
- Returns `201` + Dataset.

### POST /api/v1/datasets/bulk
`multipart/form-data` with one required file field `file` (the CSV) and optional
`delimiter` (one of `,` `;` `\t`).
- Max 10 MB of uploaded bytes (`DATASET_TOO_LARGE`).
- Reads as UTF-8 with optional BOM; invalid UTF-8 bytes → `UNSUPPORTED_ENCODING`.
- Delimiter: explicit field wins; otherwise autodetect from the first non-empty line among
  `,` `;` and tab (most occurrences wins; tie → `,` + `AMBIGUOUS_DELIMITER` warning).
- Must parse as CSV: has a header row, at least 1 column. Otherwise `INVALID_CSV`.
- First row is always treated as the header. `rowCount` is computed unless the file is
  above 2 MB, then `null`.
- Stored as an immutable snapshot in the server temp dir, always rewritten as comma-delimited
  UTF-8 CSV (the metadata keeps the detected `delimiter`/`encoding` for display); no edit
  endpoint for bulk.
- Returns `201` + Dataset.

### GET /api/v1/datasets/{id}
`200` + Dataset. `404 NOT_FOUND`.

### GET /api/v1/datasets/{id}/preview?offset=&limit=
`200` `{"columns": [...], "rows": [[...]], "offset": 0, "limit": 50, "total": 42}`.
Read-only. `404 NOT_FOUND`.

### PUT /api/v1/datasets/{id}/mapping
Body:

```json
{"textColumn": "text", "dateColumn": "date", "idColumn": "id", "resultColumn": "label"}
```

- `textColumn` required and must be an existing column.
- `dateColumn`/`idColumn`: existing column or `null`.
- `resultColumn`: existing column (its values are overwritten in the output) or a new
  column name; the output appends it when absent. Must be non-empty, at most 64 chars.
- `dateColumn` values must parse as `yyyy-mm-dd` when used by the engine; a row with an
  unparsable date is classified without a date and gets a structured row error (no abort).
- Marks `confirmed=true`. Mapping is frozen once a job is created.
- `400 INVALID_MAPPING` with details on bad column names.
- Returns `200` + Dataset.

## 4. Jobs

### POST /api/v1/jobs
Headers: `Idempotency-Key` optional, 1..128 printable chars.
Body: `{"datasetId": "ds_..."}`.

- Validates ownership, `mapping.confirmed` (`409 MAPPING_REQUIRED`).
- If an active job (`queued|running|finalizing`) exists globally → `409 JOB_ALREADY_RUNNING`
  with `details.activeJobId`.
- If `Idempotency-Key` was seen before for this session:
  same key + same datasetId → `200`, same job, `"replayed": true`;
  same key + different payload → `409 IDEMPOTENCY_CONFLICT`.
- Creates job, returns `202`:

```json
{"job": {"id": "job_...", "status": "queued"}, "replayed": false}
```

- The job starts asynchronously; the response never waits for inference.
- Job id, status, counters, progress and deadline are readable immediately through GET.

### GET /api/v1/jobs/{id}
`200`:

```json
{
  "id": "job_...",
  "datasetId": "ds_...",
  "status": "running",
  "createdAt": "2026-10-28T11:00:00Z",
  "startedAt": "2026-10-28T11:00:00Z",
  "deadlineAt": "2026-10-28T11:30:00Z",
  "finishedAt": null,
  "progress": {"stage": "classify", "processedRows": 120, "totalRows": 1897, "percent": 6},
  "counters": {"true": 80, "false": 12, "unsure": 28, "fallback": 0, "errors": 1},
  "resultAvailable": false,
  "failureReason": null,
  "warnings": ["TIMED_OUT_FALLBACK"]
}
```

- `status`: `queued | running | finalizing | succeeded | failed` (`cancelled` reserved,
  never emitted in v1).
- `stage`: `queued | parse | classify | write | validate | done | failed`.
- `percent` is `null` when `totalRows` is unknown; never invented.
- `resultAvailable` is true only when the output CSV is complete and validated.

## 5. Realtime — WebSocket

### GET /api/v1/jobs/{id}/stream?lastSequenceId=N
Session cookie is required (handshake rejected with WS close code `4401` when missing or
foreign, `4404` unknown job). Origin is validated against the CORS allowlist (close `4403`).

Server sends JSON text frames, in this order:

1. handshake:
```json
{"kind": "handshake", "protocolVersion": 1, "jobId": "job_...", "status": "running",
 "lastSequenceId": 12, "replayAvailable": true, "serverTime": "2026-10-28T11:00:01Z"}
```
`lastSequenceId` = last event id the server holds (0 when none).
2. snapshot (gap flag says whether events between requested and current were dropped):
```json
{"kind": "snapshot", "job": { ...same shape as GET /jobs/{id}... },
 "gap": false, "replayFrom": 13}
```
If `gap` is true, the UI resets its log to this snapshot and starts from `replayFrom`.
3. replay of buffered events with `sequenceId > lastSequenceId` (query param, default 0),
   each as `{"kind": "event", "event": {...}}`.
4. live events, same frame shape.
5. heartbeat every 15 s: `{"kind": "heartbeat", "serverTime": "..."}` (no sequenceId).

Event object:

```json
{
  "sequenceId": 13,
  "jobId": "job_...",
  "timestamp": "2026-10-28T11:00:02Z",
  "level": "INFO",
  "type": "progress.updated",
  "component": "processor",
  "step": "classify",
  "message": "Processed 50 of 1897 rows",
  "data": {"processedRows": 50, "totalRows": 1897, "counts": {"true": 40, "false": 5, "unsure": 5, "fallback": 0}}
}
```

- `level` in TRACE/DEBUG/INFO/WARN/ERROR/FATAL.
- `type` in job.started, step.started, step.completed, row.failed, progress.updated,
  log.recorded, job.completed, job.failed.
- `data` is a flat JSON object; `row.failed` carries rowId, lineNumber, column, code.
- The terminal `job.completed`/`job.failed` event is emitted only after the output file is
  complete and validated. After it the server closes the socket normally.
- Losing a WS connection never stops the job. A reconnect with `lastSequenceId` replays
  what the bounded buffer still holds; the buffer keeps the newest `event_buffer_size`
  (5000) events, and older ones are marked via `gap`/truncated history.

### GET /api/v1/jobs/{id}/events?afterSequenceId=0&limit=200&level=&component=&type=
Temporary event history for log export. Response:
```json
{"events": [...], "lastSequenceId": 42, "truncated": false, "total": 42}
```
`truncated=true` when the ring buffer dropped events older than the oldest one returned.
Filters are optional and repeatable (comma-separated). `limit` max 1000.

## 6. Results

All result endpoints answer `409 JOB_NOT_READY` until the job status is terminal and the
output is complete; `failed` jobs expose summary and errors but not the CSV.

### GET /api/v1/jobs/{id}/result/summary
```json
{
  "jobId": "job_...",
  "status": "succeeded",
  "totalRows": 1897,
  "counts": {"true": 1580, "false": 250, "unsure": 67, "fallback": 0, "errors": 3},
  "durationSeconds": 12.5,
  "warnings": [],
  "failureReason": null,
  "output": {"fileName": "result.csv", "bytes": 123456, "contentType": "text/csv; charset=utf-8"},
  "errorsCount": 3
}
```

### GET /api/v1/jobs/{id}/result/preview?offset=&limit=
Same paginated shape as dataset preview, but rows are the final output rows (read-only),
`columns` includes the result column. `404` when the job does not exist for the session.

### GET /api/v1/jobs/{id}/result/errors?offset=&limit=
```json
{"items": [{"rowId": "r-4", "lineNumber": 5, "column": "date", "code": "INVALID_DATE", "message": "..."}],
 "offset": 0, "limit": 50, "total": 3}
```

### GET /api/v1/jobs/{id}/result.csv
`200`, `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment;
filename="result-<jobid>.csv"`, streamed in chunks. `409 JOB_NOT_READY` before completion.
Available for a short grace period after completion (`result_grace_seconds`, 10 min);
after cleanup the job and its artifacts are removed (`404 NOT_FOUND`).

## 7. Processor behaviour and local classification

Jobs classify rows with the fitted local prototype at `backend/scripts/adapter.joblib`
(SHA-256 `9200b1536c6df28609e4e8b36a3aaefc16a08cecf1278392d878f847d609fd2a`).
The model path can be changed with `NEURON_MODEL_PATH`; the default is resolved from
the backend package, so it does not depend on the process working directory. A loaded
artifact is cached per process and path. Restart the backend after replacing an
artifact at the same path. Model-load or artifact errors fail the job with
`failureReason: "CLASSIFIER_UNAVAILABLE"`; no mock labels are generated.

The local adapter uses the mapped text and date fields. Text must be nonempty and
the date must be present and ISO `yyyy-mm-dd`. An empty sentence or missing/invalid
date produces `unsure` plus a structured row error; the backend does not invent a
date. A valid prediction is the model's argmax between `true` and `false`; if its
probability is below `0.5`, the label is `unsure`. Confidence is used internally and
is not serialized in the current API or CSV output.

### CSV output and mapping

The processor streams the dataset snapshot through the local row engine. It keeps
all input columns in their original order, preserves every non-result cell (including
`form` for the `id,text,date,label,form` practice schema), and overwrites the mapped
result column. If the mapped result column did not exist, it appends that column.
Rows remain in input order and the output has the same number of rows. These are the
same output invariants checked before `resultAvailable` becomes true; no confidence
column is added.

### Progress, errors and deadlines

The existing job and event contracts remain unchanged. Row processing emits the
existing `step.started`, `step.completed`, `progress.updated`, `row.failed`, and
`log.recorded` events. Progress counts use `true`, `false`, `unsure`, and `fallback`;
row errors appear through the existing errors endpoint and `row.failed` event shape.

The worker checks the job deadline between rows. If the deadline has expired, the
remaining rows are written as `unsure` fallbacks, and the completed job includes the
existing `TIMED_OUT_FALLBACK` warning. A running model inference is not interrupted
mid-row. A missing or unloadable model is an infrastructure failure, not a row-level
prediction and not a source of fallback labels.

## 8. Frontend behaviour required by this contract

Single page, three stages (`frontend/src/components/Studio.tsx` is the mounting point):

1. Data — tabs Manual / Bulk. Manual: editable table (id, text, date) with add/delete row,
   undo/redo (Ctrl+Z / Ctrl+Shift+Z), paste TSV into the table, Save button (POST
   datasets/manual). Bulk: file input, upload progress, preview table, mapping panel with
   text/date/id/result column selects, Confirm mapping (PUT mapping), warnings shown.
   Process button enabled only after mapping confirmed -> POST jobs with an Idempotency-Key
   generated per user click attempt; then go to stage 2.
2. Processing — status badge, stage, progress bar (percent only when known), counters,
    virtualised log list (last 1000 visible), filters level/type/component, clear + export
   visible logs as .json/.txt, auto-scroll toggle, reconnect indicator. On terminal status:
   succeeded -> stage 3; failed -> stay with error + reason and a Retry/Back action.
3. Results — summary cards (status, duration, rows, labels, fallback, errors), paginated
   read-only result table, paginated errors list, Download CSV button
   (`/result.csv`), New run button (back to stage 1, resets state).

Polling fallback: if WebSocket fails, poll GET /jobs/{id} every 2 s; the UI must still reach
the terminal state and stage 3.
