"""Create the guardrail config row for the demo user (all 4 hooks on, webhook -> local receiver)."""
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import cascade_failure_demo as demo
from finbot.core.data.database import db_session
from finbot.core.data.repositories import LabsGuardrailConfigRepository
s = demo._build_session()
with db_session() as db:
    cfg, created = LabsGuardrailConfigRepository(db, s).upsert(
        webhook_url="http://127.0.0.1:8765/hook",
        hooks={"before_model": True, "after_model": True, "before_tool": True, "after_tool": True},
        timeout_seconds=5, enabled=True)
    print("config", "created" if created else "updated", cfg.namespace, cfg.user_id, cfg.webhook_url, cfg.get_hooks())
