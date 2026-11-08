# Supplemental v4.2 native recovery evidence

Post-method-freeze integration checks only. Frozen guard/runtime/contract/schema and
the existing development tests were not edited. No new800 content, accuracy corpus,
labels or predictions were read. Only the new tests/test_recovery.py and this
recovery-report.md were written.

## Result

Command from the follow-up worktree:

```text
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python -m unittest -v experiments.local_guards_v4_followup.tests.test_recovery
```

Final result: **14 tests passed, zero failures/errors**, 0.875 seconds test execution.
All listed scenarios passed against the explicitly instantiated v4.2 Runtime class:

| Scenario | Native evidence checked |
| --- | --- |
| Corrupt journal | STOP before model; invoice remains submitted and transfer table empty. |
| Deliberate verifier exception | Only new runtime guard binding fault-injected; STOP before model/effect, source DB unchanged. |
| Restart with uncertain claim | Fresh owner blocked before model. |
| Explicit confirmed failure recovery | Native chat/background failed run retains uncertain claim; trusted test reconciler inspects zero transfers and unchanged invoice, explicitly releases old claim, then a different owner is lawfully admitted and completes. |
| Amount edit without reapproval | B01 becomes unknown; attempted native transfer is stopped and zero transfers exist. |
| Account edit without reapproval | Same binding invalidation and zero-transfer result. |
| Amount edit with renewed evidence | Prior binding disappears, real native approval creates a new binding/version, real typed review is repeated, one in-process FinStripe transfer and native paid bookkeeping succeed. |
| Account edit with renewed evidence | Same process with new account identity and vendor material version; exactly one payment succeeds. |
| Chat start_workflow/background | Captured subclass runtime survives chat reset, owner/claim lifecycle correct. |
| Duplicate chat workflow scheduling | One admission blocked before scheduling; exactly one background task scheduled. |
| Legal native vendor mutation and wrong actor | Onboarding really changes trust/risk; concrete payments actor cannot acquire vendor authority from an injected callable map; DB retains lawful values. |
| Invalid vendor enum | STOP before native mutation. |
| STOP then contextual model/native reentry | No model request after STOP; attempted subsequent native runtime entry stops before mutation. |
| STOP then direct chat Responses path | No underlying Responses create call. |

The reapproval scenarios inspect the invalid binding through a pure shadow guard
before any transfer is attempted, then obtain genuinely renewed native evidence.
They do not clear or resume a guard STOP. Separate denied-transfer tests establish
that a real attempted transfer stops its admitted owner. The recovery test releases
a claim only after explicit trusted confirmation of no effect; it adds no automatic
failure classifier, no public retry API, and no authority to resume a stopped owner.

## Harness and initial failures

The old NativeRuntimeTests fixture is reused through composition, not inherited
test discovery. In this process only its module-local Runtime factory (and the
supplement's imported factory) is patched to construct the new v4.2 Runtime with
diagnostics=True. Each factory asserts exact class identity. No frozen runtime,
guard, policy or callable implementation is patched, except the explicit verifier
fault-injection test.

The initial supplemental harness run had seven harness errors caused by cleanup
of a composed IsolatedAsyncioTestCase without its own asyncio runner. Its cleanup
did not restore ScriptClient patches, producing later missing/exhausted-script
errors. The new module now invokes the harness's two synchronous resource cleanups
directly and separates the two STOP scenarios into fresh fixtures. No method fix
was made. The final run has no unresolved scenario failure.

The inherited fixture selects a temporary SQLite DATABASE_URL before imports,
uses the local mock provider/scripted clients, stubs only Redis event publication,
and rejects external IPv4/IPv6 socket connections. Real native DB mutations,
MCP provider hooks, in-process FinStripe effect, bookkeeping and sidecar writes
remain active. Only this explicit supplemental module ran; no broad test discovery
or inference API request was made.

Installed Authlib deprecation, development SECRET_KEY and native missing-invoice-ID
completion warnings remain visible. They are not reported as scenario failures.

## Authorized source-read log and integrity

After method freeze, explicitly read:

- experiments/local_guards_v4/tests/test_runtime.py for the authorized native fixture,
  scripts and selected integration scenarios.
- experiments/local_guards_v4/execution_supplement.py for explicit trusted no-effect
  reconciliation and chat/background retry.
- experiments/local_guards_v4/store.py claim/release/STOP/event methods.

Normal imports load native source dependencies already authorized for the harness.
No other old tests, results, reports or case corpora were read in this supplemental
phase. No new800 files were opened.

The following file digests were captured before supplemental tests and checked
unchanged afterwards:

| Frozen follow-up file | SHA256 |
| --- | --- |
| `guard.py` | `598e731ba962dbdc677c298fdc3540ef03c60c57e3d2e149d9749ff4db156d1f` |
| `runtime.py` | `68f81b124bb81d5881a5d888881f1a226c398f78229fcee8cab7162cd4484869` |
| `POLICY.md` | `17bddb9a94f5a06fdfffcb1eb1a88e98ea535df17813596ea29964009702e21d` |
| `policy.json` | `a2bef6576e8f598d30a418681b8d8d27a11893d2c23575a5ac3c4fd28b6d8487` |
| `schema.json` | `f8e22af22ea0245e3494d143e2597ff23fbb424ab89a74c4c8e3429dc6be92f1` |
| `tests/test_guard.py` | `d6327cda68abe4e5f3b268dd9aed4179b382818f74bddd7dcdd899dfea42058e` |
| `tests/test_runtime.py` | `8a5e840ef8685d43d1dffafff2d9fbfe6a441572efbdd9c61709b714249f6bd6` |

This is isolated execution/recovery evidence, not a corpus-accuracy result,
production authorization, sidecar/source-DB atomicity proof or external-write race
guarantee.
