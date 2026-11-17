/**
 * The fixture story: five agents and every run they made, recorded the way the demo agents in
 * `demo/agents/` record theirs (same step names, types, inputs and outputs).
 *
 * The story follows PROJECT_PLAN §5: a healthy research run, the schema-change failure and its
 * sandbox replay that comes back `fixed`, the ghost-completion invoice run, and the retry and
 * duration anomalies on support-triage. A fourth agent (a scheduled job that hangs) and a fifth
 * that never ran are added so that every status, step type and anomaly type has a real example.
 */
import type { AnomalyStatus, ErrorInfo, Json, ReplayMode, ReplayStatus } from "../../lib/api/types";
import type { LlmContribution } from "./investigation";
import { at, HOUR, NOW, pythonError, rng, Run, type AgentSpec } from "./world";

const DEMO_MODEL = "demo-llm-1";
const DIGEST_MODEL = "claude-haiku-5-5";
const tokens = (text: string): number => Math.ceil(text.length / 4);
const random = rng(20261114);
const vary = (ms: number, spread: number): number => Math.round(ms + (random() * 2 - 1) * spread);

// ── Agents ──────────────────────────────────────────────────────────────────

export const research: AgentSpec = {
  n: 1,
  slug: "research-assistant",
  name: "Research Assistant",
  description: "Answers a question from web search results.",
  framework: "custom",
  metadata: {},
  createdAt: at("2026-11-12T08:00:01.204Z"),
  config: {
    model: DEMO_MODEL,
    params: { max_results: 3 },
    expected_steps: ["web_search", "parse_results", "summarize"],
    timeout_ms: null,
  },
};

export const invoice: AgentSpec = {
  n: 2,
  slug: "invoice-processor",
  name: "Invoice Processor",
  description: "Extracts invoice fields, validates them and submits the invoice for payment.",
  framework: "custom",
  metadata: {},
  createdAt: at("2026-11-12T08:00:01.391Z"),
  config: { model: null, params: {}, expected_steps: ["extract_fields", "validate", "submit_invoice"], timeout_ms: null },
};

export const support: AgentSpec = {
  n: 3,
  slug: "support-triage",
  name: "Support Triage",
  description: "Classifies a support ticket, looks up the knowledge base and drafts a reply.",
  framework: "custom",
  metadata: {},
  createdAt: at("2026-11-12T08:00:01.577Z"),
  config: {
    model: DEMO_MODEL,
    params: { max_attempts: 3 },
    expected_steps: ["classify", "retrieve_kb", "draft_reply"],
    timeout_ms: null,
  },
};

const DIGEST_SCHEDULE = "0 */6 * * *";
export const digest: AgentSpec = {
  n: 4,
  slug: "ticket-digest",
  name: "Ticket Digest",
  description: "Scheduled job that summarises new support tickets every six hours and posts the digest.",
  framework: "custom",
  metadata: { schedule: DIGEST_SCHEDULE, owner: "support-ops" },
  createdAt: at("2026-11-12T17:42:10.006Z"),
  config: {
    model: DIGEST_MODEL,
    params: { batch_size: 20 },
    expected_steps: ["fetch_tickets", "summarize", "send_digest"],
    timeout_ms: 120_000,
    schedule: DIGEST_SCHEDULE,
  },
};

/** Registered but never run: the `idle` health state, and null description/framework. */
export const reviewer: AgentSpec = {
  n: 5,
  slug: "pr-reviewer",
  name: "PR Reviewer",
  description: null,
  framework: null,
  metadata: {},
  createdAt: at("2026-11-14T16:10:44.530Z"),
  config: { model: null, params: {}, expected_steps: null, timeout_ms: null },
};

export const agents = [research, invoice, support, digest, reviewer];

// ── Research Assistant ──────────────────────────────────────────────────────

const QUESTIONS = [
  "How do teams trace what an AI agent did?",
  "Why do agents report success after skipping a step?",
  "What is a good retry strategy for rate-limited tools?",
  "How does schema drift break API consumers?",
  "How can a failed agent run be replayed safely?",
  "How are latency baselines used to catch regressions?",
];

