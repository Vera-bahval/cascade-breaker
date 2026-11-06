"""Agent Runner"""

import asyncio
import contextlib
import logging
import os
import secrets
from typing import Any, Type

from finbot.agents.base import BaseAgent
from finbot.agents.orchestrator import OrchestratorAgent
from finbot.agents.specialized.communication import CommunicationAgent
from finbot.agents.specialized.fraud import FraudComplianceAgent
from finbot.agents.specialized.invoice import InvoiceAgent
from finbot.agents.specialized.onboarding import VendorOnboardingAgent
from finbot.agents.specialized.payments import PaymentsAgent
from finbot.core.auth.session import SessionContext
from finbot.config import settings
from finbot.core.messaging import event_bus
from finbot.probe import trace as probe_trace

logger = logging.getLogger(__name__)


async def run_agent_with_retry(
    agent_class: Type[BaseAgent],
    session_context: SessionContext,
    task_data: dict,
    max_retries: int = 3,
    workflow_id: str | None = None,
) -> dict:
    """Run an agent with automatic retry on failure
    Args:
        agent_class: The class of the agent to instantiate
        session_context: The session context from the request
        task_data: The task data to pass on to the agent
        max_retries: The maximum number of retries
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    workflow_id = workflow_id or f"wf_{secrets.token_urlsafe(12)}"
    for attempt in range(max_retries):
        try:
            agent = agent_class(
                session_context=session_context,
                workflow_id=workflow_id,
            )
            result = await agent.process(task_data=task_data)

            logger.info(
                "Agent %s completed (workflow=%s): %s",
                agent.agent_name,
                workflow_id,
                result.get("task_summary", ""),
            )

            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(
                "Agent %s attempt %d/%d failed: %s",
                agent.agent_name,
                attempt + 1,
                max_retries,
                e,
                exc_info=True,
            )
            if attempt < max_retries - 1:
                retry_delay = 2**attempt
                # Emit retry event
                await event_bus.emit_agent_event(
                    agent_name=agent.agent_name,
                    event_type="agent_retry",
                    event_subtype="error",
                    event_data={
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "retry_delay_seconds": retry_delay,
                    },
                    session_context=session_context,
                    workflow_id=workflow_id,
                    summary=f"Agent retry {attempt + 1}/{max_retries}: {type(e).__name__}",
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.critical(
                    "Agent %s permanently failed after %d attempts",
                    agent.agent_name,
                    max_retries,
                )
                await event_bus.emit_business_event(
                    event_type="agent.failed",
                    event_subtype="error",
                    event_data={
                        "agent_name": agent.agent_name,
                        "workflow_id": workflow_id,
                        "error": str(e),
                        "task_data": task_data,
                    },
                    session_context=session_context,
                    workflow_id=workflow_id,
                    summary=f"Agent failed permanently: {agent.agent_name} ({type(e).__name__})",
                )
                return {
                    "task_status": "failed",
                    "task_summary": f"Agent {agent.agent_name} permanently failed after {max_retries} attempts: {str(e)}",
                }
    return {
        "task_status": "failed",
        "task_summary": f"Agent {agent.agent_name} failed due to unknown reason",
    }


async def run_onboarding_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the onboarding agent for a vendor
    Args:
        task_data: The task data to pass on to the agent
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    return await run_agent_with_retry(
        agent_class=VendorOnboardingAgent,
        session_context=session_context,
        task_data=task_data,
        workflow_id=workflow_id,
    )


async def run_invoice_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the invoice agent for an invoice
    Args:
        task_data: The task data to pass on to the agent
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    return await run_agent_with_retry(
        agent_class=InvoiceAgent,
        session_context=session_context,
        task_data=task_data,
        workflow_id=workflow_id,
    )


async def run_payments_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the payments agent for payment processing
    Args:
        task_data: The task data to pass on to the agent
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    return await run_agent_with_retry(
        agent_class=PaymentsAgent,
        session_context=session_context,
        task_data=task_data,
        workflow_id=workflow_id,
    )


async def run_fraud_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the fraud/compliance agent for risk assessment
    Args:
        task_data: The task data to pass on to the agent
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    return await run_agent_with_retry(
        agent_class=FraudComplianceAgent,
        session_context=session_context,
        task_data=task_data,
        workflow_id=workflow_id,
    )


def _guard_db_snapshot(session_context: SessionContext, invoice_id: Any, vendor_id: Any) -> dict:
    """DB snapshot in the shape the probe verifiers expect (current invoice, vendor,
    transactions with vendor_id). Read live from the server's database per workflow."""
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import InvoiceRepository, VendorRepository
    from finbot.mcp.servers.finstripe.models import PaymentTransaction

    with db_session() as db:
        vendor = VendorRepository(db, session_context).get_vendor(vendor_id) if vendor_id else None
        inv = InvoiceRepository(db, session_context).get_invoice(invoice_id) if invoice_id else None
        txns = (
            db.query(PaymentTransaction)
            .filter(PaymentTransaction.namespace == session_context.namespace,
                    PaymentTransaction.vendor_id == vendor_id)
            .all()
            if vendor_id else []
        )
        return {
            "invoice": inv.to_dict() if inv else {},
            "vendor": vendor.to_dict() if vendor else {},
            "transactions": [
                {"transfer_id": t.transfer_id, "invoice_id": t.invoice_id, "amount": t.amount,
                 "status": t.status, "vendor_id": vendor_id}
                for t in txns
            ],
        }


