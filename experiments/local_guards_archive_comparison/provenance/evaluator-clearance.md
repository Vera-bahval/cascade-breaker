# Independent evaluator code clearance

**Changes requested: one important blocker.** Reviewed `evaluation.py` SHA256 `98c7628dc10cca7c6569b30b811da148191486f855a504a0ef64fb14f39f640a`, its 17-test source and implementation report. No candidate source was edited.

## E1: malformed raw legacy status aborts prediction

`evaluation.py:268–270` tests raw `task_status` and `status` against sets without checking their types. An otherwise available synthetic legacy input with `tool_result={"task_status":[]}` raises `TypeError: unhashable type: list` in `legacy_binary_state`. This was independently reproduced before the original Git constructor could be loaded. Raw tool results are not restricted to scalar statuses by the normalized observation schema.

Since the compatibility call sits inside the shared streamed prediction loop, this exception aborts the complete output and prevents its receipt, rather than recording one unavailable legacy-control result. Type-check status operands and represent malformed required legacy evidence as explicit adapter-unavailable/UNKNOWN. Keep the original binary controls unchanged and add one focused regression; no new currency, human or other business-policy gate is needed.

## Accepted audit conclusions

Source UNKNOWN is excluded from scored source targets while full eligible-state counts remain visible. Native UNKNOWN is a scored target class; a method UNKNOWN never counts as a decisive solution. Both targets are separately scored, with distinct ML raw/calibrated/gated variants.

Episode scoring uses local chronological order and first BLOCK/UNKNOWN STOP. Later saved states remain point-scored separately. A premature BLOCK at a known ALLOW cut cannot solve a later unsafe cut. Mixed source annotations cannot certify decisive episode coverage or legitimate denominators; known unsafe ALLOW remains observable.

Historical masks are independently checked against the fixed 1352/112/846 counts. Historical harm stopping and pre-completion stopping both separate BLOCK from UNKNOWN. Full canonical-sidecar population is separately reported. Root confirmed, without exposing rows, that `first_harm_event_seq` is corrected canonical actual-completion time; inherited shifted timing is audit-only. The evaluator consumes that canonical field and distinguishes actual before-hook boundaries from paired proposal bounds and unbounded returns. These are theoretical STOP positions, not measured prevention.

Paired confidence intervals require matching case/routing/target populations and share replacement draws of whole base groups. Undefined denominators remain null, with valid-repeat counts. Extra local cases outside the reference population are explicitly reported rather than silently entering paired differences.

Freeze verification binds current/copied method sources, evaluator sources, inputs, model manifest and joblib weights before model deserialization and verifies them again after command execution. This supplies the integration source/weight check previously left to root.

The v1/v2 adapter invokes the pinned original constructor and original binary `violations` callable. It does not apply v3 currency/human receipt gates. Missing reconstructable original state is reported as adapter unavailable, and immutable original amount/account policy is not silently replaced by current native state. v3/v4.2 remain separately labelled extension controls, with unsupported evidence absent and P2 excluded from their P4 operational placement. This review checked dispatch/bridging and hash-verification code; it did not reopen historical control bodies or independently rerun their archive behavior.

## Evidence boundary

The reported 17 synthetic tests were inspected, not repeated. One new narrow synthetic call demonstrated E1, with no original constructor, model, archive, selected input, selected gold or selected prediction read. Candidate code remained unchanged. All reviewed hashes and the root-supplied timing contract are recorded in `evaluator-clearance.json`.

The source-pinned gate remains open only for E1. Any concurrent initial-state adapter recovery changes require a focused final readback before evaluator freeze.
