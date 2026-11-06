"""Scrape Zoopla through the ScrapeUnblocker ``getPageSource`` API.

:class:`ZooplaScraper` uses the official ``scrapeunblocker`` SDK for every request and
reads the data Zoopla embeds in its own pages:

* **Search results** and **listing pages** carry their data in the page's React
  payload (see :mod:`zoopla_scraper.parsing`).
* **Sold house prices** and **property pages** carry it in ``__NEXT_DATA__``.

No browser rendering is needed, so each page is one plain ``getPageSource`` call.
Throttled, blocked and timed-out requests are retried with doubling backoff; a page
without the expected data is fetched once more, then raises :class:`ParseError`;
unknown places and removed listings raise :class:`NotFoundError` subclasses.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections.abc import Iterable, Iterator
from typing import Any, Callable

from .errors import (
    InputError,
    ListingNotFoundError,
    LocationNotFoundError,
    NotFoundError,
    ParseError,
)
from .models import (
    Change,
    Comparables,
    Listing,
    ListingDetails,
    PropertyHistory,
    SearchPage,
    SoldPrice,
    SoldPricesPage,
)
from .monitor import diff, load_state, save_state, snapshot
from .parsing import parse_listing, parse_property, parse_search, parse_sold
from .urls import (
    CHANNELS,
    MAX_PAGES,
    PAGE_SIZE,
    SORTS,
    SearchFilters,
    SearchQuery,
    SoldFilters,
    apply_search_path,
    listing_ref,
    listing_url,
    location_slug,
    needs_resolver,
    property_url,
    resolved_path,
    resolver_url,
    search_query,
    sold_location,
    sold_url,
    uprn_ref,
)

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "TransportError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError",)

#: Listing property types -> the Land Registry class used for sold prices.
SOLD_TYPE_OF = {
    "detached": "detached",
    "detached_bungalow": "detached",
    "link_detached": "detached",
    "semi_detached": "semi",
    "semi_detached_bungalow": "semi",
    "terraced": "terraced",
    "end_terrace": "terraced",
    "mid_terrace": "terraced",
    "terraced_bungalow": "terraced",
    "flat": "flat",
    "flats": "flat",
    "maisonette": "flat",
    "studio": "flat",
    "penthouse": "flat",
}
#: ``comparables(scope="auto")`` widens from the postcode to the outcode below this.
MIN_COMPARABLES = 5

log = logging.getLogger(__name__)


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


class _BadAnswer(Exception):
    """A page without the expected data (fetched once more)."""


class ZooplaScraper:
    """Zoopla listing search, listing details, sold prices, property history and comps.

    Args:
        api_key: Your ScrapeUnblocker API key. Defaults to the
            ``SCRAPEUNBLOCKER_KEY`` environment variable (read by the SDK).
        client: A ready ``scrapeunblocker.Client`` (or anything with a compatible
            ``get_page_source``); handy for tests.
        country: Country to route requests through (two-letter code, e.g. ``gb``).
            ``None`` lets ScrapeUnblocker choose, which works for Zoopla.
        max_retries: Extra attempts for a request that fails transiently.
        backoff: Seconds before the first retry; doubles on each retry.
        timeout: Seconds to wait for one API response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any = None,
        country: str | None = None,
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 180.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if client is None:
            from scrapeunblocker import Client

            client = Client(api_key=api_key, timeout=timeout)
        self.client = client
        self.country = country.strip().lower() if country else None
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        #: Number of API requests made so far.
        self.requests = 0
        self._resolved: dict[tuple[str, str], str | None] = {}
        self._sold_slugs: dict[str, str] = {}

    # -- fetching ----------------------------------------------------------------------

    def _get(self, url: str) -> str:
        kwargs: dict[str, Any] = {}
        if self.country:
            kwargs["proxy_country"] = self.country
        self.requests += 1
        try:
            body = self.client.get_page_source(url, **kwargs)
        except Exception as exc:
            if _is_named(exc, *_NOT_FOUND_NAMES):
                raise NotFoundError(f"Zoopla answered 404 for {url}") from exc
            raise
        return body if isinstance(body, str) else str(body)

    def fetch(self, url: str, parse: Callable[[str], Any]) -> Any:
        """Fetch ``url`` and return ``parse(page)``.

        Transient SDK errors are retried with doubling backoff. If ``parse`` raises
        ``ValueError`` the URL is fetched once more, then :class:`ParseError` is raised.
        :class:`NotFoundError` (a 404, an unknown place, a removed listing) is not retried.
        """
        attempt = 0
        bad_answers = 0
        while True:
            try:
                page = self._get(url)
                try:
                    return parse(page)
                except ValueError as exc:
                    bad_answers += 1
                    if bad_answers > 1:
                        raise ParseError(f"{exc} ({url})") from None
                    raise _BadAnswer(str(exc)) from None
            except (NotFoundError, ParseError):
                raise
            except Exception as exc:
                retryable = isinstance(exc, _BadAnswer) or _is_named(exc, *_TRANSIENT_NAMES)
                if not retryable or attempt >= self.max_retries:
                    if isinstance(exc, _BadAnswer):
                        raise ParseError(f"{exc} ({url})") from None
                    raise
                reason = str(exc) if isinstance(exc, _BadAnswer) else type(exc).__name__
                log.info("retrying %s after %s", url, reason)
                self.sleep(self.backoff * (2**attempt))
                attempt += 1

    # -- listing search ----------------------------------------------------------------

    def _query(
        self, location: str | SearchQuery, channel: str, filters: SearchFilters | None
    ) -> SearchQuery:
        if isinstance(location, SearchQuery):
            return location
        return search_query(location, channel, filters)

    def search(
        self,
        location: str | SearchQuery,
        channel: str = "sale",
        filters: SearchFilters | None = None,
        *,
        page: int = 1,
    ) -> SearchPage:
        """One page of search results (25 listings).

        ``location`` is a place name, outcode, postcode, Zoopla slug
        (``"london/islington"``) or a Zoopla search URL pasted from the browser.
        """
        query = self._query(location, channel, filters)
        if page < 1 or page > MAX_PAGES:
            raise InputError(f"page must be between 1 and {MAX_PAGES}")
        url = query.url(page)

        def parse(html: str) -> SearchPage:
            return parse_search(html, url, query.channel, page)

        try:
            result = self.fetch(url, parse)
        except NotFoundError as exc:
            # Some names need Zoopla's own resolver ("leeds" -> "west-yorkshire/leeds").
            text = query.text
            path = self.resolve(text, CHANNELS[query.channel]) if text else None
            if path is None:
                raise LocationNotFoundError(f"Zoopla could not place {text or url!r}") from exc
            apply_search_path(query, path)
            log.info("Zoopla resolved %r to %s", text, query.location)
            return self.search(query, page=page)
        result.warnings = _ignored(query.filters, result.applied)
        for warning in result.warnings:
            log.warning("%s (%s)", warning, url)
        return result

    def iter_pages(
        self,
        location: str | SearchQuery,
        channel: str = "sale",
        filters: SearchFilters | None = None,
        *,
        max_pages: int | None = 1,
        start_page: int = 1,
    ) -> Iterator[SearchPage]:
        """Search result pages from ``start_page`` until the last one or ``max_pages``."""
        query = self._query(location, channel, filters)
        limit = MAX_PAGES if max_pages is None else min(int(max_pages), MAX_PAGES)
        page = start_page
        while page < start_page + limit:
            result = self.search(query, page=page)
            yield result
            if not result.listings or not result.has_next:
                return
            page += 1

    def search_listings(
        self,
        locations: str | SearchQuery | Iterable[str | SearchQuery],
        channel: str = "sale",
        filters: SearchFilters | None = None,
        *,
        max_pages: int | None = 1,
        max_results: int | None = None,
        include_featured: bool = False,
    ) -> list[Listing]:
        """Listings for one or more searches, merged without duplicates.

        Zoopla shows a few paid "featured" slots above the results of each page (they can
        also be in the regular results); they are left out unless ``include_featured`` is
        set, then each page's slots come before its results, once per listing.
        """
        listings, _ = self._collect(
            locations,
            channel,
            filters,
            max_pages=max_pages,
            max_results=max_results,
            include_featured=include_featured,
        )
        return listings

    def _collect(
        self,
        locations: str | SearchQuery | Iterable[str | SearchQuery],
        channel: str,
        filters: SearchFilters | None,
        *,
        max_pages: int | None,
        max_results: int | None,
        include_featured: bool = False,
    ) -> tuple[list[Listing], bool]:
        """``(listings, complete)``; complete = every result of every search was read."""
        items = [locations] if isinstance(locations, (str, SearchQuery)) else list(locations)
        seen: set[int] = set()
        out: list[Listing] = []
        complete = True
        for location in items:
            query = self._query(location, channel, filters)
            last: SearchPage | None = None
            for result in self.iter_pages(query, max_pages=max_pages):
                last = result
                cards = (result.featured if include_featured else []) + result.listings
                for card in cards:
                    if card.listing_id in seen:
                        continue
                    seen.add(card.listing_id)
                    out.append(card)
                    if max_results is not None and len(out) >= max_results:
                        return out, False
            # Unread pages, or more results than Zoopla's 40 pages can show.
            shown = (last.page_count or last.page) * PAGE_SIZE if last else 0
            if last is None or last.has_next or (last.total_results or 0) > shown:
                complete = False
        return out, complete

    def resolve(self, text: str, section: str) -> str | None:
        """The path Zoopla's search box would use for ``text`` (``None`` if it has none).

        ``section`` is ``for-sale``, ``to-rent`` or ``house-prices``. Answers are cached
        for the life of the scraper.
        """
        key = (section, str(text).strip().lower())
        if key not in self._resolved:
            try:
                self._resolved[key] = self.fetch(resolver_url(text, section), resolved_path)
            except NotFoundError:
                self._resolved[key] = None
        return self._resolved[key]

    # -- listings ----------------------------------------------------------------------

    def listing(self, ref: Any) -> ListingDetails:
        """Full details of a listing by id or URL (sale, rent or new home)."""
        listing_id, section = listing_ref(ref)
        url = listing_url(listing_id, section)
        try:
            return self.fetch(url, lambda html: parse_listing(html, url))
        except ListingNotFoundError:
            raise
        except NotFoundError as exc:
            raise ListingNotFoundError(f"no Zoopla listing {listing_id}") from exc

    def listings(self, refs: Iterable[Any]) -> list[ListingDetails]:
        return [self.listing(ref) for ref in refs]

    # -- sold prices and property history ----------------------------------------------

    def sold_prices(
        self, location: str, filters: SoldFilters | None = None, *, page: int = 1
    ) -> SoldPricesPage:
        """One page (25) of sold prices for a town, area, outcode or full postcode."""
        if page < 1:
            raise InputError("page must be 1 or more")
        slug = self._sold_slugs.get(location) or sold_location(location)
        url = sold_url(slug, filters, page)
        try:
            return self.fetch(url, lambda html: parse_sold(html, url, slug, page))
        except NotFoundError as exc:
            path = None
            if needs_resolver(location) and location not in self._sold_slugs:
                path = self.resolve(location, "house-prices")
            if path is None or sold_location(path) == slug:
                raise LocationNotFoundError(f"Zoopla has no house prices for {location!r}") from exc
            self._sold_slugs[location] = sold_location(path)
            log.info("Zoopla resolved %r to %s", location, self._sold_slugs[location])
            return self.sold_prices(location, filters, page=page)

    def iter_sold_pages(
        self, location: str, filters: SoldFilters | None = None, *, max_pages: int | None = 1
    ) -> Iterator[SoldPricesPage]:
        page = 1
        while max_pages is None or page <= max_pages:
            result = self.sold_prices(location, filters, page=page)
            yield result
            if not result.records or not result.has_next:
                return
            page += 1

    def sold_price_records(
        self,
        locations: str | Iterable[str],
        filters: SoldFilters | None = None,
        *,
        max_pages: int | None = 1,
        max_results: int | None = None,
    ) -> list[SoldPrice]:
        """Sold-price records for one or more places, merged without duplicates."""
        items = [locations] if isinstance(locations, str) else list(locations)
        seen: set[tuple[Any, Any, Any]] = set()
        out: list[SoldPrice] = []
        for location in items:
            for result in self.iter_sold_pages(location, filters, max_pages=max_pages):
                for record in result.records:
                    key = (record.uprn or record.address, record.sold_on, record.price)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(record)
                    if max_results is not None and len(out) >= max_results:
                        return out
        return out

    def property_history(self, ref: Any) -> PropertyHistory:
        """A property's sale history and past listings by UPRN (or property URL)."""
        uprn = uprn_ref(ref)
        url = property_url(uprn)
        try:
            return self.fetch(url, lambda html: parse_property(html, url))
        except NotFoundError as exc:
            raise NotFoundError(f"Zoopla has no property with UPRN {uprn}") from exc

    def comparables(
        self,
        ref: Any,
        *,
        months: int = 12,
        scope: str = "auto",
        same_type: bool = True,
        same_beds: bool = True,
        max_pages: int = 1,
    ) -> Comparables:
        """Recent sold prices near a listing (its postcode, or its outcode).

        ``scope`` is ``postcode``, ``outcode`` or ``auto`` (postcode first, then the
        outcode when it has fewer than :data:`MIN_COMPARABLES` sales). Sales are
        filtered to the listing's property type and bedroom count unless
        ``same_type`` / ``same_beds`` are off. The statistics cover the records read.
        """
        if scope not in ("auto", "postcode", "outcode"):
            raise InputError("scope must be auto, postcode or outcode")
        details = ref if isinstance(ref, ListingDetails) else self.listing(ref)
        filters = SoldFilters(months=months, sort="newest")
        if same_type:
            filters.property_type = SOLD_TYPE_OF.get(details.property_type or "")
        if same_beds and details.bedrooms:
            filters.beds_min = filters.beds_max = details.bedrooms
        steps = {
            "auto": [("postcode", details.postcode), ("outcode", details.outcode)],
            "postcode": [("postcode", details.postcode)],
            "outcode": [("outcode", details.outcode)],
        }[scope]
        steps = [(name, place) for name, place in steps if place]
        if not steps:
            raise InputError(f"listing {details.listing_id} has no postcode to compare with")
        records: list[SoldPrice] = []
        used = steps[0]
        for used in steps:
            # A /house-prices/ path, so a postcode without sales is not sent to the resolver.
            path = f"/house-prices/{location_slug(used[1])}/"
            try:
                records = self.sold_price_records(path, filters, max_pages=max_pages)
            except LocationNotFoundError:
                records = []
            if len(records) >= MIN_COMPARABLES:
                break
        return _comparables(details, used[0], used[1], filters, records)

    # -- watch -------------------------------------------------------------------------

    def watch(
        self,
        locations: str | SearchQuery | Iterable[str | SearchQuery],
        state_path: str,
        channel: str = "sale",
        filters: SearchFilters | None = None,
        *,
        max_pages: int | None = 1,
    ) -> list[Change]:
        """Run a search and report what changed since the last run.

        The first run saves a baseline and returns no changes. Later runs report new
        listings, price drops and increases, listings that went under offer or came
        back, and (only when every result page was read) listings that disappeared.
        """
        listings, complete = self._collect(
            locations, channel, filters, max_pages=max_pages, max_results=None
        )
        now = snapshot(listings)
        before = load_state(state_path)
        changes = [] if before is None else diff(before, now, complete=complete)
        save_state(state_path, now if complete or before is None else {**before, **now})
        return changes