def _maybe_open_guard(workflow_id: str, task_data: dict, session_context: SessionContext):
    """Open an enforcing guard runtime from PROBE_ENFORCE (e.g. "P4=V3"), covering api
    and chat workflows. Returns a no-op when unset or when direct already opened one."""
    from finbot.probe.guards import runtime as probe_guards

    if probe_guards.active_runtime() is not None:
        return contextlib.nullcontext()
    spec = os.environ.get("PROBE_ENFORCE", "").strip()
    if not spec:
        return contextlib.nullcontext()
    from finbot.probe.guards.invariants import InvariantVerifier, TextRuleVerifier
    from finbot.probe.guards.llm import ConsistencyVerifier, MastAnnotator, SelfConsistencyVerifier

    registry = {"V1": InvariantVerifier, "V2": TextRuleVerifier, "V3": ConsistencyVerifier,
                "V4": SelfConsistencyVerifier, "V5": MastAnnotator}
    enforce: dict[str, str] = {}
    for pair in spec.split(","):
        point, _, name = pair.partition("=")
        point, name = point.strip(), name.strip()
        if point and name:
            enforce[point] = name
    verifiers = [registry[n]() for n in set(enforce.values()) if n in registry]
    if not verifiers:
        return contextlib.nullcontext()
    vid, iid = task_data.get("vendor_id"), task_data.get("invoice_id")
    runtime = probe_guards.GuardRuntime(
        mode="enforce", run_id=workflow_id, verifiers=verifiers,
        snapshot=lambda: _guard_db_snapshot(session_context, iid, vid), enforce=enforce)
    return probe_guards.open_runtime(runtime)


async def run_orchestrator_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the orchestrator agent to coordinate a multi-agent workflow.
    Args:
        task_data: Must contain 'description'. May include vendor_id, invoice_id, etc.
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Synthesized result from all delegated agents
    """
    workflow_id = workflow_id or f"wf_{secrets.token_urlsafe(12)}"
    with probe_trace.record_to_dir(settings.PROBE_TRACE_DIR, workflow_id, task_data=task_data):
        with _maybe_open_guard(workflow_id, task_data, session_context):
            return await run_agent_with_retry(
                agent_class=OrchestratorAgent,
                session_context=session_context,
                task_data=task_data,
                workflow_id=workflow_id,
            )


async def run_communication_agent(
    task_data: dict,
    session_context: SessionContext,
    workflow_id: str | None = None,
) -> dict:
    """Run the communication agent for sending notifications
    Args:
        task_data: The task data to pass on to the agent
        session_context: The session context from the request
        workflow_id: Optional workflow id
    Returns:
        Agent execution result
    """
    return await run_agent_with_retry(
        agent_class=CommunicationAgent,
        session_context=session_context,
        task_data=task_data,
        workflow_id=workflow_id,
    )
