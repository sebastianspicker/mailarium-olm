"""Bounded EWS indexed paging helpers."""

from dataclasses import dataclass

from .errors import EWSValidationError

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class IndexedPage:
    """Define a validated offset and size for a bounded EWS item request."""

    offset: int = 0
    size: int = MAX_PAGE_SIZE

    def __post_init__(self) -> None:
        if self.offset < 0 or not 1 <= self.size <= MAX_PAGE_SIZE:
            raise EWSValidationError("EWS page must have a non-negative offset and size 1..100")


def next_page(*, offset: int, returned: int, includes_last_item: bool, cap: int) -> IndexedPage | None:
    """Return the next request without allowing a non-advancing page loop."""
    if cap < 1 or returned < 0 or offset < 0:
        raise EWSValidationError("invalid EWS paging values")
    if includes_last_item or returned == 0 or offset + returned >= cap:
        return None
    return IndexedPage(offset=offset + returned, size=min(MAX_PAGE_SIZE, cap - offset - returned))
