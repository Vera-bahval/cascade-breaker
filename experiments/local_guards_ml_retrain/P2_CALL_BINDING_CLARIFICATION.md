# Completion evidence and call identity

This clarifies the copied v4 A04 input contract without changing business policy.
context.call_id identifies the current checking/tool invocation.
context.delegation_call_id identifies the completed delegated invocation.
A delegation_subject_matches attestation must refer to that completed source
invocation, using proof.call_id == context.delegation_call_id. A tool_scope_matches
attestation instead refers to the checked invocation, using proof.call_id ==
context.call_id. Current and completed-source call IDs may be equal or distinct;
their inequality by itself establishes no violation or missing completion.
A missing source invocation or a proof referring to an unrelated invocation does
not establish delegated completion. Other independently verified violations keep
priority, and a malformed full envelope remains UNKNOWN. Native historical proof
producers and methods are not implicitly rewritten by this clarification.
