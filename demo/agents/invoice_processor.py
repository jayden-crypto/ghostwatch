"""Invoice Processor: extract_fields -> validate -> submit_invoice.

Demo scenario "ghost-invoice": the validation service is down. The agent swallows that error,
never calls submit_invoice, and still reports success. Ghostwatch flags the ghost completion.
"""

import ghostwatch as gw

from fake_services.invoice_api import InvoiceApi, ValidationUnavailable

AGENT = gw.Agent(
    slug="invoice-processor",
    name="Invoice Processor",
    description="Extracts invoice fields, validates them and submits the invoice for payment.",
    framework="custom",
)
CONFIG = {"model": None, "expected_steps": ["extract_fields", "validate", "submit_invoice"]}

invoices = InvoiceApi()


@gw.tool(side_effects=True)
def submit_invoice(invoice: dict) -> dict:
    return invoices.submit(invoice)


def extract_fields(document: str) -> dict:
    """Parse the 'Key: value' lines of an invoice document."""
    fields = dict(line.split(": ", 1) for line in document.splitlines() if ": " in line)
    return {
        "invoice_number": fields["Invoice"],
        "vendor": fields["Vendor"],
        "total": float(fields["Total"]),
        "currency": fields["Currency"],
    }


def run(input: dict) -> dict:
    with gw.execution(input=input, config=CONFIG, tags=["demo"]) as execution:
        with execution.step("extract_fields", type="reasoning", input=input) as step:
            invoice = extract_fields(input["document"])
            step.output = invoice

        with execution.step("validate", input=invoice) as step:
            try:
                verdict = invoices.validate(invoice)
            except ValidationUnavailable as error:
                # The bug this demo is about: the outage is swallowed, so the invoice is silently
                # never submitted, and the run below still reports success.
                execution.log(f"validation skipped: {error}", level="warning")
                verdict = None
            step.output = verdict

        if verdict is not None and verdict["valid"]:
            submit_invoice(invoice)

        execution.output = {"status": "processed", "invoice_number": invoice["invoice_number"]}
    return execution.output
