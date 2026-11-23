"""Report the additional Rules replica separately from the three assigned cells."""
from unittest.mock import patch

from . import compatible, compatible_readout, compatible_rules_recovery, live

CASE = compatible.CASE
INITIAL = compatible.RUNTIME
REPLICA = compatible_rules_recovery.REPLICA


def collect():
    manifest = compatible.load_frozen()

    def episode(case, arm):
        return (REPLICA if arm == "rules" else INITIAL) / f"{case}--{arm}"

    with (patch.object(live, "PRIVATE", compatible.PRIVATE), patch.object(live, "RUNTIME", REPLICA),
          patch.object(live, "episode", episode), patch.object(live.pilot, "episode_path", episode)):
        recovery = live.results(manifest)
    assert all(not row["requests"] for row in recovery["unattributed"].values())
    rules, = [row for row in recovery["rows"] if row["arm"] == "rules"]
    rules["series"] = "compatible-rental-secondary-rules-replica"
    initial = compatible_readout.collect()
    totals = {name: {key: initial["new_billing"][name][key] + recovery["new_billing"][name][key]
                     for key in initial["new_billing"][name]} for name in ("eliza", "jev")}
    assert recovery["new_billing"]["jev"]["requests"] == 0
    assert all(values["billed_usd"] + values["pending_reserve_usd"] <= manifest["caps"][name + "_usd"]
               for name, values in totals.items())
    complete = rules["workflows"] is not None
    first_db = INITIAL / f"{CASE}--rules" / "finbot.db"
    replica_db = episode(CASE, "rules") / "finbot.db"
    initial_transfers = live.live_audit.query(first_db,
        "SELECT namespace,transfer_id FROM payment_transactions WHERE status='completed'")
    replica_transfers = live.live_audit.query(replica_db,
        "SELECT namespace,transfer_id FROM payment_transactions WHERE status='completed'")
    if complete:
        first, = initial_transfers
        second, = replica_transfers
        assert first["namespace"] != second["namespace"] and first["transfer_id"] != second["transfer_id"]
    hybrid, = [row for row in initial["rows"] if row["arm"] == "hybrid"]
    comparison = ({"hybrid_minus_replica_usd": hybrid["usd"] - rules["usd"],
                   "hybrid_minus_replica_wall_seconds": hybrid["wall_seconds"] - rules["wall_seconds"],
                   "scope": "Three independent trajectories on the same catalogue task, with Rules restarted once."}
                  if complete else None)
    return dict(assigned_triplet=3, assigned_complete=initial["observed_complete_oracles"],
                secondary_rules_replica=rules, replica_billing=recovery["new_billing"],
                total_billing_including_replica=totals, original_caps=manifest["caps"],
                reduced_executor_cap_usd=live.load(REPLICA/"authorization.json")["remaining_executor_cap_usd"],
                replica_transfer_distinct_from_original=True if complete else None,
                completed_task_descriptive_comparison=comparison)


if __name__ == "__main__":
    live.dump(live.HERE / "compatible_rules_replica_results.json", collect())
