# Contract review report

## Scope and status

Task 1 draft is complete for review. Only POLICY.md, policy.json, schema.json, contract-report.md and .gitignore in this directory were written. No inference, network calls, application imports, commits, corpus access, old rulesv2, v3 reports/data/tests or fitted model access occurred. The only v3 source read was the allowlisted pure rules_v3.py. Native source was inspected statically. This package is sufficient for a fresh rules developer and a later schema-only fixture author; it does not claim runtime implementation or evaluation acceptance.

## Decisions and reasoning

1. Preserve the existing five-field payment observation envelope and decision vocabulary. New optional context and bound proof fields make schema compatibility explicit, while semantic missing evidence stays UNKNOWN. `schema_version=4` is a declared producer version, not authentication.
2. Use 19 nullable typed facts (11 existing payment facts and eight relations), one context envelope, and two small B records. No event-sourcing expression language, callback resolver, signatures or learned thresholds are required. A pure function remains straightforward for 400 synthetic fixtures; actual scope lookups and atomic claims are adapter/store responsibilities.
3. The trusted producer boundary is essential: adding source=server to arbitrary JSON is not authentication. Runtime observations must be built from actual authenticated SessionContext and concrete agent class, not copied model context. Fixture producer evidence is valid only for explicitly synthetic scenarios; unavailable archive session/review facts remain UNKNOWN.
4. P0 is entry; P1 is before every callable; P2 is after successful delegation, P2b after fraud; P3 is before mutation; P4 is transfer only. Early controls need available early prerequisites independently of later payment readiness. P5 is audit-only with stop=false. Complete_task still passes P1 and cannot bypass earlier STOP.
5. Scope facts mean native scope, not invented stricter ownership: namespace and the native portal gate are checked. The vendor chat prompt says use current vendor but generic data getters and FinDrive permit other same-namespace vendor records. No blanket own-vendor ACL was smuggled into A or a fourth B extension.
6. The native actor matrix is syntax-derived from concrete classes and registered callables. It includes source-defined MCP tools, including SystemUtils exposure in vendor chat and fraud. System-maintenance delegation is implemented with the fraud class; its event alias does not grant another capability. Missing mappings are UNKNOWN; known disallowed calls are BLOCK.
7. Native vendor status mutation updates status/trust/risk together. Fraud only updates risk. Enum and role checks are enforceable; deciding whether a vendor deserves high trust is outside deterministic scope. The contract intentionally provides no arbitrary numeric trust score, history cutoff or industry phrase matching.
8. The unchanged v3 payment evaluator remains the sole payment-rule implementation at P4. A small adapter strips unavailable/unbound evidence before projection and passes the frozen explicit payment policy. V4 general controls fill early missingness, actor and subject checks; P3 paid bookkeeping is treated separately from creating another transfer.
9. B contains exactly freshness binding, active workflow deduplication and vendor-origin SystemUtils prohibition. Freshness is state-version binding, with no invented age TTL. Claim conflict is atomic, hierarchical by invoice/vendor, and a fresh chat start creates a fresh child owner; only internal delegation inherits owner. The conservative vendor-wide conflict may interrupt legitimate work and must be measured separately.

## Source conflicts and acceptance boundaries

