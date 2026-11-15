"""Support Triage: classify -> retrieve_kb -> draft_reply.

Demo scenarios: "rate-limit" (the knowledge base answers 429 twice, the agent retries) and
"slow" (the knowledge base is slow, the run takes several times its usual duration).
"""

import ghostwatch as gw

from fake_services.kb_api import KnowledgeBase, RateLimited
from fake_services.llm import MODEL, FakeLLM
from fake_services.timing import timing

AGENT = gw.Agent(
    slug="support-triage",
    name="Support Triage",
    description="Classifies a support ticket, looks up the knowledge base and drafts a reply.",
    framework="custom",
)
CONFIG = {
    "model": MODEL,
    "params": {"max_attempts": 3},
    "expected_steps": ["classify", "retrieve_kb", "draft_reply"],
}

kb = KnowledgeBase()
llm = FakeLLM()

CATEGORIES = {
    "refund": "billing",
    "charge": "billing",
    "invoice": "billing",
    "login": "access",
    "password": "access",
}


@gw.llm_call(model=MODEL)
def classify(ticket: str) -> dict:
    category = next((label for word, label in CATEGORIES.items() if word in ticket.lower()), "bug")
    return llm.complete(
        f"Classify this support ticket as billing, access or bug.\nTicket: {ticket}", reply=category
    )


@gw.tool(side_effects=False)  # read-only: a sandbox replay may run it when it has no recording
def retrieve_kb(category: str) -> dict:
    return kb.lookup(category)


@gw.llm_call(model=MODEL)
def draft_reply(ticket: str, articles: list) -> dict:
    guidance = " ".join(article["body"] for article in articles) or "A specialist will follow up."
    return llm.complete(
        f"Draft a short reply to this ticket using the articles.\nTicket: {ticket}\nArticles: {articles}",
        reply=f"Thanks for getting in touch. {guidance}",
    )


def retrieve_with_retries(category: str) -> dict:
    """Retry the knowledge base on rate limits, backing off between attempts."""
    for attempt in range(1, CONFIG["params"]["max_attempts"] + 1):
        try:
            return retrieve_kb(category)
        except RateLimited:
            if attempt == CONFIG["params"]["max_attempts"]:
                raise
            timing.wait(0.2 * attempt)
    raise AssertionError("unreachable")


def run(input: dict) -> dict:
    kb.reset()
    with gw.execution(input=input, config=CONFIG, tags=["demo"]) as execution:
        category = classify(input["ticket"])["text"]
        articles = retrieve_with_retries(category)["articles"]
        reply = draft_reply(input["ticket"], articles)
        execution.output = {
            "category": category,
            "reply": reply["text"],
            "articles": [a["id"] for a in articles],
        }
    return execution.output