def _ignored(filters: SearchFilters, applied: dict[str, Any]) -> list[str]:
    """Filters that were asked for but are not in Zoopla's own report of the search."""
    if not applied:
        return []
    warnings = []
    if filters.sort:
        wanted = SORTS.get(filters.sort, filters.sort)
        got = str(applied.get("sort") or "")
        if got and not got.startswith(wanted):
            warnings.append(f"Zoopla sorted by {got!r}, not {wanted!r}")
    checks = ["beds_min", "beds_max"]
    if filters.price_frequency in (None, "month", "per_month"):
        checks += ["price_min", "price_max"]
    for name in checks:
        value = getattr(filters, name)
        if value is not None and applied.get(name) != int(value):
            warnings.append(f"Zoopla did not apply {name}={value}")
    if filters.radius is not None and applied.get("radius") is not None:
        if float(applied["radius"]) != float(filters.radius):
            warnings.append(f"Zoopla used radius {applied['radius']}, not {filters.radius}")
    return warnings


def _comparables(
    details: ListingDetails,
    scope: str,
    place: str | None,
    filters: SoldFilters,
    records: list[SoldPrice],
) -> Comparables:
    prices = [r.price for r in records if r.price]
    median = float(statistics.median(prices)) if prices else None
    asking = details.price if details.channel == "sale" else None
    versus = None
    if asking and median:
        versus = round((asking - median) / median * 100, 1)
    return Comparables(
        listing_id=details.listing_id,
        listing_url=details.url,
        asking_price=asking,
        address=details.address,
        scope=scope,
        location=place,
        filters=filters.describe(),
        count=len(prices),
        median_price=median,
        mean_price=round(statistics.fmean(prices), 2) if prices else None,
        min_price=min(prices) if prices else None,
        max_price=max(prices) if prices else None,
        asking_vs_median_percent=versus,
        records=records,
    )
