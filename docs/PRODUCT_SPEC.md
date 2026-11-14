# Ghostwatch — Product Specification & Engineering Execution Plan

## 1. Your role

You are the lead software architect, senior full-stack engineer and technical coordinator for **Ghostwatch**.

We are a team of two developers:

- **Jayden:** Backend, SDK, event ingestion, database and agent instrumentation.
- **Adit:** Frontend, dashboard, visualisations and user experience.

Both developers will work independently on separate branches and push their work to a shared GitHub repository.

Your responsibility is to help us build a complete, functional, integrated product within approximately 48 hours.

Do not approach this as a toy prototype or a generic AI dashboard. We want a technically credible developer tool with a clear architecture, working functionality and a polished interface.

---

# 2. Product vision

## Ghostwatch

**Tagline: Your agents say they're working. Ghostwatch makes sure they actually are.**

Ghostwatch is an observability and reliability platform for AI agents and automated workflows.

As developers deploy increasingly autonomous agents, they need visibility into what those agents are doing, whether they are behaving correctly, where they fail and why.

Traditional monitoring tells developers whether a service is running.

Ghostwatch should help developers understand whether their AI agents are actually doing what they were supposed to do.

The platform should:

1. Monitor AI agent executions.
2. Capture detailed execution traces.
3. Detect failures and unusual behaviour.
4. Investigate failures using actual execution evidence.
5. Replay previous executions using recorded inputs.

The key differentiator is evidence-based investigation rather than simply displaying errors or generating AI explanations.

---

# 3. Core product functionality

## Feature 1: Agent monitoring

Developers must be able to register and monitor their agents.

Each execution should capture:

- Agent name and ID.
- Execution/run ID.
- Execution status.
- Start time and end time.
- Total duration.
- Input and output metadata.
- Token usage, when available.
- Estimated cost, when usage and pricing information are available.
- Errors and exceptions.
- Number of execution steps.
- Tool calls and their results.

Supported execution statuses:

- Running
- Completed
- Failed
- Timed out

The dashboard should provide an overview of all monitored agents and their latest executions.

## Feature 2: Execution tracing

This is one of the most important features.

We need a detailed timeline showing exactly what happened during an agent execution.

Example:

Agent: Research Assistant

Execution:
1. Received user input.
2. Called search tool.
3. Retrieved three results.
4. Passed results to the language model.
5. Generated an intermediate response.
6. Called another tool.
7. Encountered an exception.
8. Execution failed.

Every step should contain:

- Step name and type.
- Start and end timestamps.
- Duration.
- Input and output metadata.
- Status.
- Error details, if applicable.

The frontend should visualise this as an interactive execution timeline or trace tree.

Developers should be able to expand individual steps and inspect their details.

## Feature 3: Anomaly detection

Ghostwatch should identify suspicious execution behaviour.

Implement deterministic detection rules first.

Examples:

- Execution duration suddenly increases.
- Repeated tool-call failures.
- Excessive retries.
- Unusually high token consumption.
- Agents repeatedly timing out.
- Executions marked successful despite missing expected completion events.
- Unexpected execution patterns compared with historical baselines.

Every anomaly should contain:

- Anomaly type.
- Severity.
- Associated agent and execution.
- Detection timestamp.
- Supporting evidence.
- Explanation of why it was flagged.

Do not pretend that simple threshold checks are sophisticated machine learning.

Use sensible deterministic rules for the MVP. AI-assisted analysis can be added on top.

## Feature 4: AI-powered failure investigation

This is the primary intelligence feature.

When an execution fails or an anomaly is detected, Ghostwatch should investigate the available execution data.

The investigation engine should:

1. Retrieve the complete execution trace.
2. Identify the failing step.
3. Examine the surrounding events.
4. Examine relevant errors and tool responses.
5. Identify potential contributing factors.
6. Produce a structured investigation report.

The report should contain:

- Summary.
- Root-cause hypothesis.
- Evidence supporting the hypothesis.
- Relevant execution steps.
- Confidence level.
- Suggested next actions.

CRITICAL REQUIREMENT:

The system must distinguish between confirmed facts and hypotheses.

Never present an AI-generated explanation as a confirmed root cause unless the available evidence supports that conclusion.

If there is insufficient evidence, explicitly state that.

Use the Fable model where available for investigation and explanation, but keep the underlying monitoring and anomaly detection functional without depending on the LLM.

Keep model calls isolated behind a provider interface so the model can be changed later.

## Feature 5: Execution replay

Developers should be able to replay a previously recorded execution.

For the MVP:

- Store the original execution inputs.
- Store the execution configuration and recorded events.
- Allow developers to initiate a replay.
- Create a new execution linked to the original.
- Display the original and replayed executions separately.
- Compare their outcomes.

IMPORTANT:

Replaying an execution must not silently repeat external side effects.

