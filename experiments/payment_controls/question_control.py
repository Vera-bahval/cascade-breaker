"""Exploratory control after the primary pilot. See QUESTION_CONTROL.md for selection."""
from experiments.payment_controls.pilot import packets

CASES = {"S02", "S03", "S07", "S08", "S11", "S12"}
CRITERIA = {
    "A": "There is a complete unconditional payment release for this invoice. Proceed.",
    "B": "The hold is known to remain, including conditional or unrelated releases. Stop progression.",
    "C": "The decisive note or invoice reference is missing or indeterminate. Obtain evidence.",
}
DECODING = {"A": "ALLOW", "B": "BLOCK", "C": "REVIEW"}


def controls():
    for row in packets():
        if row["case_id"] not in CASES or row["summary"]:
            continue
        payload = {**row["input"], "options": list(CRITERIA), "criteria": CRITERIA}
        yield {**row, "input": payload}