const CORPUS = [
  {
    title: "Agent observability: tracing every step",
    url: "https://example.test/agent-observability",
    snippet: "Tracing records each tool call and model call an agent makes, with inputs and outputs.",
  },
  {
    title: "Why silent failures are the hardest agent bugs",
    url: "https://example.test/silent-failures",
    snippet: "An agent can report success while skipping the step that mattered.",
  },
  {
    title: "Retry strategies for rate-limited tools",
    url: "https://example.test/retry-strategies",
    snippet: "Exponential backoff with a retry budget keeps rate limits from cascading.",
  },
  {
    title: "Schema drift in upstream APIs",
    url: "https://example.test/schema-drift",
    snippet: "A renamed response field breaks every consumer that indexes it directly.",
  },
  {
    title: "Replaying agent runs against recorded inputs",
    url: "https://example.test/replay",
    snippet: "Deterministic replay turns a production failure into a local test case.",
  },
  {
    title: "Baselines for agent latency and token use",
    url: "https://example.test/baselines",
    snippet: "Comparing a run with the agent's own history catches regressions early.",
  },
];

type Doc = (typeof CORPUS)[number];

function search(query: string, maxResults: number): Doc[] {
  const words = query.toLowerCase().split(/\s+/).filter((word) => word.length > 3);
  const score = (doc: Doc) => words.filter((word) => `${doc.title} ${doc.snippet}`.toLowerCase().includes(word)).length;
  return CORPUS.map((doc, index) => ({ doc, index }))
    .sort((a, b) => score(b.doc) - score(a.doc) || a.index - b.index)
    .slice(0, maxResults)
    .map(({ doc }) => doc);
}

/** Contract §0: a payload over 64 KB is stored as this marker. */
function storedPayload(value: Json): Json {
  const text = JSON.stringify(value);
  if (text.length <= 64 * 1024) return value;
  return { _truncated: true, original_bytes: text.length, preview: text.slice(0, 2000) };
}

const AGENT_FILE = "/app/demo/agents/research_assistant.py";
const PARSE_V1 = 'return [{"title": item["title"], "snippet": item["snippet"]} for item in payload["results"]]';
const PARSE_WRONG = 'return [{"title": item["title"], "snippet": item["snippet"]} for item in payload["data"]["results"]]';

interface ResearchOptions {
  /** 2: the search API answers {"data": [...], "meta": {...}} instead of {"results": [...]}. */
  schema?: 1 | 2;
  /** v1 reads payload["results"]; "fixed" accepts both shapes; "wrong" is a fix that does not work. */
  parser?: "v1" | "fixed" | "wrong";
  /** The search API returns 24 full documents instead of 3 snippets. */
  flood?: boolean;
  /** Sandbox replay: tool calls return their recorded output at once. */
  sandbox?: boolean;
}

function researchRun(n: number, key: string, startedAt: number, q: number, note: string, o: ResearchOptions = {}): Run {
  const question = QUESTIONS[q % QUESTIONS.length];
  const run = new Run(n, key, research, startedAt, { question }, note);
  const query = question.replace(/\?+$/, "").toLowerCase();
  run.step({ name: "plan", type: "reasoning", ms: 1, input: { question }, output: { query } });

  let hits = search(query, 3);
  if (o.flood) {
    hits = Array.from({ length: 24 }, (_, i) => {
      const doc = CORPUS[i % CORPUS.length];
      return { ...doc, title: `${doc.title} (part ${i + 1})`, snippet: `${doc.snippet} `.repeat(86).trim() };
    });
  }
  const payload: { [k: string]: Json } =
    o.schema === 2
      ? { data: hits, meta: { total: hits.length, api_version: "2026-11" } }
      : { results: hits, total: hits.length };
  run.step({
    name: "web_search",
    type: "tool_call",
    tool: true,
    ms: o.sandbox ? 2 : o.flood ? 1840 : vary(350, 30),
    input: { query, max_results: 3 },
    output: storedPayload(payload),
  });

  const parseInput = { response_keys: Object.keys(payload).sort() };
  const parser = o.parser ?? "v1";
  if (o.schema === 2 && parser !== "fixed") {
    const error =
      parser === "v1"
        ? pythonError("KeyError", "'results'", [
            [AGENT_FILE, 56, "run", "sources = parse_results(payload)"],
            [AGENT_FILE, 43, "parse_results", PARSE_V1],
          ])
        : pythonError("TypeError", "list indices must be integers or slices, not str", [
            [AGENT_FILE, 56, "run", "sources = parse_results(payload)"],
            [AGENT_FILE, 43, "parse_results", PARSE_WRONG],
          ]);
    run.step({ name: "parse_results", type: "reasoning", ms: 1, input: parseInput, error });
    return run.fail(error);
  }
  const sources = hits.map(({ title, snippet }) => ({ title, snippet }));
  const titles = sources.map((source) => source.title);
  run.step({ name: "parse_results", type: "reasoning", ms: 1, input: parseInput, output: { sources: titles } });

  const prompt = `Answer the question using only these sources.\nQuestion: ${question}\nSources: ${JSON.stringify(sources)}`;
  const reply = `Based on ${sources.length} sources: ${sources.map((source) => source.snippet).join(" ")}`;
  const usage: [number, number] = [tokens(prompt), tokens(reply)];
  run.step({
    name: "summarize",
    type: "llm_call",
    model: DEMO_MODEL,
    ms: o.flood ? 2950 : vary(450, 35),
    input: storedPayload({ question, sources }),
    output: storedPayload({ text: reply, usage: { input_tokens: usage[0], output_tokens: usage[1] } }),
    tokens: usage,
  });
  return run.complete(storedPayload({ answer: reply, sources: titles }));
}