Use mocked or sandboxed tool calls by default. Any real external action must require explicit developer authorisation.

---

# 4. Product interface

We want Ghostwatch to feel like a serious developer infrastructure product.

Design direction:

- Dark-first interface.
- Premium, minimal developer-tool aesthetic.
- Clear typography.
- Restrained use of colour.
- Strong information hierarchy.
- Smooth interactions.
- No unnecessary gradients, decorative animations or generic AI-themed illustrations.

Suggested navigation:

1. Overview
2. Agents
3. Executions
4. Traces
5. Anomalies
6. Investigations
7. Replays
8. Settings

## Overview dashboard

Display:

- Total registered agents.
- Total executions.
- Successful executions.
- Failed executions.
- Average execution duration.
- Detected anomalies.
- Recent executions.
- Agent health overview.
- Execution trends over time.

## Agents page

Show:

- Registered agents.
- Agent status.
- Total executions.
- Success/failure rates.
- Average duration.
- Latest execution.

Allow users to inspect individual agents.

## Executions page

Provide a searchable and filterable execution table.

Filters should include:

- Agent.
- Execution status.
- Date range.
- Duration.
- Anomaly presence.

## Trace explorer

An interactive timeline or tree showing execution steps.

Clicking a step should reveal its inputs, outputs, duration, status and errors.

## Anomalies page

Display detected anomalies with severity, supporting evidence and associated executions.

## Investigation page

Display structured AI investigation reports.

The interface should clearly distinguish facts, hypotheses and recommendations.

## Replay page

Show original executions and their replay counterparts, with a comparison of outcomes.

---

# 5. Technical architecture

Use a modular architecture.

Suggested stack:

### Frontend
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- React Flow where useful for trace visualisation
- Recharts for charts

### Backend
- Python
- FastAPI
- Pydantic
- SQLAlchemy

### Database
- PostgreSQL

### Background processing
- Redis and a worker if needed.

Avoid unnecessary infrastructure for a 48-hour MVP.

### AI layer
- Fable model integration through a dedicated provider abstraction.
- Structured JSON outputs.
- Explicit error handling.
- Configurable model credentials through environment variables.

### Integration architecture

The backend must expose a documented REST API.

Suggested endpoints:

- POST /api/v1/agents
- GET /api/v1/agents
- GET /api/v1/agents/{agent_id}
- POST /api/v1/executions
- GET /api/v1/executions
- GET /api/v1/executions/{execution_id}
- POST /api/v1/executions/{execution_id}/events
- GET /api/v1/executions/{execution_id}/trace
- GET /api/v1/anomalies
- GET /api/v1/investigations/{execution_id}
- POST /api/v1/investigations/{execution_id}
- POST /api/v1/executions/{execution_id}/replay

You may adjust endpoint naming if there is a strong architectural reason. Document every change.

---

# 6. Two-developer work division

This is a critical requirement.

We have two developers working on the same GitHub repository. We cannot have both people constantly modifying the same files and breaking each other's work.

Design the repository and development process around independent contributions.

## Jayden: Backend and SDK

Primary ownership:

- FastAPI backend.
- Database schema and migrations.
- Agent registration.
- Execution ingestion.
- Event storage.
- Execution trace processing.
- Anomaly detection engine.
- Investigation service.
- Replay engine.
- Python SDK for agent instrumentation.
- Backend tests.
- API documentation.

Expected deliverables:

1. Working backend.
2. PostgreSQL integration.
3. Agent registration and execution ingestion.
4. Trace storage and retrieval.
5. Deterministic anomaly detection.
6. Investigation API.
7. Replay API with safe defaults.
8. Python SDK.
9. API documentation.
10. Backend tests.

## Adit: Frontend and dashboard

Primary ownership:

- Next.js application.
- Application layout and navigation.
- Dashboard overview.
- Agent management interface.
- Execution explorer.
- Trace visualisation.
- Anomaly dashboard.
- Investigation reports UI.
- Replay interface.
- Charts and data visualisation.
- Responsive design.
- Frontend tests.

Expected deliverables:

1. Complete frontend application.
2. Consistent design system.
3. All major dashboard pages.
4. Interactive trace explorer.
5. Execution filtering.
6. Anomaly visualisation.
7. Investigation report interface.
8. Replay comparison interface.
9. API integration.
10. Frontend tests.

## Shared responsibilities

Both developers must:

- Review each other's pull requests.
- Keep the shared API contract consistent.
- Communicate breaking changes.
- Test integrated functionality.
- Update documentation.
- Avoid committing secrets or environment files.

---

# 7. GitHub collaboration strategy

We will use GitHub as the single source of truth.

Recommended branch structure:

- main: stable, integrated application.
- jayden/backend: Jayden's backend work.
- adit/frontend: Adit's frontend work.
- feature/*: smaller independent features when appropriate.

Rules:

1. Never push unfinished or untested work directly to main.
2. Commit frequently with descriptive commit messages.
3. Open pull requests for major features.
4. Keep PRs focused and reasonably small.
5. Review changes before merging.
6. Pull the latest main before beginning new work.
7. Resolve conflicts deliberately rather than overwriting another developer's work.
8. Never commit .env files, API keys or credentials.

Create a GitHub issue for each significant feature.

Use labels such as:

- backend
- frontend
- integration
- bug
- documentation
- priority: high

## Preventing integration problems

Before implementation, establish a shared API contract.

The frontend and backend must agree on:

- Request formats.
- Response formats.
- Data types.
- Execution status values.
- Error response formats.
- Pagination.
- Authentication assumptions.

Create an OpenAPI specification or equivalent API documentation.

Adit should be able to build the frontend against mocked API responses while Jayden develops the backend.

Do not make frontend implementation dependent on backend completion.

Once both sides are ready, integrate against the same API contract.

Avoid having both developers edit the same core files.

---

# 8. Demo requirements

The final product must have a convincing, repeatable demonstration.

Prepare a sample AI agent that performs a realistic task.

Demonstration sequence:

1. Register an AI agent with Ghostwatch.
2. Run a successful execution.
3. Show its execution trace.
4. Run another execution with an intentionally introduced failure.
5. Show Ghostwatch detecting the failure.
6. Open the investigation report.
7. Show the evidence behind the suspected root cause.
8. Replay the execution in a sandbox.
9. Compare the original and replayed executions.

The demonstration should make the product's value immediately obvious.

Use controlled sample data and predictable failure scenarios.

Do not depend on an unpredictable external service during the final presentation.

---

# 9. Quality and engineering requirements

We care about actual functionality, not screenshots pretending to be software.

Requirements:

- Backend endpoints must work.
- Data must persist.
- Frontend must consume actual backend APIs.
- Execution traces must be generated from real events.
- Anomalies must be detected using implemented logic.
- AI investigations must use actual stored execution data.
- Replay must create a distinct execution.
- Errors must be handled gracefully.
- Loading and empty states must exist.
- Core functionality must have automated tests.
- The application must have setup instructions.
- Sample data must be available for demonstrations.

Never fabricate metrics, execution results or investigation evidence.

If a feature is not implemented, label it as incomplete rather than displaying fake functionality.

---

# 10. Your first task: planning before coding

DO NOT immediately generate the entire application.

First inspect the existing GitHub repository and its current contents.

Then produce:

1. A concise technical architecture.
2. A recommended directory structure.
3. A database schema.
4. A shared API contract.
5. A precise division of work between Jayden and Adit.
6. A GitHub issue breakdown with priorities.
7. A dependency map identifying which tasks can run in parallel.
8. A realistic 48-hour implementation schedule.
9. A list of technical risks and potential integration conflicts.
10. A definition of done for the MVP.

Create a `PROJECT_PLAN.md` containing the agreed architecture and development plan.

Create a `CONTRIBUTING.md` documenting our GitHub workflow.

Create an `.env.example` without real credentials.

Once the plan is established, help us implement the product incrementally.

For each implementation task:

- State which developer owns it.
- Identify the files involved.
- Identify dependencies.
- Specify acceptance criteria.
- Explain how to test it.
- Mention any API contract changes.
- Keep changes within the assigned ownership boundaries.

Do not silently make architectural changes that affect the other developer's work.

If a change requires both developers to modify their respective components, explicitly describe the integration sequence.

---

# 11. Scope discipline

We have approximately 48 hours.

Prioritise the following:

P0:
- Agent registration.
- Execution ingestion.
- Persistent event storage.
- Execution trace visualisation.
- Deterministic anomaly detection.
- Evidence-based investigation.
- Working integrated dashboard.

P1:
- Python SDK.
- Execution replay.
- Token and cost tracking.
- Advanced filtering.

P2:
- Advanced analytics.
- Multiple model providers.
- More sophisticated anomaly detection.
- Additional integrations.

Finish P0 before expanding into P1 or P2.

Do not introduce Kubernetes, microservices, complex distributed infrastructure or unnecessary abstractions.

Build the smallest technically sound system that demonstrates the complete Ghostwatch workflow.

---

# 12. Final objective

We want Ghostwatch to be a credible, functional AI-agent observability product.

The final experience should let a developer answer five questions:

1. What are my agents doing?
2. What happened during a particular execution?
3. Is something behaving abnormally?
4. Why did an execution fail, and what evidence supports that explanation?
5. Can I safely reproduce and investigate the failure?

Every architectural and product decision should support these questions.

**Build Ghostwatch as real developer infrastructure, not an AI-themed dashboard.**

Start by inspecting the repository and producing the implementation plan. Do not skip the two-developer GitHub collaboration requirements.