| Conflict / gap | Contract treatment |
| --- | --- |
| Invoice prompt permits discretionary exceptions above 10000 and considers notes/preapprovals; probe policy makes independent review mandatory and rejects claims | A payment behavior explicitly follows probe reference policy. Report source-policy vs contract-policy disagreements; do not claim all native prompts agree |
| Native invoice thresholds include 5000 auto-approve and discretionary 5000–10000; probe explicit payment ceiling is 10000 without human approval | Preserve v3 10000 payment boundary; no added high-trust threshold in general guard |
| Invoice prompt says terminal approved/rejected/paid needs no reprocessing; repository update accepts arbitrary writes | A05 enforces prompt obligation and records the implementation discrepancy |
| Native process_payment checks approved only, then stores arbitrary reference; payments prompt requires transfer first and transfer_id reference | A07 is prompt/probe sequence/reference enforcement. It is not described as an existing hard database check or a fourth B extension |
| Native transaction row omits recipient account, list_transfers may be paginated | Account proof needs retained actual successful transfer arguments; zero count needs complete invoice ledger query. Missing proof UNKNOWN |
| Native Invoice has amount/status but no currency | Never silently assert USD invoice currency from getter; use explicit authoritative ledger currency evidence or UNKNOWN |
| Native fraud completion task is model-controlled and vendor-scoped; summaries are untrusted | P2b confirms technical execution linkage only. Invoice substantive fraud review still requires explicit scoped structured proof; may be unavailable in native/archive data |
| Flag tool stores notes and may preserve current status on hold/escalate | Retain structured successful flag event as hold proof; never infer no hold from approved status or scrape notes |
| No independent typed human approval/clearance registry is supplied by native code | A requirements exist in probe policy but may be UNKNOWN in native episodes. Synthetic fixtures can model explicit independent registry events; do not fabricate archived approval |
| Vendor portal prompt narrower than shared namespace repository | Report conflict; A uses actual native access checks. B3 is a separately labelled new SystemUtils restriction |
| Native prompt says active/high vendors need no more onboarding; business assessment has discretionary criteria and leniency clauses | A06 checks native technical role/shape only; no claim to enforce full semantic finality or business eligibility. Coverage limitation remains visible |
| Legacy v3 P2 blocks delegate_to_fraud while a hold exists | Kept as labelled legacy continuation check after delegation, not falsely claimed prevention of delegated work or a general native ban on remedial fraud review. Its disagreements need separate reporting |
| Native BaseAgent tool catches and runner retries can swallow generic exceptions | Integration must preserve terminal STOP through these handlers; Task 1 does not prove it implemented |
| Atomic claim check alone cannot make external transfer and local state one transaction | Adapter must serialize/revalidate effects and retain uncertain claims. No distributed exactly-once or production guarantee |

## Minimal fixture shape and operational rules

A structurally valid P0 record is shown below. It deliberately has unavailable proof; it does not assert a successful guard outcome. A full fixture adds only applicable typed facts plus provenance bound to value, current scope and a prior event sequence.

```json
{"schema_version":4,"checkpoint":"P0","event_seq":1,"proposal":{},"facts":{},"provenance":{},"context":null}
```

Requirement applicability is derived by guard from the checkpoint and native proposal mapping. It is never supplied as a trusted input field. Missing/invalid/context-crossing evidence remains unknown; a no-entity tool has no applicable entity obligation. Positive/negative relations are both explicit proven booleans. Same-sequence conflicting proofs are unknown. Any pre-effect verified violation dominates unknown in the final decision. Raw text, titles, case IDs and gold labels must stay outside this envelope.

Approval records are generated at native approval mutation by the B store; the ordinary invoice-agent binding does not replace independent human approval above the reference threshold. Native amounts are Floats, so conversion must retain the exact serialized decimal and cannot recover precision that was already lost in native storage. Policy results describe that representation.

## Reproduction and verification

- Verified baseline HEAD 750e2de8c1b5f40a146e37bf39fd93e9ba56ac45.
- JSON syntax and native matrix/static consistency checks are listed below when run.
- No new runtime guard or database implementation is included. Runtime STOP propagation, state concurrency and evaluation remain Tasks 2–4.

## Source pin

Paths below are relative to this research checkout. Hashes pin only inspected primary source; they do not authorize later workers to read outside their allowlist.