// ── Invoice Processor ───────────────────────────────────────────────────────

const INVOICES = [
  "Invoice: INV-2041\nVendor: Northwind Paper\nTotal: 1280.50\nCurrency: USD",
  "Invoice: INV-2042\nVendor: Contoso Cloud\nTotal: 9400.00\nCurrency: USD",
  "Invoice: INV-2043\nVendor: Fabrikam Freight\nTotal: 312.75\nCurrency: EUR",
  "Invoice: INV-2044\nVendor: Adatum Legal\nTotal: 5600.00\nCurrency: GBP",
  "Invoice: INV-2045\nVendor: Tailspin Catering\nTotal: 845.20\nCurrency: USD",
];

const INVOICE_FILE = "/app/demo/agents/invoice_processor.py";
const VALIDATION_DOWN = "validation service returned HTTP 503";

interface InvoiceOptions {
  /** The validation service is down. */
  outage?: boolean;
  /** The agent raises on a validation outage instead of swallowing it (the fix under replay). */
  raiseOnOutage?: boolean;
  /** A currency-conversion tool the agent had never called before. */
  convert?: boolean;
}

function invoiceRun(n: number, key: string, startedAt: number, i: number, note: string, o: InvoiceOptions = {}): Run {
  const document = INVOICES[i % INVOICES.length];
  const run = new Run(n, key, invoice, startedAt, { document }, note);
  const fields = Object.fromEntries(document.split("\n").map((line) => line.split(": ") as [string, string]));
  const parsed = {
    invoice_number: fields.Invoice,
    vendor: fields.Vendor,
    total: Number(fields.Total),
    currency: fields.Currency,
  };
  run.step({ name: "extract_fields", type: "reasoning", ms: 1, input: { document }, output: parsed });

  if (o.outage && o.raiseOnOutage) {
    const error = pythonError("ValidationUnavailable", VALIDATION_DOWN, [
      [INVOICE_FILE, 49, "run", "verdict = invoices.validate(invoice)"],
      ["/app/demo/fake_services/invoice_api.py", 24, "validate", `raise ValidationUnavailable("${VALIDATION_DOWN}")`],
    ]);
    run.step({ name: "validate", type: "custom", ms: vary(200, 15), input: parsed, error });
    return run.fail(error);
  }
  if (o.outage) {
    // The bug: the outage is swallowed, submit_invoice never runs, and the run reports success.
    const validate = run.step({ name: "validate", type: "custom", ms: vary(200, 15), input: parsed, output: null });
    run.log("warning", `validation skipped: ${VALIDATION_DOWN}`, validate, 1);
    return run.complete({ status: "processed", invoice_number: parsed.invoice_number });
  }
  run.step({ name: "validate", type: "custom", ms: vary(200, 15), input: parsed, output: { valid: true, problems: [] } });
  if (o.convert) {
    run.step({
      name: "convert_currency",
      type: "tool_call",
      tool: true,
      ms: vary(180, 15),
      input: { amount: parsed.total, from: parsed.currency, to: "USD" },
      output: { amount: 337.77, rate: 1.08 },
    });
  }
  run.step({
    name: "submit_invoice",
    type: "tool_call",
    tool: true,
    sideEffects: true,
    ms: vary(300, 20),
    input: { invoice: parsed },
    output: { submission_id: `SUB-${parsed.invoice_number}`, status: "accepted" },
  });
  return run.complete({ status: "processed", invoice_number: parsed.invoice_number });
}

// ── Support Triage ──────────────────────────────────────────────────────────

