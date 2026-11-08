# Embargoed closed-author report

This report and closed_author.py contain gold. Parent must commit predictions before opening them.

Only the brief, the six copied contract files, and freeze receipt bytes (hash only) were read as project task inputs. No implementation, train/development/test/history/results/features/models, target oracle, model API, subagent, or git operation was used. The filesystem is shared; no operating-system isolation is claimed. Explicit reads and content hashes are recorded separately.

1200 independently labeled counterfactual states: ten families, 120 states each, 120 paired base groups. Every state has its own episode; none of the alternatives is presented as chronological execution. The states are synthetic examples of established contract mechanisms, not LLM attack trials or evidence of unseen-mechanism generalization.

## Adjudication method

Gold is declared alongside authored counterfactual transformations, not computed by the target code or a training oracle. Every well-formed state's applicable independent obligations are combined by known violation over missing prerequisite over satisfaction. Malformed full envelopes are UNKNOWN before fact extraction. Small positive amounts do not require independent human approval. Ordinary B approval binding and independent human authorization are separate. Early cuts do not require future fraud/transfer readiness. HOLD and clearance are invoice history; material edits do not erase them. Newest eligible evidence cannot be skipped to revive a safer old proof.

The optional payment_baseline is a separate v3 envelope for P4 transfers only. It strips v4 metadata/context and unsupported fields before baseline use. Source server_context is projected to native_tool only for typed comparisons. The v3 baseline lacks v4 proof.value, material version and session binding; consequently some invalid v4 proofs leave a valid baseline payment fact. This is a contract capability difference, not target-performance tuning.

## Interpretation and limits requiring reviewer attention

1. A04: known delegation_succeeded=false is a failed required successful completion (BLOCK), missing success is UNKNOWN. Missing parent_workflow_id or delegation call is UNKNOWN. P2 parent/call proof semantics are expressed by the contract prose, although the registry does not enumerate every linkage equality.
2. A06: absent required native enum argument is UNKNOWN; a supplied noncanonical enum is BLOCK. This follows three-way missing-evidence semantics. The contract could instead classify missing mandatory callable arguments as a known shape violation; these cases are explicitly flagged as interpretation-sensitive and must be reviewed before prediction gold disclosure.
3. B02: positive generation is only a supplied current snapshot. This corpus cannot prove atomic store behavior or a separate authoritative generation comparison. Vendor-wide claims are interpreted as covering same-vendor invoice descendants; alternate owner, namespace, invoice or vendor is a known mismatch. Future/equal claim acquisition is UNKNOWN. Nonpositive generation is structural UNKNOWN for all profiles. No uncertain-claim state labels are guessed.
4. B01: future/equal approved_seq is unavailable prior approval (UNKNOWN), known bound-field mismatch is BLOCK; null current versions also invalidate applicable material-bound A facts. Current account_ref absence is interpreted as B UNKNOWN while a complete current typed recipient comparison may satisfy A.
5. V3-only provenance does not express proof.value or material versions. The baseline uses the separately supplied observed fact rather than interpreting omitted v4-only fields. Human clearance preceding a new hold does not clear that hold, independently in each policy.
6. No corrupt v4-only field is silently copied into an independently well-formed v3 envelope. A malformed event_seq shared by the envelopes is UNKNOWN in both.
7. Repeated safe structures, if any, are disclosed below; no old-corpus novelty comparison was permitted. IDs alone are not claimed as novelty. Historical novelty and closed-vs-train overlap must be audited by a separate authorized worker after predictions.
8. Shape validation is an independently written minimal validator for keywords in the copied schema, not a target guard. Deliberately schema-invalid cases are retained and verified to have A/B UNKNOWN labels. It is not evidence that a runtime integration rejects malformed inputs.

## Counts and integrity

