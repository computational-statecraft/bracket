# The local HTTP API

bracket's page is a client of a JSON API served on `http://127.0.0.1:8765` (or the port shown in the app's window).
Anything the page does, a script can do. A live, generated schema is at `/docs` while bracket runs.

**Two rules for every request** (they keep other websites out of a server running on your machine):

1. Address it to `127.0.0.1` or `localhost`; any other `Host` is refused.
2. Every request other than `GET` must carry the header `X-Bracket: 1`.
3. Requests a browser marks as cross-site (`Sec-Fetch-Site: cross-site` or `same-site`) are refused; scripts and
   command-line tools do not send that header.

```bash
curl -s http://127.0.0.1:8765/api/status
```

```bash
curl -s -X POST http://127.0.0.1:8765/api/settings -H 'X-Bracket: 1' -H 'Content-Type: application/json' -d '{"cloud_model": "claude-haiku-5-5"}'
```

## Status and settings

| Method and path | Does |
|---|---|
| `GET /api/status` | version, data folder, session id, whether a draft can be resumed, and the state of each tier (`lexicon`, `library`, `local`, `cloud`) |
| `GET /api/settings` | every setting with its value and where it came from (`env:NAME`, `file`, `default`); the API key only as `{set, hint}` |
| `POST /api/settings` | `{name: value, …}` for any names in `backend/config.py` `SPEC`; `""` or `null` removes one. The local engine restarts if its settings changed |
| `GET /api/local/check` | a real, timed generation from the local model |
| `GET /api/cloud/check` | a real, timed request to Claude |
| `POST /api/shutdown` | quit bracket (and the local engine) |

## Local models

| Method and path | Does |
|---|---|
| `GET /api/models` | the catalog with sizes, which are installed and recommended, download progress, memory and free disk, and the engine's state (`no-binary`, `no-model`, `starting`, `ready`, `failed`) |
| `POST /api/models/{id}/download` | start (or resume) a download; poll `GET /api/models` for progress |
| `POST /api/models/{id}/cancel` | stop a download (it resumes from where it stopped next time) |
| `POST /api/models/{id}/use` | run an installed model |
| `DELETE /api/models/{id}` | delete a model from disk |

## Drafting

| Method and path | Does |
|---|---|
| `POST /api/segment` | `{text, structured: true}` splits a pasted draft into sentences with structure (`kind`: `h`/`p`/`li`, `label`, `brk`) |
| `POST /api/synonyms` | `{sentence, start, end}`: WordNet synonyms for the span, inflected to match, and its strength ladder if it is on one |
| `GET /api/propose/stream` | server-sent events of proposals. Query: `tier` (`local` or `cloud`), `sentence`, `start`/`end` (omit for the whole sentence), `n`, `strength` (integer), `register` (`plain`/`institutional`/`formal`), `length` (`shorter`/`same`/`longer`), `target` (a ladder rung), `context` (neighbouring sentences, one per line). Events: `delta` (`{text}` so far), `final` (`{options: [{text, flags}], ms}`, after the validator), `error` (`{error}`) |
| `GET /api/precedents` | `sentence`, optional `start`/`end`: up to three precedent sentences, quoted exactly, with `cites` and, for a span, the aligned `phrase` and the stretch it replaces (`rstart`/`rend`) |
| `GET /api/snapshot`, `POST /api/snapshot` | the current draft (`{doc}`), as the page saves it |

## Library

| Method and path | Does |
|---|---|
| `GET /api/library` | documents, bodies, and the state of a running fetch |
| `POST /api/library/fetch` | download the starter library's sources into the data folder (bundled ones are skipped; `?force=true` re-downloads) |
| `POST /api/library/add?name=&body=&title=&date=&url=&topic=` | add a document: the raw file (PDF, HTML, text or Markdown) as the request body |

## The record

| Method and path | Does |
|---|---|
| `POST /api/event` | `{kind, payload, sentence_id}`: append an event to the log |
| `GET /api/export?fmt=md` | the statement with structure, each sentence's history and dissents |
| `GET /api/export?fmt=json` / `?fmt=csv` | the session's full event log |

Event kinds written by the page include `edit`, `accept`, `accept.alternative`, `reject`, `bracket.open`, `bracket.add`,
`bracket.drop`, `bracket.settle`, `state`, `dissent`, `split`, `join`, `undo`, `redo`, `swap.lexical`, `rail.open.span`,
`rail.open.sentence`, `rail.claude`; the server writes `proposal.local`, `proposal.cloud` (with the raw model output and
what the validator kept) and `proposal.agreed` (precedents shown).
