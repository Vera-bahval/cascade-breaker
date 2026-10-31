# Native v4 integration receipt

The opt-in native adapter is implemented against contract revision 4.1 and its
final scripted replay passes 32 tests. The existing FinBot probe suite passes 42 tests. No new inference API
requests, new dependency, subagent, commit, or public HTTP/UX change was made by
this implementation task. The profile is off unless explicitly enabled.

## Activation and native boundaries

For a native local experiment set `FINBOT_V4_PROFILE=A` or `B` and a durable
`FINBOT_V4_STORE=/absolute/private/path.sqlite`. Invalid enabled configuration
fails closed. Tests instead use a private `Runtime(...).open()` or
`agent_scope(...)`, which permits an explicit synthetic fixture contract.
Native Invoice has no currency: no currency is inferred from USD policy. Each
cut freshly attests the declared immutable fixture unit contract using trusted
`server_context` operation `currency_contract_attest`, with current material
versions and a fresh record ID. The safe synthetic fixture explicitly declares
USD and an initial no-HOLD state;
missing currency leaves payment UNKNOWN. Initial human facts, if declared by a
fixture, use the synthetic independent registry and are never inferred from a
message or ordinary invoice approval.

`finbot/probe/v4.py` is a lightweight default-off bridge. Runner entry and chat
stream entry capture authenticated `SessionContext`; actual concrete class
identity supplies the technical actor. Workflow admission, all callable maps,
direct decorated native methods, chat native tools and direct MCP callables are
covered. MCP availability uses the actual discovered server/tool map. B removes
SystemUtils from vendor-origin discovery and checks invocation again, including
already connected providers and Fraud descendants; admin registered tools remain
available. Configurable agent names and text summaries supply no authority.

P0 runs before model entry. P1 precedes tools/delegations/start_workflow;
mutations additionally receive P3 and transfer alone receives P4. Child runner
completion performs P2 before the parent method can capture or consume its
summary. P5 remains audit-only. STOP is durable and explicitly rethrown through
native BaseAgent/chat/MCP/runner and native tool handlers. Later tools, retry,
completion, contextual inference and chat direct Responses calls check STOP.
There is an immediate check after awaited instrumentation/hooks, immediately
before underlying model/native/MCP invocation.

Native namespace and actual portal gates are preserved. In particular generic
same-namespace cross-vendor getters remain permitted at the vendor chat portal,
and FinDrive's vendor gate denies admin files. The native prompt's stronger
current-vendor wording is not silently added as a new A/B control. Admitted
workflow subject arguments still bind to the immutable workflow envelope.

## Evidence and claims

Successful scoped native flags persist typed HOLD and review facts. A positive
no-flag invoice review requires successful native reads of the current invoice
and matching vendor risk profile, current covered material versions, and
successful completion by that same concrete Fraud execution. Vendor aggregates
or successful task completion alone cannot establish it. This is a procedural
structured-review check, not a semantic assessment of fraud analysis quality.
Summaries cannot clear a typed HOLD. Stored facts keep their original versions
and event sequence. Under contract 4.1, HOLD/independent-clearance are invoice
event history: material edits do not erase known HOLD/no-HOLD, and latest-event,
subject and clearance-after-HOLD checks still apply. Other payment readiness
facts remain material-version bound. Restarting with an initial fixture state
cannot overwrite a newer native HOLD.

Successful native invoice approval creates the ordinary material-bound approval
record. Contract 4.1 permits valid native reapproval when the source row remains
approved after a material edit; it does not invent a terminal-row prohibition. It does not create human approval. Every observed pre-effect material
snapshot reconciles invoice/vendor revisions and invalidates stale bindings.
Completed transfer records retain the actual successful arguments and reference.
A07 bookkeeping checks exactly one native completed transfer matching reference,
invoice, vendor, amount, currency and retained authorized recipient. It is
separate from P4 zero-prior-transfer prevention.

Each chat start_workflow reserves a fresh owner and atomically acquires its B
claim before scheduling. Internal delegation alone inherits that owner. Losing
`ClaimConflict` gives BLOCK with `B02:violated`; journal unavailability gives
UNKNOWN. The private background coroutine opens the captured runtime inside
actual execution, after the chat context may already have been reset. Known
terminal success releases the claim; STOP/uncertain outcome retains it for
independent reconciliation without TTL.

