import { ERROR_CODES, type ErrorCode, type ErrorEnvelope, type Json } from "./types";

/**
 * Every failed request, whichever adapter made it.
 *
 * `code` is a contract error code when the backend answered with the error envelope (§0), or one
 * of two client-side codes when it did not: `network_error` (no answer at all) and
 * `invalid_response` (an answer that is not the contract's shape).
 */
export class ApiError extends Error {
  readonly code: ErrorCode | "network_error" | "invalid_response";
  /** HTTP status, or null when no response arrived. */
  readonly status: number | null;
  readonly details: Json;

  constructor(code: ApiError["code"], message: string, status: number | null = null, details: Json = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export const isApiError = (error: unknown): error is ApiError => error instanceof ApiError;

export const isNotFound = (error: unknown): boolean => isApiError(error) && error.code === "not_found";

const isErrorCode = (value: unknown): value is ErrorCode =>
  typeof value === "string" && (ERROR_CODES as readonly string[]).includes(value);

/** The contract's error envelope, if `body` is one. */
export function parseErrorEnvelope(body: unknown): ErrorEnvelope["error"] | null {
  if (typeof body !== "object" || body === null) return null;
  const error = (body as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return null;
  const { code, message, details } = error as { code?: unknown; message?: unknown; details?: unknown };
  if (!isErrorCode(code) || typeof message !== "string") return null;
  return { code, message, details: (details ?? null) as Json };
}

export const HTTP_STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  unauthorized: 401,
  not_found: 404,
  conflict: 409,
  execution_already_terminal: 409,
  validation_error: 422,
  side_effect_authorization_required: 422,
  internal_error: 500,
  llm_unavailable: 503,
};

/** What to show a person for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}