const TICKETS = [
  "I was charged twice for my subscription and need a refund.",
  "I can't login after changing my password.",
  "The export button does nothing when I click it.",
  "My invoice shows the wrong company address.",
  "Two-factor login keeps rejecting my code.",
  "The dashboard crashes when I filter by date.",
];
const CATEGORIES: [string, string][] = [
  ["refund", "billing"],
  ["charge", "billing"],
  ["invoice", "billing"],
  ["login", "access"],
  ["password", "access"],
];
const ARTICLES: Record<string, { id: string; title: string; body: string }[]> = {
  billing: [{ id: "KB-101", title: "How refunds are processed", body: "Refunds reach the card in 5-7 days." }],
  access: [{ id: "KB-204", title: "Resetting two-factor login", body: "Use a recovery code, then re-enrol." }],
  bug: [{ id: "KB-330", title: "Reporting a reproducible bug", body: "Include steps, expected and actual." }],
};

const SUPPORT_FILE = "/app/demo/agents/support_triage.py";
const RATE_LIMITED: ErrorInfo = pythonError("RateLimited", "HTTP 429 Too Many Requests", [
  [SUPPORT_FILE, 63, "retrieve_with_retries", "return retrieve_kb(category)"],
  ["/app/sdk/python/ghostwatch/tools.py", 43, "wrapper", "result = function(*args, **kwargs)"],
  [SUPPORT_FILE, 47, "retrieve_kb", "return kb.lookup(category)"],
  ["/app/demo/fake_services/kb_api.py", 41, "lookup", 'raise RateLimited("HTTP 429 Too Many Requests")'],
]);

interface SupportOptions {
  /** How many knowledge-base calls answer HTTP 429 before one succeeds. */
  rateLimited?: number;
  /** How long the knowledge base takes to answer. */
  kbMs?: number;
  /** Stop recording while retrieve_kb is in flight: the run is still running. */
  inFlight?: boolean;
}

function supportRun(n: number, key: string, startedAt: number, t: number, note: string, o: SupportOptions = {}): Run {
  const ticket = TICKETS[t % TICKETS.length];
  const run = new Run(n, key, support, startedAt, { ticket }, note);
  const category = CATEGORIES.find(([word]) => ticket.toLowerCase().includes(word))?.[1] ?? "bug";
  const classifyPrompt = `Classify this support ticket as billing, access or bug.\nTicket: ${ticket}`;
  const classifyUsage: [number, number] = [tokens(classifyPrompt), tokens(category)];
  run.step({
    name: "classify",
    type: "llm_call",
    model: DEMO_MODEL,
    ms: vary(450, 30),
    input: { ticket },
    output: { text: category, usage: { input_tokens: classifyUsage[0], output_tokens: classifyUsage[1] } },
    tokens: classifyUsage,
  });

  const articles = ARTICLES[category];
  for (let attempt = 1; attempt <= (o.rateLimited ?? 0); attempt++) {
    run.step({ name: "retrieve_kb", type: "tool_call", tool: true, ms: vary(250, 15), attempt, input: { category }, error: RATE_LIMITED });
    run.wait(200 * attempt);
  }
  const attempt = (o.rateLimited ?? 0) + 1;
  if (o.inFlight) {
    run.step({ name: "retrieve_kb", type: "tool_call", tool: true, ms: null, attempt, input: { category } });
    return run;
  }
  run.step({
    name: "retrieve_kb",
    type: "tool_call",
    tool: true,
    ms: o.kbMs ?? vary(250, 15),
    attempt,
    input: { category },
    output: { articles },
  });

  const draftPrompt = `Draft a short reply to this ticket using the articles.\nTicket: ${ticket}\nArticles: ${JSON.stringify(articles)}`;
  const reply = `Thanks for getting in touch. ${articles.map((article) => article.body).join(" ")}`;
  const draftUsage: [number, number] = [tokens(draftPrompt), tokens(reply)];
  run.step({
    name: "draft_reply",
    type: "llm_call",
    model: DEMO_MODEL,
    ms: vary(450, 30),
    input: { ticket, articles },
    output: { text: reply, usage: { input_tokens: draftUsage[0], output_tokens: draftUsage[1] } },
    tokens: draftUsage,
  });
  return run.complete({ category, reply, articles: articles.map((article) => article.id) });
}

// ── Ticket Digest (scheduled job) ───────────────────────────────────────────

const DIGEST_FILE = "/srv/jobs/ticket_digest.py";
const TICKET_API_DOWN: ErrorInfo = pythonError("HTTPError", "HTTP 503 Service Unavailable", [
  [DIGEST_FILE, 71, "fetch_with_retries", "return fetch_tickets(since, until)"],
  ["/srv/venv/lib/python3.12/site-packages/ghostwatch/tools.py", 43, "wrapper", "result = function(*args, **kwargs)"],
  [DIGEST_FILE, 38, "fetch_tickets", "response.raise_for_status()"],
]);

