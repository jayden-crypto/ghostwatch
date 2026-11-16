from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import PageDep, SessionDep, require_api_key
from app.api.responses import errors
from app.schemas.common import Page
from app.schemas.replays import Replay, ReplayClaim, ReplayCreate
from app.services import replay as service

router = APIRouter(tags=["replays"])


@router.post(
    "/executions/{execution_id}/replay",
    response_model=Replay,
    status_code=201,
    responses=errors(
        404,
        (409, "`conflict`: the execution is still running."),
        (
            422,
            "`side_effect_authorization_required`: `mode` is `live` without `authorize_side_effects: true`. "
            "Also `validation_error` for a malformed body.",
        ),
    ),
    summary="Request a replay of an execution (sandbox by default)",
)
def create_replay(execution_id: str, body: ReplayCreate, session: SessionDep) -> Replay:
    """Records a replay request in status `pending`. A replay worker running the agent's code picks it up.

    `mode: "sandbox"` never runs a tool with side effects. Calls the original run made return their
    recorded outputs. A call it never made runs only if it is an LLM call or a tool declared free of
    side effects; any other tool is blocked. `mode: "live"` runs every tool for real and is refused
    unless the body also says `authorize_side_effects: true`.
    """
    return service.to_schema(service.create_replay(session, execution_id, body))


@router.get("/replays", response_model=Page[Replay], responses=errors(400, 422), summary="List replays")
def list_replays(
    session: SessionDep,
    page: PageDep,
    original_execution_id: str | None = None,
    status: Annotated[str | None, Query(description="Comma-separated replay statuses")] = None,
    sort: Annotated[str, Query(description="requested_at; prefix with - for descending")] = "-requested_at",
) -> Page[Replay]:
    """Replays, newest first. A worker polls this with `status=pending` to find work.

    `comparison` is set once the replay's execution has ended: both summaries, the outcome, the
    deltas and the steps aligned by ordinal and name, each with its `replay_source`.
    """
    return service.list_replays(
        session,
        original_execution_id=original_execution_id,
        status=status,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/replays/{replay_id}", response_model=Replay, responses=errors(404), summary="Get one replay")
def get_replay(replay_id: str, session: SessionDep) -> Replay:
    """One replay. Poll it until `status` is `completed` or `failed`."""
    return service.to_schema(service.get_replay(session, replay_id))


@router.post(
    "/replays/{replay_id}/claim",
    response_model=ReplayClaim,
    responses=errors(401, 404, (409, "`conflict`: the replay has already been claimed.")),
    dependencies=[Depends(require_api_key)],
    summary="Claim a pending replay and get its bundle (worker)",
)
def claim_replay(replay_id: str, session: SessionDep) -> ReplayClaim:
    """Gives the replay to exactly one worker and returns what it needs to run it.

    The bundle holds the original execution and its recorded tool and LLM calls in order. The worker
    then starts an execution with `replay_of` and `replay_id` set and streams its events as usual;
    when that execution ends, the replay becomes `completed` and its comparison is computed.
    """
    return service.claim_replay(session, replay_id)
