"""Errors raised by the scraper."""

from __future__ import annotations


class ZooplaError(Exception):
    """Base class for scraper errors."""


class NotFoundError(ZooplaError):
    """Zoopla has no such listing, property or place."""


class ListingNotFoundError(NotFoundError):
    """The listing is gone (sold, let or withdrawn); Zoopla shows a search page instead."""


class LocationNotFoundError(NotFoundError):
    """Zoopla does not know the place (it answers 404 or sends you to its home page)."""


class ParseError(ZooplaError):
    """A response was not the Zoopla page the scraper expected."""


class InputError(ZooplaError, ValueError):
    """A location, listing, filter or sort order could not be used."""