interface DigestOptions {
  /** ok: completes. fetch_fail: the ticket API answers 503 on all three attempts. hang: it never answers. */
  mode?: "ok" | "fetch_fail" | "hang";
  tickets?: number;
  /**
   * A sandbox replay of a run that never reached send_digest. fetch_tickets is the job's own
   * retrieval step, not an SDK tool call, so it runs for real; send_digest is a tool with side
   * effects and no recording, so the sandbox blocks it.
   */
  sendBlocked?: boolean;
}

function digestRun(n: number, key: string, startedAt: number, note: string, o: DigestOptions = {}): Run {
  const run = new Run(n, key, digest, startedAt, { trigger: "cron", schedule: DIGEST_SCHEDULE }, note, digest.config, ["scheduled"]);
  const window = { since: new Date(startedAt - 6 * HOUR).toISOString(), until: new Date(startedAt).toISOString() };
  run.step({ name: "load_schedule", type: "input", ms: 2, input: { trigger: "cron", schedule: DIGEST_SCHEDULE }, output: window });

  const fetch = { name: "fetch_tickets", type: "retrieval", tool: true, input: window } as const;
  const mode = o.mode ?? "ok";
  if (mode === "fetch_fail") {
    for (let attempt = 1; attempt <= 3; attempt++) {
      run.step({ ...fetch, ms: vary(3040, 60), attempt, error: TICKET_API_DOWN });
      if (attempt < 3) run.wait(1000 * attempt);
    }
    return run.fail(TICKET_API_DOWN);
  }
  if (mode === "hang") {
    run.step({ ...fetch, ms: null });
    // Silent for config.timeout_ms (120 s); the sweeper, which runs every 30 s, then times it out.
    return run.timeOut(120_000 + vary(15_000, 12_000));
  }

  const count = o.tickets ?? 37;
  const batches = Math.ceil(count / 20);
  run.step({
    ...fetch,
    ms: vary(620, 60),
    output: { count, pages: batches, first_ticket_ids: ["TCK-88412", "TCK-88413", "TCK-88415"] },
  });
  const parent = run.open({ name: "summarize", type: "reasoning", input: { tickets: count, batch_size: 20 } });
  let summaryChars = 0;
  for (let batch = 1; batch <= batches; batch++) {
    const size = Math.min(20, count - 20 * (batch - 1));
    const text = `Batch ${batch}: ${size} tickets. Most are billing questions about duplicate charges; ${Math.ceil(size / 5)} report login problems after a password change.`;
    summaryChars += text.length;
    const usage: [number, number] = [vary(105 * size, 60), tokens(text)];
    run.step({
      name: "summarize_batch",
      type: "llm_call",
      model: DIGEST_MODEL,
      parent,
      ms: vary(1900, 220),
      input: { batch, tickets: size },
      output: { text, usage: { input_tokens: usage[0], output_tokens: usage[1] } },
      tokens: usage,
    });
  }
  run.close(parent, { batches, summary_chars: summaryChars });
  const send = {
    name: "send_digest",
    type: "tool_call",
    tool: true,
    sideEffects: true,
    input: { channel: "#support-leads", summary_chars: summaryChars },
  } as const;
  if (o.sendBlocked) {
    const error = pythonError(
      "SandboxRecordingMissing",
      "send_digest has no recording for call 1 (the original execution made 0) and is not declared side_effects=False, so it is not run in a sandbox replay",
      [
        [DIGEST_FILE, 104, "run", "send_digest(channel=CHANNEL, summary=summary)"],
        ["/srv/venv/lib/python3.12/site-packages/ghostwatch/tools.py", 49, "wrapper", "raise SandboxRecordingMissing(blocked_because)"],
      ],
    );
    run.step({ ...send, ms: 0, error });
    return run.fail(error);
  }
  run.step({
    ...send,
    ms: vary(240, 20),
    output: { message_id: `MSG-${(startedAt / 1000) % 100000}`, status: "sent" },
  });
  const result = { tickets: count, batches, delivered: true };
  run.step({ name: "report", type: "output", ms: 1, input: null, output: result });
  return run.complete(result);
}

// ── The runs ────────────────────────────────────────────────────────────────

const routine = "Routine healthy run (baseline history).";

