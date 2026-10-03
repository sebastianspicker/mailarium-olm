"""Shared operation serialization for archive repositories."""

from __future__ import annotations

import inspect
import sqlite3
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from functools import wraps
from typing import Any

from .session import ArchiveSession


def serialized_operation(method: Callable[..., Any]) -> Callable[..., Any]:
    """Run one public repository operation under its archive transaction lock.

    The decorator is applied at repository definition time.  This keeps
    operation scope visible in the repository classes and avoids intercepting
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
    """Mark a repository's public instance methods as archive operations."""
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


class ArchiveRepository:
    """Base for repositories that share one archive session.

    Subclasses are decorated with :func:`archive_repository`; every public
    method then holds the session's single re-entrant lock, exactly as the
    database facade's own operations do.
    """

    def __init__(self, session: ArchiveSession) -> None:
        self._session = session

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the shared archive connection."""
        return self._session.conn

    def operation(self) -> AbstractContextManager[None]:
        """Hold the shared archive-operation lock for one complete call."""
        return self._session.operation()


__all__ = ["ArchiveRepository", "archive_repository", "serialized_operation"]
