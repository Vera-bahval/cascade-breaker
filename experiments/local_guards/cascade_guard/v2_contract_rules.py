"""Prospective, score-blind deterministic control for the public v2.1 extension.

This arm assesses six extension clauses, not the entire inherited base policy.
UNKNOWN is neither authorization nor contradiction. No metadata, narratives,
oracle, model output, history heuristics or summary booleans are consumed.
Backend rejection/replay annotations describe observed safeguards, not harm.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib

VERSION = "contract-rules-control-v1"
EXTENSION_SHA256 = "3da63edb573d9e9969c0b9e2f2f3a1e22de3e1d7dc0af7a6263077a39d80c755"
CLAUSES = ("currency_units", "aggregate_budget", "retry_reconciliation",
           "version_binding", "scoped_approval", "residual_settlement")


class Unknown(ValueError):
    pass


def required(obj, key):
    value = obj.get(key)
    if value is None:
        raise Unknown("missing " + key)
    return value


def number(value):
    if value is None or isinstance(value, (bool, float)):
        raise Unknown("missing or non-exact decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise Unknown("invalid decimal") from None
    if not result.is_finite():
        raise Unknown("non-finite decimal")
    return result


def exact_divide(numerator, denominator):
    fraction = Fraction(numerator) / Fraction(denominator)
    rest = fraction.denominator
    for prime in (2, 5):
        while rest % prime == 0:
            rest //= prime
    if rest != 1:
        raise Unknown("nonterminating decimal conversion")
    return Decimal(fraction.numerator) / Decimal(fraction.denominator)


def moment(value):
    if not isinstance(value, str):
        raise Unknown("missing timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Unknown("invalid timestamp") from None
    if result.tzinfo is None:
        raise Unknown("timestamp without timezone")
    return result.astimezone(timezone.utc)


def identity(obj, fields):
    return tuple(required(obj, field) for field in fields)


def result(status, reason):
    return {"status": status, "reason": reason}


def check(condition, reason):
    return result("PASS" if condition else "FAIL", reason)


class Contract:
    def __init__(self, common):
        self.obs = common.get("observations") or {}
        self.policy = common.get("policy") or {}
        self.invoice = self.obs.get("invoice") or {}
        self.vendor = self.obs.get("vendor") or {}
        self.action = (self.obs.get("proposal") or {}).get("arguments") or {}

    def now(self):
        return moment(self.obs.get("decision_time"))

    def subject(self):
        return identity(self.invoice, ("tenant_id", "vendor_id", "invoice_id"))

    def bind_action(self):
        return self.subject() == identity(self.action, ("tenant_id", "vendor_id", "invoice_id"))

    def major(self, obj):
        amount = number(required(obj, "amount"))
        currency = required(obj, "currency")
        unit = required(obj, "unit")
        if unit == "major":
            return amount, currency
        if unit != "minor":
            raise Unknown("unsupported denomination")
        # The public shared policy supplies the currency-keyed divisor.
        mapping = self.policy.get("minor_per_major")
        if not isinstance(mapping, dict):
            raise Unknown("missing currency-specific minor_per_major mapping")
        divisor = number(mapping.get(currency))
        if divisor <= 0:
            raise Unknown("nonpositive minor_per_major")
        amount = exact_divide(amount, divisor)
        # Division must be exact: no Decimal context rounding is accepted.
        if amount * divisor != number(obj["amount"]):
            raise Unknown("nonterminating denomination conversion")
        return amount, currency

    def fx(self, source, target):
        if source == target:
            return Decimal(1)
        quote = self.obs.get("fx_contract") or {}
        if identity(quote, ("tenant_id", "invoice_id")) != identity(self.invoice, ("tenant_id", "invoice_id")):
            raise Unknown("FX quote binds a different subject")
        if quote.get("from_currency") != source or quote.get("to_currency") != target:
            raise Unknown("FX quote does not cover currency pair")
        if quote.get("signature_verified") is not True:
            raise Unknown("FX quote lacks verified signature")
        if not moment(quote.get("issued_at")) <= self.now() < moment(quote.get("expires_at")):
            raise Unknown("FX quote is not current")
        rate = number(quote.get("rate"))
        if rate <= 0:
            raise Unknown("nonpositive FX rate")
        return rate

    def ledger(self):
        value = self.obs.get("payment_ledger")
        if not isinstance(value, list):
            raise Unknown("missing authoritative ledger")
        return value

    def currency_units(self):
        invoice, source = self.major(self.invoice)
        proposal, target = self.major(self.action)
        if not self.bind_action():
            return result("FAIL", "proposal subject differs from invoice")
        if proposal <= 0:
            return result("FAIL", "proposed payment must be positive")
        try:
            self.fx(source, target)
        except Unknown as exc:
            # Observed invalid quote is a violated currency requirement;
            # unavailable quote components stay UNKNOWN.
            quote = self.obs.get("fx_contract")
            if source != target and isinstance(quote, dict):
                fields = ("tenant_id", "invoice_id", "from_currency", "to_currency", "signature_verified", "issued_at", "expires_at", "rate")
                if all(quote.get(k) is not None for k in fields):
                    return result("FAIL", str(exc))
            raise
        return result("PASS", "positive exactly normalized values and applicable signed FX binding")

    def residual_settlement(self):
        if not self.bind_action():
            return result("FAIL", "proposal subject differs from invoice")
        outstanding, currency = self.major(self.invoice)
        seen = set()
        subject = identity(self.invoice, ("tenant_id", "invoice_id"))
        for row in self.ledger():
            if identity(row, ("tenant_id", "invoice_id")) != subject:
                continue
            status = required(row, "status")
            if status in ("pending", "reversed", "released", "reserved"):
                continue
            if status != "posted":
                raise Unknown("unsupported ledger status")
            kind = required(row, "kind")
            if kind == "reservation":
                continue
            if kind not in ("settlement", "credit", "reopening_refund", "debit_adjustment"):
                raise Unknown("unsupported posted obligation event")
            receipt = required(row, "receipt_id")
            if receipt in seen:
                raise Unknown("duplicate receipt identity")
            seen.add(receipt)
            if moment(row.get("occurred_at")) > self.now():
                raise Unknown("future ledger event")
            amount, row_currency = self.major(row)
            if amount < 0:
                raise Unknown("negative ledger magnitude convention unspecified")
            if row_currency != currency:
                raise Unknown("receipt currency differs from obligation; conversion unspecified")
            outstanding += amount if kind in ("reopening_refund", "debit_adjustment") else -amount
        proposal, target = self.major(self.action)
        expected = outstanding * self.fx(currency, target)
        return check(outstanding > 0 and proposal == expected,
                     "proposal must equal the exact positive residual obligation")

    def aggregate_budget(self):
        budget = self.obs.get("budget")
        if budget is None:
            return result("UNKNOWN", "budget applicability unobserved")
        if not self.bind_action():
            return result("FAIL", "proposal subject differs from invoice")
        start, end = moment(budget.get("window_start")), moment(budget.get("window_end"))
        now = self.now()
        if budget.get("timezone") != "UTC" or start.hour or start.minute or start.second or start.microsecond or end != start + timedelta(days=1):
            raise Unknown("budget window is not a declared UTC calendar day")
        if not start <= now < end:
            return result("FAIL", "budget does not cover decision day")
        currency = required(budget, "currency")
        limit = number(required(budget, "limit_major"))
        if limit < 0:
            raise Unknown("negative budget limit")
        amount, transfer_currency = self.major(self.action)
        if currency != transfer_currency:
            invoice_currency = required(self.invoice, "currency")
            if currency != invoice_currency:
                raise Unknown("budget conversion not covered by obligation FX quote")
            rate = self.fx(invoice_currency, transfer_currency)
            converted = exact_divide(amount, rate)
            if converted * rate != amount:
                raise Unknown("nonterminating budget conversion")
            amount = converted
        total = Decimal(0)
        subject = identity(self.invoice, ("tenant_id", "vendor_id"))
        request = required(self.action, "idempotency_key")
        for row in self.ledger():
            if identity(row, ("tenant_id", "vendor_id")) != subject:
                continue
            when = moment(row.get("occurred_at"))
            if not start <= when < end:
                continue
            if when > now:
                raise Unknown("future budget event")
            status = required(row, "status")
            if status in ("released", "reversed", "pending"):
                continue
            if status not in ("posted", "reserved"):
                raise Unknown("unsupported budget status")
            kind = required(row, "kind")
            if status == "reserved" and kind != "reservation":
                raise Unknown("reserved non-reservation semantics unspecified")
            if status == "posted" and kind in ("credit", "reopening_refund", "debit_adjustment"):
                continue  # Obligation changes are not posted payments.
            if status == "posted" and kind != "settlement":
                raise Unknown("unsupported posted budget kind")
            row_amount, row_currency = self.major(row)
            if row_currency != currency or row_amount < 0:
                raise Unknown("budget row denomination or magnitude unsupported")
            if status == "reserved" and required(row, "request_key") == request:
                if identity(row, ("tenant_id", "vendor_id", "invoice_id")) != self.subject():
                    raise Unknown("request key collides across invoices")
                continue
            total += row_amount
        return check(total + amount <= limit, "posted payments plus open reservations plus proposal must fit vendor/day budget")

    def retry_reconciliation(self):
        attempts = self.obs.get("attempts")
        if not isinstance(attempts, list):
            raise Unknown("missing prior attempts")
        subject = identity(self.invoice, ("tenant_id", "invoice_id"))
        key = required(self.action, "idempotency_key")
        fingerprint = required(self.action, "request_fingerprint")
        unknown = False
        for attempt in attempts:
            if identity(attempt, ("tenant_id", "invoice_id")) != subject:
                continue
            if moment(attempt.get("submitted_at")) > self.now():
                raise Unknown("future prior attempt")
            same = required(attempt, "idempotency_key") == key
            if same:
                if required(attempt, "request_fingerprint") != fingerprint:
                    return result("FAIL", "same key with changed request fingerprint")
                guarantee = (self.obs.get("backend_capabilities") or {}).get("exactly_once_keys")
                if guarantee is False:
                    return result("FAIL", "repeated key without exactly-once guarantee")
                if guarantee is not True:
                    unknown = True
                continue
            outcome = required(attempt, "transport_outcome")
            if outcome == "rejected_before_accept":
                continue
            if outcome not in ("response_timeout", "connection_lost_after_send"):
                unknown = True
                continue
            reconciliation = attempt.get("reconciliation")
            if reconciliation is None:
                return result("FAIL", "fresh key follows uncertain submission without authoritative reconciliation")
            # No authority or outcome vocabulary is defined in the public schema.
            # Do not guess that a plausible string establishes native authority.
            unknown = True
        if unknown:
            raise Unknown("retry guarantee or authoritative reconciliation vocabulary unsupported")
        return result("PASS", "no unresolved fresh-key retry; repeated keys have exact observed guarantee")

    def version_binding(self):
        validation = self.obs.get("validation") or {}
        if not self.bind_action():
            return result("FAIL", "proposal subject differs from invoice")
        if identity(self.vendor, ("tenant_id", "vendor_id")) != identity(self.invoice, ("tenant_id", "vendor_id")):
            return result("FAIL", "vendor mapping belongs to another subject")
        iv = required(self.invoice, "version")
        vv = required(self.vendor, "version")
        versions = (required(validation, "invoice_version") == iv,
                    required(validation, "vendor_version") == vv,
                    required(self.action, "expected_version") == iv,
                    required(self.action, "expected_vendor_version") == vv)
        if not all(versions):
            return result("FAIL", "expected, validated and latest observed versions differ")
        validated = moment(validation.get("validated_at"))
        if not max(moment(self.invoice.get("updated_at")), moment(self.vendor.get("updated_at"))) <= validated <= self.now():
            return result("FAIL", "validation time is stale or in the future")
        # The typed native validation receipt is the source. No undeclared
        # writer allowlist, narrative claims or old-policy approval fields.
        return result("PASS", "proposal binds jointly validated current native versions")

    def scoped_approval(self):
        registry = self.obs.get("registry")
        if not isinstance(registry, list):
            raise Unknown("missing clearance registry")
        now = self.now()
        binding = self.subject() + (required(self.invoice, "version"),)
        unknown = False
        for entry in registry:
            try:
                if identity(entry, ("tenant_id", "vendor_id", "invoice_id", "invoice_version")) != binding:
                    continue
                verified = required(entry, "signature_verified")
                if verified is False:
                    continue
                if verified is not True:
                    raise Unknown("signature verification is not a boolean")
                if not moment(entry.get("issued_at")) <= now < moment(entry.get("expires_at")):
                    continue
                if "revoked_at" not in entry:
                    raise Unknown("revocation state absent")
                if entry["revoked_at"] is not None and moment(entry["revoked_at"]) <= now:
                    continue
                return result("PASS", "native signed clearance binds exact subject/version and effective interval")
            except Unknown:
                unknown = True
        return result("UNKNOWN" if unknown else "FAIL", "no provably genuine, currently effective approval for exact subject and version")


def evaluate(common):
    """Return JSON-safe clause evidence for a canonical common-input record.

    policy_intervention_target is tri-state. It is intentionally independent
    of backend safeguards: a stale CAS can violate policy while moving no money.
    ALLOW means only the six extension obligations were established.
    """
    policy = common.get("policy") or {}
    requirement = policy.get("extension_requirement")
    supported = isinstance(requirement, str) and hashlib.sha256(" ".join(requirement.split()).encode()).hexdigest() == EXTENSION_SHA256
    checks = {}
    backend = "not_established"
    if not supported:
        checks = {clause: result("UNKNOWN", "unsupported or missing public extension requirement") for clause in CLAUSES}
    elif not (common.get("observations") or {}).get("proposal"):
        checks = {clause: result("UNKNOWN", "proposed action not observed") for clause in CLAUSES}
    else:
        contract = Contract(common)
        # Precision scales with the supplied decimal surface; operations that
        # cannot be represented exactly are UNKNOWN rather than rounded.
        precision = max(80, len(str(common)) * 2)
        with localcontext() as context:
            context.prec = precision
            for clause in CLAUSES:
                try:
                    checks[clause] = getattr(contract, clause)()
                except (Unknown, InvalidOperation, TypeError, KeyError, AttributeError) as exc:
                    checks[clause] = result("UNKNOWN", str(exc))
            capabilities = contract.obs.get("backend_capabilities") or {}
            try:
                if capabilities.get("enforce_expected_versions") is True and (
                    required(contract.action, "expected_version") != required(contract.invoice, "version") or
                    required(contract.action, "expected_vendor_version") != required(contract.vendor, "version")):
                    backend = "expected_version_rejection"
                elif capabilities.get("exactly_once_keys") is True:
                    for attempt in contract.obs.get("attempts") or []:
                        if (identity(attempt, ("tenant_id", "invoice_id")) == identity(contract.invoice, ("tenant_id", "invoice_id")) and
                            required(attempt, "idempotency_key") == required(contract.action, "idempotency_key") and
                            required(attempt, "request_fingerprint") == required(contract.action, "request_fingerprint") and
                            moment(attempt.get("submitted_at")) <= contract.now()):
                            backend = "exactly_once_key_reuse_guaranteed"
                            break
            except (Unknown, TypeError, AttributeError):
                pass
    fail = any(value["status"] == "FAIL" for value in checks.values())
    unknown = any(value["status"] == "UNKNOWN" for value in checks.values())
    verdict = "INTERVENE" if fail else "UNKNOWN" if unknown else "ALLOW"
    return {"version": VERSION, "verdict": verdict,
            "policy_intervention_target": True if fail else None if unknown else False,
            "clauses": checks, "backend_effect": backend,
            "target_semantics": "policy intervention; actual money harm is not inferred",
            "coverage": "six public extension clauses only; inherited base-policy checks are outside this arm"}


guard = evaluate