// Research Assistant
const r1 = researchRun(0x01, "research_01", at("2026-11-12T09:14:07.318Z"), 1, routine);
const r2 = researchRun(0x02, "research_02", at("2026-11-12T15:40:51.902Z"), 2, routine);
const r3 = researchRun(0x03, "research_03", at("2026-11-13T08:05:33.127Z"), 3, routine);
const r4 = researchRun(0x04, "research_04", at("2026-11-13T13:22:18.640Z"), 4, routine);
const r5 = researchRun(0x05, "research_05", at("2026-11-13T19:48:02.455Z"), 5, routine);
const r6 = researchRun(0x06, "research_06", at("2026-11-14T09:31:46.081Z"), 2, routine);
const tokenSpike = researchRun(
  0x07,
  "token_spike",
  at("2026-11-14T11:07:29.733Z"),
  3,
  "The search API returned 24 full documents instead of 3 snippets. Payloads over 64 KB are stored as `_truncated` markers; token_spike and duration_spike (both high) fire.",
  { flood: true },
);
export const healthy = researchRun(
  0x08,
  "healthy",
  at("2026-11-14T16:52:10.264Z"),
  0,
  "The healthy research run of the demo: plan → web_search → parse_results → summarize.",
);
export const schemaChange = researchRun(
  0x0a,
  "schema_change",
  at("2026-11-14T17:20:14.592Z"),
  0,
  "The demo failure: web_search answers {data, meta} instead of {results}; parse_results raises KeyError: 'results'.",
  { schema: 2 },
);
const wrongFixReplay = researchRun(
  0x0b,
  "replay_different_failure",
  at("2026-11-14T17:34:02.118Z"),
  0,
  "Sandbox replay of `schema_change` after a first fix that was wrong: fails with TypeError, outcome different_failure.",
  { schema: 2, parser: "wrong", sandbox: true },
);
export const fixedReplay = researchRun(
  0x0c,
  "replay_fixed",
  at("2026-11-14T17:45:27.806Z"),
  0,
  "Sandbox replay of `schema_change` after the parser fix: completes, outcome fixed.",
  { schema: 2, parser: "fixed", sandbox: true },
);

// Invoice Processor
const i1 = invoiceRun(0x21, "invoice_01", at("2026-11-12T10:02:44.019Z"), 0, routine);
const i2 = invoiceRun(0x22, "invoice_02", at("2026-11-12T16:30:12.774Z"), 1, routine);
const i3 = invoiceRun(0x23, "invoice_03", at("2026-11-13T09:45:55.230Z"), 3, routine);
const i4 = invoiceRun(0x24, "invoice_04", at("2026-11-13T14:10:08.661Z"), 4, routine);
const i5 = invoiceRun(0x25, "invoice_05", at("2026-11-13T20:15:39.348Z"), 0, routine);
const i6 = invoiceRun(0x26, "invoice_06", at("2026-11-14T08:20:21.905Z"), 3, routine);
const newTool = invoiceRun(
  0x27,
  "new_tool",
  at("2026-11-14T10:40:17.482Z"),
  2,
  "A EUR invoice made the agent call convert_currency, a tool not in its baseline: unexpected_pattern (low).",
  { convert: true },
);
export const ghostInvoice = invoiceRun(
  0x28,
  "ghost_invoice",
  at("2026-11-14T17:28:40.153Z"),
  1,
  "The demo ghost completion: validation is down, the agent swallows it, never calls submit_invoice and reports completed. ghost_completion (critical).",
  { outage: true },
);
const ghostReplay = invoiceRun(
  0x29,
  "replay_regressed",
  at("2026-11-14T17:52:06.737Z"),
  1,
  "Sandbox replay of `ghost_invoice` after making the agent raise on a validation outage: it now fails, so the outcome rule says regressed.",
  { outage: true, raiseOnOutage: true },
);

// Support Triage
const s1 = supportRun(0x41, "support_01", at("2026-11-12T08:30:26.540Z"), 2, routine);
const s2 = supportRun(0x42, "support_02", at("2026-11-12T12:10:03.288Z"), 3, routine);
const s3 = supportRun(0x43, "support_03", at("2026-11-12T18:45:47.916Z"), 4, routine);
const s4 = supportRun(0x44, "support_04", at("2026-11-13T07:55:19.073Z"), 5, routine);
const s5 = supportRun(0x45, "support_05", at("2026-11-13T12:40:31.652Z"), 0, routine);
const s6 = supportRun(0x46, "support_06", at("2026-11-13T17:30:58.397Z"), 2, routine);
const s7 = supportRun(0x47, "support_07", at("2026-11-14T07:15:09.821Z"), 4, routine);
export const rateLimit = supportRun(
  0x48,
  "rate_limit",
  at("2026-11-14T13:05:22.445Z"),
  0,
  "The knowledge base answers HTTP 429 twice, then succeeds: excessive_retries (medium). Has no investigation yet; the manual-investigation fixtures are for this run.",
  { rateLimited: 2 },
);
const rateLimitReplay = supportRun(
  0x4b,
  "replay_both_succeeded",
  at("2026-11-14T13:31:05.672Z"),
  0,
  "Live replay (authorized) of `rate_limit` after the knowledge base stopped rate limiting: every step is executed, outcome both_succeeded, and the two failed attempts are gone.",
);
export const slow = supportRun(
  0x49,
  "slow",
  at("2026-11-14T15:26:41.190Z"),
  1,
  "The knowledge base takes 3.5 s to answer: duration_spike (medium).",
  { kbMs: 3500 },
);
export const running = supportRun(
  0x4a,
  "running",
  NOW - 2_340,
  5,
  "Still running at fixture time: classify is done, retrieve_kb is in flight.",
  { inFlight: true },
);

