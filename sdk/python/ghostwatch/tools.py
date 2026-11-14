"""`@ghostwatch.tool`: record every call of a function as a tool_call step."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar, overload

from ghostwatch.execution import current_execution

F = TypeVar("F", bound=Callable[..., Any])


@overload
def tool(func: F) -> F: ...
@overload
def tool(*, side_effects: bool = False, name: str | None = None) -> Callable[[F], F]: ...


def tool(func: Any = None, *, side_effects: bool = False, name: str | None = None) -> Any:
    """Record calls of the decorated function as steps of the current execution.

    `side_effects=True` marks a tool that changes the outside world (sends, writes, pays). The flag
    is stored with every call, and such a tool is never executed during a sandbox replay.
    Outside an execution the function runs exactly as if it were not decorated.
    """

    def decorate(function: F) -> F:
        tool_name = name or function.__name__
        signature = inspect.signature(function)

        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            run = current_execution()
            if run is None:
                return function(*args, **kwargs)
            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                tool_input: Any = dict(bound.arguments)
            except TypeError:
                tool_input = {"args": list(args), "kwargs": kwargs}  # the call itself will raise below
            step = run.step(
                tool_name,
                "tool_call",
                input=tool_input,
                tool_name=tool_name,
                attempt=run._next_attempt(tool_name),
                metadata={"side_effects": side_effects},
            )
            with step:
                try:
                    result = function(*args, **kwargs)
                except BaseException:
                    run._record_tool_result(tool_name, failed=True)
                    raise
                run._record_tool_result(tool_name, failed=False)
                step.output = result
                return result

        wrapper.__ghostwatch_tool__ = {"name": tool_name, "side_effects": side_effects}  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate(func) if func is not None else decorate
