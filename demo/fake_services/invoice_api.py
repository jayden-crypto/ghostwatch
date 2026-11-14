"""A fake accounts-payable system: validates invoices and accepts submissions."""

from __future__ import annotations

from fake_services.timing import timing


class ValidationUnavailable(Exception):
    """The validation service is down."""


class InvoiceApi:
    """With `validation_outage=True`, `validate` raises as a real dependency would during an outage."""

    def __init__(self, validation_outage: bool = False, latency: float = 0.2) -> None:
        self.validation_outage = validation_outage
        self.latency = latency
        self.submitted: list[str] = []  # invoice numbers actually submitted: the real side effect

    def validate(self, invoice: dict) -> dict:
        timing.wait(self.latency)
        if self.validation_outage:
            raise ValidationUnavailable("validation service returned HTTP 503")
        problems = []
        if invoice["total"] <= 0:
            problems.append("total must be positive")
        if not invoice["vendor"]:
            problems.append("vendor is missing")
        return {"valid": not problems, "problems": problems}

    def submit(self, invoice: dict) -> dict:
        timing.wait(self.latency * 1.5)
        self.submitted.append(invoice["invoice_number"])
        return {"submission_id": f"SUB-{invoice['invoice_number']}", "status": "accepted"}