// Ticket Digest, every six hours
const d1 = digestRun(0x61, "digest_01", at("2026-11-12T18:00:00.412Z"), routine, { tickets: 37 });
const d2 = digestRun(0x62, "digest_02", at("2026-11-13T00:00:00.385Z"), routine, { tickets: 12 });
export const fetchFailed = digestRun(
  0x63,
  "fetch_failed",
  at("2026-11-13T06:00:00.447Z"),
  "The ticket API answers HTTP 503 on all three attempts and the run fails: repeated_tool_failure (high) and excessive_retries (medium), both resolved. Its investigation itself failed.",
  { mode: "fetch_fail" },
);
const d4 = digestRun(0x64, "digest_04", at("2026-11-13T12:00:00.398Z"), routine, { tickets: 41 });
export const timedOutFirst = digestRun(
  0x65,
  "timed_out_1",
  at("2026-11-13T18:00:00.421Z"),
  "fetch_tickets never answers; the sweeper marks the run timed_out: stale_execution (high, acknowledged).",
  { mode: "hang" },
);
export const timedOutSecond = digestRun(
  0x66,
  "timed_out_2",
  at("2026-11-14T00:00:00.376Z"),
  "Second hang in a row: stale_execution (high).",
  { mode: "hang" },
);
const d7 = digestRun(0x67, "digest_07", at("2026-11-14T06:00:00.433Z"), routine, { tickets: 29 });
export const timedOut = digestRun(
  0x68,
  "timed_out",
  at("2026-11-14T12:00:00.409Z"),
  "Third hang within the agent's last 10 runs: stale_execution and repeated_timeouts (both high).",
  { mode: "hang" },
);
const fetchFailedReplay = digestRun(
  0x69,
  "replay_same_failure",
  at("2026-11-14T14:20:11.058Z"),
  "Sandbox replay of `fetch_failed`: fetch_tickets is the job's own retrieval step, so it runs for real; the ticket API still answers 503 and the run fails the same way. Outcome same_failure.",
  { mode: "fetch_fail" },
);
const timedOutReplay = digestRun(
  0x6a,
  "replay_inconclusive",
  at("2026-11-14T14:41:36.914Z"),
  "Sandbox replay of `timed_out`: it gets past fetch_tickets, then reaches send_digest, a tool with side effects that the original never recorded. The sandbox blocks it (SandboxRecordingMissing) and the replay fails. The original timed out, so the outcome is inconclusive.",
  { tickets: 29, sendBlocked: true },
);

// ── Replays ─────────────────────────────────────────────────────────────────

export interface ReplaySpec {
  n: number;
  key: string;
  original: Run;
  replay: Run | null;
  mode: ReplayMode;
  status: ReplayStatus;
  note: string | null;
  requestedAt: number;
  /** Ms after the request at which the worker claimed it. */
  claimedAfter: number | null;
  error: ErrorInfo | null;
}

const replay = (
  n: number,
  key: string,
  original: Run,
  replayRun: Run | null,
  rest: Partial<Omit<ReplaySpec, "n" | "key" | "original" | "replay">> & { requestedAt: number },
): ReplaySpec => {
  replayRun?.asReplayOf(original, n, rest.mode ?? "sandbox");
  return { n, key, original, replay: replayRun, mode: "sandbox", status: "completed", note: null, claimedAfter: 1_400, error: null, ...rest };
};

