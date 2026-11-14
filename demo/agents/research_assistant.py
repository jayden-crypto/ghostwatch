"""Research Assistant: plan -> web_search -> parse_results -> summarize.

Demo scenario "schema-change": the search API starts answering {"data": [...], "meta": {...}}
instead of {"results": [...]}, and parse_results raises KeyError: 'results'.
"""

import ghostwatch as gw

from fake_services.llm import MODEL, FakeLLM
from fake_services.search_api import SearchApi

AGENT = gw.Agent(
    slug="research-assistant",
    name="Research Assistant",
    description="Answers a question from web search results.",
    framework="custom",
)
CONFIG = {
    "model": MODEL,
    "params": {"max_results": 3},
    "expected_steps": ["web_search", "parse_results", "summarize"],
}

search = SearchApi()
llm = FakeLLM()


@gw.tool
def web_search(query: str) -> dict:
    return search.search(query, max_results=CONFIG["params"]["max_results"])


@gw.llm_call(model=MODEL)
def summarize(question: str, sources: list) -> dict:
    prompt = f"Answer the question using only these sources.\nQuestion: {question}\nSources: {sources}"
    reply = f"Based on {len(sources)} sources: " + " ".join(source["snippet"] for source in sources)
    return llm.complete(prompt, reply=reply)


def parse_results(payload: dict) -> list:
    """Pick the fields the summary needs out of the search API's response."""
    return [{"title": item["title"], "snippet": item["snippet"]} for item in payload["results"]]


def run(input: dict) -> dict:
    with gw.execution(input=input, config=CONFIG, tags=["demo"]) as execution:
        with execution.step("plan", type="reasoning", input=input) as step:
            query = input["question"].rstrip("?").lower()
            step.output = {"query": query}

        payload = web_search(query)

        with execution.step(
            "parse_results", type="reasoning", input={"response_keys": sorted(payload)}
        ) as step:
            sources = parse_results(payload)
            step.output = {"sources": [source["title"] for source in sources]}

        summary = summarize(input["question"], sources)
        execution.output = {"answer": summary["text"], "sources": [source["title"] for source in sources]}
    return execution.output
