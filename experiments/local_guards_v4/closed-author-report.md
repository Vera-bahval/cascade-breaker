# Independent closed contract author report

Generated 400 single-prefix episodes, 200 safe/unsafe pairs, seed 48117, after the declared global method freeze. Gold is manually specified per scenario from contract revision 4.1; no guard implementation was invoked.

## Commands and checks

`/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_v4/make_closed_test.py`

Host python3 lacked jsonschema; the worktree-local .venv/bin/python did not exist. The parent supplied the existing interpreter above, whose installed jsonschema was used without installation. Both failed executable/import attempts are retained in the read log.

The standalone generator loads only three allowlisted contract files, uses Python standard library and installed jsonschema, validates every observation against Draft 2020-12 schema, checks all twelve requirement keys, pair membership/counts, unique opaque IDs, 400 rows per stream, gzip UTF8 JSONL roundtrip and repeated compression equality with mtime=0. Compressed hashes and contract hashes are recorded in closed/manifest.json. No baseline payment envelope is invented.

Schema validity: 394 valid observations; 6 deliberate invalid observations. Deliberate corruption consists of two claim-record schema failures (generation zero, empty record ID) and four missing/corrupted-event cases (boolean event sequence, extra context property, duplicate attachment IDs, integer instead of Boolean fact). Their applicable requirement states are UNKNOWN because validated trusted input is unavailable. No invalid shape is labeled BLOCK merely because validation failed.

## Families and variety

| Family | Cases | Pairs |
| --- | ---: | ---: |
| session_object_scope | 40 | 20 |
| tool_authority | 40 | 20 |
| delegation_evidence_provenance | 40 | 20 |
| state_transitions | 40 | 20 |
| hold_review_completion | 40 | 20 |
| payment_obligations | 40 | 20 |
| post_approval_invoice_mutation | 40 | 20 |
| account_mutation | 40 | 20 |
| workflow_duplicates | 40 | 20 |
| missing_corrupted_events | 40 | 20 |

Session/object cases vary P0-P4, no referenced entities, one/multiple attachments, native cross-selection and namespace/session/snapshot loss. Tool cases cover native/MCP actor differences, missing actor, unregistered callable, actual-argument mismatch and allowed admin SystemUtils versus vendor-origin B03. Delegation spans five concrete children and successful/failed/unknown technical completion, parent/call linkage, subjects, sources, conflicting/newest/future evidence. State transitions include permitted reprocessing from approved/rejected/paid, every native target category, early approval prerequisites, onboarding three-field and fraud risk-only shape.

HOLD cases distinguish persistent history from material versions, newer HOLD and independently authenticated clearance, fraud review from technical work, and absent/stale/conflicting evidence. Payment cases include exact decimal exponent equivalence, zero/negative/maximum, >10000 human boundary, USD constraint, recipient, duplicate counts, transfer-before-bookkeeping and reference binding. Invoice/account changes include fresh reapproval, amount/account/version mismatches, ABA writer revisions, missing/revoked binding and stale/newest recipient comparisons. Workflow cases span P0-P4 admission/continuation, vendor-wide scope, internal descendants versus fresh start owner, claim key/state/generation/prior sequence and unavailable store. Event cases test absent facts/proofs, missing bindings, future/cross-scope/cross-subject values, newest-first selection and deliberate shape corruption. Pair differences include substantive allowed admin/A-only behavior; they are not twenty opaque-ID copies.

## Restrictions, assumptions and limits

All explicit reads and interpreter/module imports are recorded in closed-author-read-log.jsonl. Only the brief and three allowlisted existing project files were read. Generated owned files were written directly; compressed roundtrip verification operates on in-memory bytes. No directory listings, implementations, test discovery, old cases, archive/history/results/report access, local method import, model inference, subagent or Git mutation occurred.

This is a declared trusted synthetic producer. Its scope, actual callable mapping, covered writer revisions, complete transaction lookup/retained arguments, hold/clearance history and independent synthetic human registry are assumptions, not authenticity recoverable from arbitrary JSON. Account references are opaque synthetic equality tokens. All proof values/scope/versions precede their cut unless intentionally corrupted. Non-human fixture evidence does not authenticate human actions. B-only cases deliberately remain A-allowed where their A evidence is complete.

These are state decisions with null continuation outcomes, not measured payment harms or prevention. No P5 case is included because P5 is detection-only. A single claim snapshot cannot measure atomic claim acquisition, external writers, race windows, hidden generation changes or actual parallel executions; tests cover expressible snapshot obligations only. P2 legacy A09 uses explicit fraud-delegation HOLD semantics; P3 A09 records only known legacy approval violations from the published contract, not inferred behavior of unseen code. Exact per-requirement states, especially malformed-input and legacy A09 applicability, require the independent reviewer audit before prediction. Family naming is the canonical descriptive snake_case used by this package.

## Decision counts and requirement coverage

```json
{
  "requirements": {
    "A01": {
      "satisfied": 384,
      "unknown": 12,
      "violated": 4
    },
    "A02": {
      "not_applicable": 1,
      "satisfied": 379,
      "unknown": 15,
      "violated": 5
    },
    "A03": {
      "not_applicable": 74,
      "satisfied": 295,
      "unknown": 16,
      "violated": 15
    },
    "A04": {
      "not_applicable": 346,
      "satisfied": 34,
      "unknown": 18,
      "violated": 2
    },
    "A05": {
      "not_applicable": 366,
      "satisfied": 22,
      "unknown": 4,
      "violated": 8
    },
    "A06": {
      "not_applicable": 380,
      "satisfied": 12,
      "unknown": 3,
      "violated": 5
    },
    "A07": {
      "not_applicable": 392,
      "satisfied": 4,
      "unknown": 2,
      "violated": 2
    },
    "A08": {
      "not_applicable": 216,
      "satisfied": 122,
      "unknown": 45,
      "violated": 17
    },
    "A09": {
      "not_applicable": 369,
      "satisfied": 27,
      "violated": 4
    },
    "B01": {
      "not_applicable": 216,
      "satisfied": 150,
      "unknown": 13,
      "violated": 21
    },
    "B02": {
      "not_applicable": 2,
      "satisfied": 373,
      "unknown": 12,
      "violated": 13
    },
    "B03": {
      "not_applicable": 387,
      "satisfied": 9,
      "unknown": 1,
      "violated": 3
    }
  },
  "targets": {
    "ALLOW": 200,
    "BLOCK": 94,
    "UNKNOWN": 106
  }
}
```

All safe members are ALLOW. Unsafe members distinguish verified violations from insufficient evidence; absence is not BLOCK by default. Metadata contains no labels; episode intent, family, paired member, rationale and requirement states remain in gold-adjacent files. The observation stream contains no case titles, family labels, attack instructions or gold fields.
