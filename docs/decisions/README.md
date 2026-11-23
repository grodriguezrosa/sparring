# Architecture decision records

One file per significant decision: what was decided, why, and what it costs. Records are never rewritten; a later decision that changes one marks the old record as `Superseded by NNNN`.

| # | Decision | Status |
|---|---|---|
| [0001](0001-score-answers-with-jev.md) | Score interview answers with Jev, called from FastAPI | Accepted |

## Writing a new record

Copy [`template.md`](template.md) to `NNNN-short-title.md` (next number, lowercase, hyphens), fill it in and add it to the table.

Records are public: write them so they are safe to publish. Never include keys, personal data (CV content, transcripts), account IDs or internal prices that are not public. Raw experiment output stays in the local, git-excluded `spikes/` folder; a record only summarises the evidence.