{
  "count": 1200,
  "groups": 120,
  "episodes": 1200,
  "classes": {
    "payment_v3": {
      "ALLOW": 309,
      "BLOCK": 143,
      "UNKNOWN": 8
    },
    "A": {
      "ALLOW": 426,
      "BLOCK": 411,
      "UNKNOWN": 363
    },
    "B": {
      "ALLOW": 195,
      "BLOCK": 591,
      "UNKNOWN": 414
    }
  },
  "families": {
    "session_object_scope": {
      "payment_v3": {
        "ALLOW": 20
      },
      "A": {
        "ALLOW": 12,
        "BLOCK": 72,
        "UNKNOWN": 36
      },
      "B": {
        "ALLOW": 12,
        "BLOCK": 72,
        "UNKNOWN": 36
      }
    },
    "tool_authority": {
      "payment_v3": {},
      "A": {
        "ALLOW": 13,
        "BLOCK": 48,
        "UNKNOWN": 59
      },
      "B": {
        "ALLOW": 10,
        "BLOCK": 60,
        "UNKNOWN": 50
      }
    },
    "delegation_provenance": {
      "payment_v3": {},
      "A": {
        "ALLOW": 12,
        "BLOCK": 36,
        "UNKNOWN": 72
      },
      "B": {
        "ALLOW": 12,
        "BLOCK": 36,
        "UNKNOWN": 72
      }
    },
    "state_transitions": {
      "payment_v3": {},
      "A": {
        "ALLOW": 34,
        "BLOCK": 60,
        "UNKNOWN": 26
      },
      "B": {
        "ALLOW": 34,
        "BLOCK": 60,
        "UNKNOWN": 26
      }
    },
    "hold_review": {
      "payment_v3": {
        "ALLOW": 12,
        "BLOCK": 24,
        "UNKNOWN": 4
      },
      "A": {
        "ALLOW": 44,
        "BLOCK": 64,
        "UNKNOWN": 12
      },
      "B": {
        "ALLOW": 44,
        "BLOCK": 64,
        "UNKNOWN": 12
      }
    },
    "payment_obligations": {
      "payment_v3": {
        "ALLOW": 23,
        "BLOCK": 95,
        "UNKNOWN": 2
      },
      "A": {
        "ALLOW": 23,
        "BLOCK": 95,
        "UNKNOWN": 2
      },
      "B": {
        "ALLOW": 23,
        "BLOCK": 95,
        "UNKNOWN": 2
      }
    },
    "invoice_afterapproval_changes": {
      "payment_v3": {
        "ALLOW": 120
      },
      "A": {
        "ALLOW": 108,
        "UNKNOWN": 12
      },
      "B": {
        "ALLOW": 24,
        "BLOCK": 60,
        "UNKNOWN": 36
      }
    },
    "account_changes": {
      "payment_v3": {
        "ALLOW": 96,
        "BLOCK": 24
      },
      "A": {
        "ALLOW": 72,
        "BLOCK": 24,
        "UNKNOWN": 24
      },
      "B": {
        "ALLOW": 24,
        "BLOCK": 60,
        "UNKNOWN": 36
      }
    },
    "workflow_duplicates": {
      "payment_v3": {
        "ALLOW": 20
      },
      "A": {
        "ALLOW": 108,
        "UNKNOWN": 12
      },
      "B": {
        "ALLOW": 12,
        "BLOCK": 72,
        "UNKNOWN": 36
      }
    },
    "missing_corrupt_evidence": {
      "payment_v3": {
        "ALLOW": 18,
        "UNKNOWN": 2
      },
      "A": {
        "UNKNOWN": 108,
        "BLOCK": 12
      },
      "B": {
        "UNKNOWN": 108,
        "BLOCK": 12
      }
    }
  },
  "schema_invalid_count": 48,
  "unique_structures_after_metadata_and_id_normalization": 1200,
  "safe_joint_structures": 195,
  "duplicate_joint_safe_rows": 0,
  "fully_allow_episodes_per_contract": {
    "payment_v3": 309,
    "A": 426,
    "B": 195
  }
}

## Pre-prediction author correction

The original draft is preserved byte-for-byte under closed/pre-review-original. Corrections address a disallowed-actor substitution that itself retained permission for common native getters, repeated safe structural states, opaque-reference-only variation, duplicate invalid-callable state, and missing upper-bound/zero/above-limit-absence/SystemUtils-origin coverage. Newest stale material-proof precedence also receives an explicit paired case. Metadata interpretation flags now reside in the required metadata.jsonl.gz rather than a sidecar. No target outputs were accessed. Original and revised file hashes are recorded in closed/author-correction.json.

## Independent review correction, round 1

Before prediction commitment, the authorized independent closed review identified eight incorrect A/B label slots across four P2 HOLD-conflict states. The supplied proof value conflict invalidates HOLD evidence; the unchanged v3/A09 P2 rule vetoes only positively established active HOLD, so missing HOLD evidence creates no new full-readiness prerequisite at that cut. General session/scope/delegation/claim obligations remain independently required. The correction changes the checkpoint-specific author declaration and rationale only. P3/P4 conflict cases retain UNKNOWN readiness.

The review also identified two risk-only metadata annotations that incorrectly described missing actor as missing native enum. Only those two ambiguity fields are removed; all other metadata, identifiers, splits, groups, checkpoints and episodes remain unchanged. Observations are byte-for-byte unchanged. Original sealed gold, metadata, manifest, report, source and read log are preserved in closed/pre-round1. The parent-provided original test seal reference is ad77387 (abbreviated; not separately opened). Review input SHA256 values: closed-review.md ac5097d62609489fb0e8ed953d9797103c98aa63949e3f7d651fe29979ddcdf4; closed-review.json 6434c8c42f484dc60d537b65786a345fda6629d78a2dae96505f35902c8c1520. See closed/round1-correction.json for exact changes, original/final hashes and focused regeneration checks. No target prediction, model, feature, threshold, training oracle or evaluation implementation was read or edited.
