# Independent sealed test review

Status: PASS. Independently adjudicated 320 P4 episodes, 160 pairs and 8 families against the frozen contract, without inspecting or invoking target methods.

Integrity findings: 0. The independent checker validates all gold decisions, typed nullable fields, current-subject provenance before the cut, human proof source and exact-hold chronology, minimal paired treatment, model-field isolation and null synthetic outcomes. Scratch seed 17731 regeneration is byte-identical: True.

TRAIN/CAL overlap: 15609 old input rows compared; exact complete model-view matches: 0; matches after decimal normalization: 0; matching contract states after excluding untrusted text: 0. Identity fields are excluded from every comparison. Shared policy capability does not by itself establish leakage.

Internal model-input diversity: 233 unique views across 320 episodes; 56 duplicate sets; 0 contradictory-label sets. Repeated views are valid paired contract cases, but 320 distinct episode IDs do not imply 320 distinct model inputs or independent observations. Analysis should retain pair/group clustering and acknowledge repeated views.

Manifest SHA256: `d959869b85d440de74b59e8e3b186ab6ccf0855db1fb8179841b41f6e06bca13`. Payload hashes are in review.json. Sealed input bytes were unchanged. Detailed adjudications, proof issues and overlap pointers remain in review.json and must remain hidden from method authors until prediction freeze.