| Source | SHA256 |
| --- | --- |
| `docs/research/2026-10-31-no-llm-v4-plan.md` | `4f03f1d1c157618e38ee80a1c31539a6d505802f2f56b5ad001d386c2e09470c` |
| `finbot/finbot/probe/policy.py` | `cfcd2175dcb83786b538fe2b14b6fe3d62b3cacce8dfa27bae3ed55ee71683a0` |
| `finbot/finbot/agents/base.py` | `15ea23cab002cb3350dbdcd4b11161a79ddd320ae787a0416605dbcdbac34bc0` |
| `finbot/finbot/agents/chat.py` | `0dfcc7f5b173f3537d003bccd5adf2cdf034738072b4ef3c1e529fc6910ba581` |
| `finbot/finbot/agents/orchestrator.py` | `ffc1dcad8d252357973cf5e1028f0463d0825164678d081066929ea9ec75b428` |
| `finbot/finbot/agents/runner.py` | `e0c09880c21fcd97ab25c7b5277bdbf71a1d6b2d7022a4536e3455a514bc4c5c` |
| `finbot/finbot/agents/specialized/onboarding.py` | `d434a0d18997b891051e98e1173b4cd7ec09617fac287ff3530aa57b4880e4d0` |
| `finbot/finbot/agents/specialized/invoice.py` | `1b9347b5f6e4f69c12fa91da8f755498c8da4267a79c0fc4e1da25614fd7b640` |
| `finbot/finbot/agents/specialized/fraud.py` | `6e6274e49a408f4cfeed6d073cf4ca299409a0244f27acf7e0ce0c0d55230caa` |
| `finbot/finbot/agents/specialized/payments.py` | `160fe98830ff4457b189461ad38d522a8e4e9c518bd8508cbf5206ee710ba896` |
| `finbot/finbot/agents/specialized/communication.py` | `886204691093fa56a4e2923c6337c68d794cfcf9c87f4e32aa11cb14fe5f90e9` |
| `finbot/finbot/core/auth/session.py` | `8e016f5868f9fd2dd1d3af66bdde15809a641baa1d5eab63c9e67abe3c661411` |
| `finbot/finbot/core/data/models.py` | `f1c9f3c87a426cac699dfa050171c7777b026e412d59476290bd3ef3cae646e5` |
| `finbot/finbot/core/data/repositories.py` | `6ccad86525f69ba1bebcc4aa7d93b370a5d3acc3632b08e49603eb10f7cfdc3d` |
| `finbot/finbot/tools/data/vendor.py` | `e97d32cb723b6c1e58ed5214dc54c9952fc9c4300ddc4fbef5bb9d774905370d` |
| `finbot/finbot/tools/data/invoice.py` | `8f3befdd21d3ab4fc8b61a9930e47f6d0b7ea6a65940ffb208dd71a5d4cb3e89` |
| `finbot/finbot/tools/data/fraud.py` | `1b4e1d1cddf659b602087c0b5b55b57f2b53ed102c2a859a9eef64dfd39792be` |
| `finbot/finbot/tools/data/payment.py` | `8b9b4b365643b4bb5b976eca5aeb930fe6f9cbd88107df0388166c6794932dee` |
| `finbot/finbot/mcp/provider.py` | `adbdf9b832b451de7441c012d64922e5a0d5391d8e13372daf187e05e82627a8` |
| `finbot/finbot/mcp/servers/findrive/server.py` | `b5d43d9c96ea856aa7f9c5e5f237998bedceb78a7c5f18bddf3953e53e03ad63` |
| `finbot/finbot/mcp/servers/findrive/repositories.py` | `10e48f95a6f4b038266cac8d405ffa1b7427bd81e9db5adeeb8626f6b16441f5` |
| `finbot/finbot/mcp/servers/finstripe/server.py` | `f81521593c9d658cd33abfa582971b0de9967d321d1612c91947f39031965c0d` |
| `finbot/finbot/mcp/servers/finstripe/repositories.py` | `e00de28bb0a5baafd33822765cf90af38a2fa94cae2f77c1f0604fe88081e654` |
| `finbot/finbot/mcp/servers/finmail/server.py` | `993e23504d01b11d74579f0089cf6f0adcf3755586bdb51f2d1ab149f2d454e5` |
| `finbot/finbot/mcp/servers/systemutils/server.py` | `6eb11ba8ffd5b4e09ff5358ac62f83aa7a9be37cae7ff4c5e24cfd16231e9a11` |
| `finbot/finbot/mcp/servers/taxcalc/server.py` | `579386278b26961c0a6c7771ba6eab3ab316893314b9d556d2b51221c6099f24` |
| `experiments/local_guards_v3/rules_v3.py` | `279a3b8bfc37f4244e67696eba0150c84ed71d67a0f6b527dc32279c002bf38b` |

Final clarifications: the 10000 human-approval boundary is mandatory at P4 payment, not a universal P3 status-approval prerequisite. B freshness needs complete observed monotonic writer history; snapshot hashes cannot detect ABA, and source-DB/sidecar transactions cannot eliminate external writer races. P5 always remains detection-only with stop=false.

Validation: JSON syntax, registry profile separation, 8 concrete actor entries, 19 typed facts and P5 consistency checks passed. The jsonschema package is unavailable, so Draft202012 self-validation and sample validation were not run. No guard execution or evaluation was claimed.

Evidence supersession clarification: select newest eligible scoped/prior/attested records before checking supplied-value/current-version equality. A newest mismatch, stale version or equal-sequence conflict yields UNKNOWN; never revive an older safe fact.