## Final validation

All commands use the existing native Python 3.13 environment; no model API
client is contacted. The native integration test module chooses its temporary
DATABASE_URL and mock provider before importing FinBot. Internet sockets are
rejected by the replay and each native test.

From repository root:

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m experiments.local_guards_v4.integration_replay --output /tmp/v4-integration-replay.json
```

Result: **32 tests, 0 failures, 0 errors**. Coverage includes safe actual native
Fraud/invoice/payment delegation, in-memory FastMCP transfer and native paid
bookkeeping; foreign objects/attachments; forged no-HOLD summary; amount/account
edits and positive amount-edit/reapproval/new-binding renewal; same-namespace permitted getters; concurrent duplicate chat admission;
restart with uncertain claim and durable HOLD; corruption/verifier exceptions;
child STOP and no later same-batch tool/parent model/retry; background execution
after parent context reset; direct native and MCP paths; immutable vendor origin;
admin tool preservation; missing currency; P5 audit; and profile-off behavior.

Final correction wave was observed RED first: the safe actual invoice review
had insufficient native review evidence, duplicate admission returned UNKNOWN,
and suspended before-model/native/MCP instrumentation allowed downstream calls
or effects. The corrected focused six-test set passed, including the
aggregate-only review negative test. Final full replay then passed all 32. The added 4.1 positive renewal regression
starts with a bound approval at 100, observes an amount edit to 101 while the
row remains approved, completes fresh actual invoice/vendor Fraud review, calls
the real Invoice reapproval tool, verifies a new binding ID/version, and then
performs exactly one native transfer and paid bookkeeping. The paired existing
no-reapproval amount/account-edit tests still STOP before transfer.

From `finbot/`, on the unchanged final native FinBot source files (the later
4.1 update changed the pure guard, adapter currency attestation and one test):

```sh
LLM_PROVIDER=mock DATABASE_URL=sqlite:////tmp/finbot-v4-existing-probe-final.sqlite /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m pytest tests/unit/probe -q -p no:tests.plugins.google_sheets_reporter.pytest_google_sheets
```

Result: **42 passed**, one pre-existing Authlib deprecation warning, 0.44 s.
`git diff --check` and compilation of changed modules also passed.

The latest receipt is saved in `results/native-replay.json`. Its instrumented
integration replay measured 148 complete `Runtime.check`
invocations, including native repository reads, sidecar operations, pure guard
and STOP persistence: median **8.593 ms**, p95 **30.879 ms**. Tracemalloc was
active, so these are instrumented local checks rather than production traffic
latency. Whole test execution was 5.514 s; imports plus execution 10.627 s.
Peak traced Python allocation was **107,296,546 bytes** including imports and
native dependencies. This is not process RSS or a baseline-relative overhead
claim. Pure guard-only `timing_ms` is not substituted for full-check timing.

## Acceptance limits

- Native source DB commits and SQLite sidecar commits are independent. Approval
  mutation plus binding, transfer plus journal, and check plus effect are not a
  shared transaction. A journal failure after a source effect stops continuation
  and retains uncertainty; it cannot undo the completed effect.
- The revision guarantee is **current-read reconciliation plus observed protected
  events**. It catches observed amount/account changes and observed restorations.
  A source writer changing and restoring material state entirely between reads
  leaves no observed revision. Unobserved external ABA and source-DB races remain
  outside this guarantee. This adapter does not claim complete writer coverage,
  atomic native payments, distributed exactly-once, or prevention after an effect.
- Invoice-specific Fraud evidence uses typed source reads and technical completion;
  fraud merit, subjective vendor trust decisions and free-text intent remain out
  of scope. A no-HOLD state must have explicit typed initial/registry evidence;
  missing notes or a pleasant summary never mean no HOLD.
- Scripted safe workflows establish reachable native-path enforcement, not model
  accuracy, conversion, safe-stop FPR, held-out generalization or archive harm
  prevention. Native A/B source conflicts remain explicitly described above.
- The native probe suite checks existing behavior with the v4 profile disabled;
  it is not a claim that the entire upstream FinBot test suite was run.