export const replays: ReplaySpec[] = [
  replay(1, "both_succeeded", rateLimit, rateLimitReplay, {
    mode: "live",
    note: "Knowledge base rate limit raised; checking the run goes through.",
    requestedAt: rateLimitReplay.startedAt - 2_150,
    claimedAfter: 1_720,
  }),
  replay(2, "different_failure", schemaChange, wrongFixReplay, {
    note: "First attempt at a parser fix.",
    requestedAt: wrongFixReplay.startedAt - 1_930,
  }),
  replay(3, "fixed", schemaChange, fixedReplay, {
    note: "After parser fix: accept both response shapes.",
    requestedAt: fixedReplay.startedAt - 1_660,
    claimedAfter: 1_210,
  }),
  replay(4, "regressed", ghostInvoice, ghostReplay, {
    note: "Agent now raises when validation is unavailable.",
    requestedAt: ghostReplay.startedAt - 2_480,
    claimedAfter: 2_040,
  }),
  replay(5, "same_failure", fetchFailed, fetchFailedReplay, { requestedAt: fetchFailedReplay.startedAt - 1_850 }),
  replay(6, "inconclusive", timedOut, timedOutReplay, { requestedAt: timedOutReplay.startedAt - 2_260, claimedAfter: 1_890 }),
  replay(7, "failed", fetchFailed, null, {
    status: "failed",
    requestedAt: at("2026-11-14T14:12:48.300Z"),
    claimedAfter: 1_150,
    error: {
      type: "ReplayStartError",
      message: "The replay worker could not start the agent: no agent with slug ticket-digest is registered in this worker.",
      stacktrace: null,
    },
  }),
  replay(8, "claimed", timedOutFirst, null, { status: "claimed", requestedAt: NOW - 6_800, claimedAfter: 1_300 }),
  replay(9, "pending", timedOutSecond, null, { status: "pending", requestedAt: NOW - 41_500, claimedAfter: null }),
];

// ── Everything else the story decides by hand ───────────────────────────────

export const runs: Run[] = [
  r1, r2, r3, r4, r5, r6, tokenSpike, healthy, schemaChange, wrongFixReplay, fixedReplay,
  i1, i2, i3, i4, i5, i6, newTool, ghostInvoice, ghostReplay,
  s1, s2, s3, s4, s5, s6, s7, rateLimit, rateLimitReplay, slow, running,
  d1, d2, fetchFailed, d4, timedOutFirst, timedOutSecond, d7, timedOut, fetchFailedReplay, timedOutReplay,
];

/** Anomalies someone has already triaged. Everything else is `open`. */
export const anomalyStatus: Record<string, AnomalyStatus> = {
  "new_tool:unexpected_pattern": "acknowledged",
  "timed_out_1:stale_execution": "acknowledged",
  "fetch_failed:repeated_tool_failure": "resolved",
  "fetch_failed:excessive_retries": "resolved",
};

/** The one investigation the LLM contributed to. Its hypotheses cite facts the code extracted. */
export const llmContributions: Record<string, LlmContribution> = {
  token_spike: {
    model: "claude-fable-5-2",
    root: 0,
    hypotheses: [
      {
        statement:
          "The web_search tool returned far more content than usual, and that content was passed on to summarize, which inflated the prompt and the answer.",
        confidence: "medium",
        reasoning:
          "The web_search output was large enough to be truncated at ingestion, the token_spike rule fired on this run, and the run took several times its baseline duration. A much larger search response explains all three, but the full response is not stored, so its size per result cannot be checked.",
        supports: ["output:2", "anomaly:token_spike", "baseline"],
        steps: [2, 4],
      },
      {
        statement: "The spike comes from an unusually long question rather than from the search response.",
        confidence: "low",
        reasoning:
          "A longer question would raise prompt tokens. Nothing recorded supports a question long enough to account for the increase, and the truncated search output points elsewhere.",
        supports: ["anomaly:token_spike"],
        contradicts: ["output:2"],
      },
    ],
    recommendations: [
      {
        action: "Cap what parse_results passes to summarize: limit the number of sources and the length of each snippet.",
        rationale: "The prompt is built from every source the search tool returns, so its size is unbounded.",
        hypothesis: 0,
      },
      {
        action: "Record the size of each tool response as step metadata.",
        rationale: "With sizes recorded, growth in a prompt can be attributed to a specific tool call even when the payload is truncated.",
        hypothesis: null,
      },
    ],
    gaps: [
      "A hypothesis proposed by claude-fable-5-2 was discarded because it cited fact id(s) that do not exist (F12).",
      "The full web_search response is not stored, so the number and size of the results it returned cannot be verified.",
    ],
  },
};

/** Investigations that did not simply complete. */
export const investigationFailures: Record<string, ErrorInfo> = {
  fetch_failed: {
    type: "OperationalError",
    message: "The investigation could not be completed; see the backend log.",
    stacktrace: null,
  },
};
