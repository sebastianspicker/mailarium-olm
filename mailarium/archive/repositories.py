"""Shared operation serialization for archive repository collaborators."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Generator
from functools import wraps
from typing import Any


def serialized_operation(method: Callable[..., Any]) -> Callable[..., Any]:
    """Run one public repository operation under its archive transaction lock.

    The decorator is applied at repository definition time.  This keeps
    operation scope visible in the collaborator classes and avoids intercepting
    arbitrary attribute access on the database facade.  Generator methods hold
    the same lock for their complete iteration lifetime.
    """

    if inspect.isgeneratorfunction(method):

        @wraps(method)
        def serialized_generator(self: Any, *args: Any, **kwargs: Any) -> Generator[Any]:
            with self.operation():
                yield from method(self, *args, **kwargs)

        return serialized_generator

    @wraps(method)
    def serialized(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self.operation():
            return method(self, *args, **kwargs)

    return serialized


def archive_repository(cls: type[Any]) -> type[Any]:
    """Mark a collaborator's public instance methods as archive operations."""
    for name, value in vars(cls).items():
        if (
            name.startswith("_")
            or name == "operation"
            or isinstance(value, (classmethod, staticmethod, property))
            or not callable(value)
        ):
            continue
        setattr(cls, name, serialized_operation(value))
    return cls
