/** Wording shared by every replay screen, so the sandbox guarantee is stated the same way everywhere. */

/** What sandbox guarantees, in the words of contract v1.2 §10. Shown wherever a sandbox replay is explained. */
export const SANDBOX_RULE =
  "Calls the original run made return their recorded outputs. A call it never made runs live only if it is a model call or a tool marked side-effect free. Any other tool is blocked, so nothing with side effects ever runs.";

export const LIVE_RULE = "Every tool and model call runs for real, including tools with side effects. Nothing is served from the recording.";

export const AUTHORIZATION_LABEL = "I authorize real external side effects for this replay";

/** Where replays are executed. The backend only coordinates; a worker has the agent's code. */
export const WORKER_COMMAND = "cd demo && uv run python replay.py worker";
