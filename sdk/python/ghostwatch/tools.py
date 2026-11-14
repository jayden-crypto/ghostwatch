"""`@ghostwatch.tool` and `@ghostwatch.llm_call`: record every call of a function as a step."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar, overload

from ghostwatch.execution import current_execution

F = TypeVar("F", bound=Callable[..., Any])


def _recorded(function: F, *, step_type: str, name: str, model: str | None, info: dict[str, Any]) -> F:
    signature = inspect.signature(function)
    is_tool = step_type == "tool_call"

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        run = current_execution()
        if run is None:
            return function(*args, **kwargs)
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            call_input: Any = dict(bound.arguments)
        except TypeError:
            call_input = {"args": list(args), "kwargs": kwargs}  # the call itself will raise below
        step = run.step(
            name,
            step_type,
            input=call_input,
            tool_name=name if is_tool else None,
            model=model,
            attempt=run._next_attempt(name),
            metadata={"side_effects": info["side_effects"]} if is_tool else None,
        )
        with step:
            try:
                result = function(*args, **kwargs)
            except BaseException:
                run._record_tool_result(name, failed=True)
                raise
            run._record_tool_result(name, failed=False)
            step.output = result
            usage = result.get("usage") if isinstance(result, dict) else None
            if not is_tool and isinstance(usage, dict):
                step.tokens_input = usage.get("input_tokens")
                step.tokens_output = usage.get("output_tokens")
            return result

    wrapper.__ghostwatch_tool__ = info  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


@overload
def tool(func: F) -> F: ...
@overload
def tool(*, side_effects: bool = False, name: str | None = None) -> Callable[[F], F]: ...


def tool(func: Any = None, *, side_effects: bool = False, name: str | None = None) -> Any:
    """Record calls of the decorated function as tool_call steps of the current execution.

    `side_effects=True` marks a tool that changes the outside world (sends, writes, pays). The flag
    is stored with every call, and such a tool is never executed during a sandbox replay.
    Outside an execution the function runs exactly as if it were not decorated.
    """

    def decorate(function: F) -> F:
        tool_name = name or function.__name__
        info = {"name": tool_name, "side_effects": side_effects}
        return _recorded(function, step_type="tool_call", name=tool_name, model=None, info=info)

    return decorate(func) if func is not None else decorate


@overload
def llm_call(func: F) -> F: ...
@overload
def llm_call(*, model: str | None = None, name: str | None = None) -> Callable[[F], F]: ...


def llm_call(func: Any = None, *, model: str | None = None, name: str | None = None) -> Any:
    """Record calls of the decorated function as llm_call steps of the current execution.

    If the function returns a dict with a `usage` dict holding `input_tokens` / `output_tokens`
    (the shape model APIs return), those are recorded as the step's token usage.
    """

    def decorate(function: F) -> F:
        step_name = name or function.__name__
        info = {"name": step_name, "side_effects": False}
        return _recorded(function, step_type="llm_call", name=step_name, model=model, info=info)

    return decorate(func) if func is not None else decorate
