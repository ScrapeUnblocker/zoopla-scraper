"""Zoopla URLs: locations, search filters, listings, sold prices and property pages.

Every filter value below is one Zoopla's own search form uses, so the URLs are the
ones you get when you click through zoopla.co.uk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from html import unescape as html_unescape
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from .errors import InputError

BASE = "https://www.zoopla.co.uk"
#: Listings on one search results page.
PAGE_SIZE = 25
#: Zoopla shows at most 40 result pages (1,000 listings) for one search.
MAX_PAGES = 40
#: Sold-price records on one page.
SOLD_PAGE_SIZE = 25

CHANNELS = {"sale": "for-sale", "rent": "to-rent"}
_CHANNEL_ALIASES = {
    "sale": "sale",
    "for-sale": "sale",
    "buy": "sale",
    "rent": "rent",
    "to-rent": "rent",
    "let": "rent",
}

#: ``--sort`` names and the ``results_sort`` values Zoopla uses for them.
SORTS = {
    "recommended": "recommended",
    "newest": "newest_listings",
    "price-high": "highest_price",
    "price-low": "lowest_price",
    "most-reduced": "most_reduced",
}
#: Property types for listing searches (``property_sub_type``).
PROPERTY_TYPES = (
    "detached",
    "semi_detached",
    "terraced",
    "flats",
    "bungalow",
    "farms_land",
    "park_home",
)
_TYPE_ALIASES = {
    "semi": "semi_detached",
    "semi-detached": "semi_detached",
    "terrace": "terraced",
    "flat": "flats",
    "apartment": "flats",
    "apartments": "flats",
    "bungalows": "bungalow",
    "land": "farms_land",
    "farms-land": "farms_land",
    "park-home": "park_home",
}
#: Search radius options in miles (0 = this area only).
RADII = (0, 0.25, 0.5, 1, 3, 5, 10, 15, 20, 30, 40)
#: "Added to Zoopla" windows.
ADDED = {"24h": "24_hours", "3d": "3_days", "7d": "7_days", "14d": "14_days", "30d": "30_days"}
#: Rentals: "available from" windows.
AVAILABLE = {"now": "now", "1m": "1months", "3m": "3months", "6m": "6months", "12m": "12months"}
FURNISHED = ("furnished", "part_furnished", "unfurnished")
#: Rentals: what ``price_min`` / ``price_max`` are per.
PRICE_FREQ = {"month": "per_month", "week": "per_week"}
NEW_HOMES = ("include", "exclude", "only")
ONLY_OR_EXCLUDE = ("only", "exclude")

#: Sold prices: property types (Land Registry classes).
SOLD_TYPES = {"detached": "D", "semi": "S", "terraced": "T", "flat": "F"}
#: Sold prices: "last sold within" windows in months.
SOLD_MONTHS = (3, 6, 12, 60, 120, 240)
#: Sold prices: ``--sort`` names and Zoopla's ``sortOrder`` / ``sortDirection``.
SOLD_SORTS = {
    "newest": ("last_sale_date", "desc"),
    "oldest": ("last_sale_date", "asc"),
    "price-high": ("last_sale_price", "desc"),
    "price-low": ("last_sale_price", "asc"),
    "address": ("address", "asc"),
    "address-desc": ("address", "desc"),
}

_ZOOPLA_HOST = re.compile(r"(^|\.)zoopla\.co\.uk$", re.I)
_LISTING_PATH = re.compile(r"/(for-sale|to-rent|new-homes)/details/(\d+)", re.I)
_UPRN_PATH = re.compile(r"/property/uprn/(\d+)", re.I)
_SEARCH_PATH = re.compile(r"^/(for-sale|to-rent|new-homes)/([a-z0-9_-]+)/(.+?)/?$", re.I)
_SOLD_PATH = re.compile(r"^/house-prices/(.+?)/?$", re.I)
_RESOLVED = re.compile(r"(/(?:for-sale|to-rent|new-homes|house-prices)/[^\s\"'<>]*)")


def _choice(name: str, value: Any, options: Any, aliases: dict[str, str] | None = None) -> Any:
    key = str(value).strip().lower().replace(" ", "-")
    if aliases and key in aliases:
        return aliases[key]
    if isinstance(options, dict):
        if key in options:
            return options[key]
        if key in options.values():
            return key
        allowed = ", ".join(options)
    else:
        if key in options:
            return key
        allowed = ", ".join(str(o) for o in options)
    raise InputError(f"unknown {name} {value!r}; choose from: {allowed}")


def channel_name(value: str) -> str:
    """``sale`` or ``rent`` (also accepts ``for-sale``, ``to-rent``, ``buy`` and ``let``)."""
    key = str(value).strip().lower()
    if key not in _CHANNEL_ALIASES:
        raise InputError(f"unknown channel {value!r}; use sale or rent")
    return _CHANNEL_ALIASES[key]


def is_zoopla_url(text: str) -> bool:
    parts = urlsplit(str(text).strip())
    return parts.scheme in ("http", "https") and bool(_ZOOPLA_HOST.search(parts.hostname or ""))


def location_slug(location: str) -> str:
    """The URL slug Zoopla uses for a place.

    ``"Bristol"`` -> ``bristol``, ``"Milton Keynes"`` -> ``milton-keynes``,
    ``"BS9 4LY"`` -> ``bs9-4ly`` and ``"london/islington"`` stays as it is
    (copy the part after ``/property/`` from a Zoopla URL for areas inside a town).
    """
    text = str(location or "").strip().lower().replace("&", " and ")
    parts = [re.sub(r"[^a-z0-9]+", "-", p).strip("-") for p in text.split("/")]
    parts = [p for p in parts if p]
    if not parts:
        raise InputError("a location is needed, e.g. bristol, london/islington, bs9 or BS9 4LY")
    return "/".join(parts)


def _int(name: str, value: Any, low: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InputError(f"{name} must be a whole number, not {value!r}") from None
    if number < low:
        raise InputError(f"{name} must be at least {low}, not {value!r}")
    return number


def _flag(value: Any) -> str:
    return "true" if value else "false"


@dataclass
class SearchFilters:
    """Filters for a Zoopla listing search (any field left ``None`` is not sent).

    Prices are in pounds; for rentals they are per month unless
    ``price_frequency="per_week"``. ``size_min`` / ``size_max`` are in square feet.
    Fields marked *sale* or *rent* only apply to that channel.
    """

    beds_min: int | None = None
    beds_max: int | None = None
    baths_min: int | None = None
    baths_max: int | None = None
    price_min: int | None = None
    price_max: int | None = None
    property_types: list[str] = field(default_factory=list)
    radius: float | None = None
    keywords: str | None = None
    added: str | None = None
    sort: str | None = None
    size_min: int | None = None
    size_max: int | None = None
    reduced_only: bool = False
    retirement: str | None = None
    #: sale: ``include`` (Zoopla's default), ``exclude`` or ``only``.
    new_homes: str | None = None
    #: sale: also list properties that are under offer or sold STC.
    include_sold: bool = False
    #: sale
    chain_free: bool = False
    #: sale: ``only`` or ``exclude``.
    auction: str | None = None
    #: sale: ``only`` or ``exclude``.
    shared_ownership: str | None = None
    #: rent: ``per_month`` (default) or ``per_week`` for price_min / price_max.
    price_frequency: str | None = None
    #: rent: ``furnished``, ``part_furnished`` or ``unfurnished``.
    furnished: str | None = None
    #: rent
    pets_allowed: bool = False
    #: rent
    bills_included: bool = False
    #: rent: ``now``, ``1m``, ``3m``, ``6m`` or ``12m``.
    available: str | None = None
    #: rent: student accommodation ``only`` or ``exclude``.
    student: str | None = None
    #: rent: house shares / rooms ``only`` or ``exclude``.
    house_share: str | None = None

    _SALE_ONLY = ("new_homes", "include_sold", "chain_free", "auction", "shared_ownership")
    _RENT_ONLY = (
        "price_frequency",
        "furnished",
        "pets_allowed",
        "bills_included",
        "available",
        "student",
        "house_share",
    )

    def is_set(self, name: str) -> bool:
        value = getattr(self, name)
        return value not in (None, False, "", [])

    def describe(self) -> dict[str, Any]:
        """The filters that are set, as a plain dict."""
        return {f.name: getattr(self, f.name) for f in fields(self) if self.is_set(f.name)}

    def to_params(self, channel: str = "sale") -> list[tuple[str, str]]:
        """Query parameters for Zoopla, validated (raises :class:`InputError`)."""
        channel = channel_name(channel)
        wrong = self._RENT_ONLY if channel == "sale" else self._SALE_ONLY
        misplaced = [name for name in wrong if self.is_set(name)]
        if misplaced:
            other = "rent" if channel == "sale" else "sale"
            raise InputError(f"{', '.join(misplaced)} only apply to {other} searches")
        params: list[tuple[str, str]] = []
        for name in ("beds_min", "beds_max", "baths_min", "baths_max", "price_min", "price_max"):
            value = getattr(self, name)
            if value is not None:
                params.append((name, str(_int(name, value))))
        for low, high in (("beds_min", "beds_max"), ("price_min", "price_max")):
            a, b = getattr(self, low), getattr(self, high)
            if a is not None and b is not None and int(a) > int(b):
                raise InputError(f"{low} ({a}) is higher than {high} ({b})")
        if self.price_frequency:
            params.append(
                ("price_frequency", _choice("price frequency", self.price_frequency, PRICE_FREQ))
            )
        for kind in self.property_types or []:
            params.append(("property_sub_type", property_type(kind)))
        if self.radius is not None:
            params.append(("radius", _radius(self.radius)))
        if self.keywords:
            params.append(("keywords", str(self.keywords).strip()))
        if self.added:
            params.append(("added", _choice("added window", self.added, ADDED)))
        if self.sort:
            params.append(("results_sort", _choice("sort order", self.sort, SORTS)))
        if self.size_min is not None or self.size_max is not None:
            if self.size_min is not None:
                params.append(("floor_area_min", str(_int("size_min", self.size_min))))
            if self.size_max is not None:
                params.append(("floor_area_max", str(_int("size_max", self.size_max))))
            params.append(("floor_area_units", "sq_feet"))
        if self.reduced_only:
            params.append(("reduced_price_only", "true"))
        if self.retirement:
            params.append(("is_retirement_home", _only(self.retirement, "retirement")))
        if self.new_homes:
            params.append(("new_homes", _choice("new homes option", self.new_homes, NEW_HOMES)))
        if self.include_sold:
            params.append(("include_sold", "true"))
        if self.chain_free:
            params.append(("chain_free", "true"))
        if self.auction:
            params.append(("is_auction", _only(self.auction, "auction")))
        if self.shared_ownership:
            params.append(("is_shared_ownership", _only(self.shared_ownership, "shared ownership")))
        if self.furnished:
            params.append(("furnished_state", _choice("furnishing", self.furnished, FURNISHED)))
        if self.pets_allowed:
            params.append(("pets_allowed", "true"))
        if self.bills_included:
            params.append(("bills_included", "true"))
        if self.available:
            params.append(
                ("available_from", _choice("available window", self.available, AVAILABLE))
            )
        if self.student:
            params.append(("is_student_accommodation", _only(self.student, "student")))
        if self.house_share:
            params.append(("is_shared_accommodation", _only(self.house_share, "house share")))
        return params


def property_type(value: str) -> str:
    """A ``property_sub_type`` value (``semi`` -> ``semi_detached``, ``flat`` -> ``flats``)."""
    return _choice("property type", value, PROPERTY_TYPES, _TYPE_ALIASES)


def _radius(value: Any) -> str:
    try:
        miles = float(value)
    except (TypeError, ValueError):
        raise InputError(f"radius must be a number of miles, not {value!r}") from None
    if miles not in RADII:
        raise InputError(f"radius must be one of {', '.join(str(r) for r in RADII)} miles")
    return f"{miles:g}"


def _only(value: str, name: str) -> str:
    return _flag(_choice(f"{name} option", value, ONLY_OR_EXCLUDE) == "only")


@dataclass
class SearchQuery:
    """One listing search: where, sale or rent, and the filters."""

    location: str
    channel: str = "sale"
    filters: SearchFilters = field(default_factory=SearchFilters)
    #: Extra query parameters taken from a pasted Zoopla URL.
    extra: list[tuple[str, str]] = field(default_factory=list)
    #: Path between the channel and the location ("property", "houses", "flats", ...).
    kind: str = "property"
    #: The place as typed, when it may need Zoopla's location resolver (see
    #: :meth:`ZooplaScraper.search`); ``None`` for slugs with a ``/`` and pasted URLs.
    text: str | None = None

    def url(self, page: int = 1) -> str:
        params = [(k, v) for k, v in self.extra if k != "pn"]
        own = self.filters.to_params(self.channel)
        names = {k for k, _ in own}
        params = [(k, v) for k, v in params if k not in names] + own
        if page > 1:
            params.append(("pn", str(page)))
        path = f"/{CHANNELS[self.channel]}/{self.kind}/{quote(self.location, safe='/')}/"
        query = urlencode(params)
        return BASE + path + (f"?{query}" if query else "")


def search_query(
    location: str, channel: str = "sale", filters: SearchFilters | None = None
) -> SearchQuery:
    """A :class:`SearchQuery` for a place name, postcode, slug or pasted Zoopla search URL.

    For a pasted URL its own filters are kept; ``filters`` set here win over them.
    """
    filters = filters or SearchFilters()
    channel = channel_name(channel)
    text = str(location or "").strip()
    if is_zoopla_url(text):
        parts = urlsplit(text)
        match = _SEARCH_PATH.match(parts.path)
        if not match or match.group(2).lower() == "details":
            raise InputError(f"not a Zoopla search URL (listing pages go to `listing`): {text}")
        section, kind, place = match.groups()
        extra = parse_qsl(parts.query, keep_blank_values=False)
        if section.lower() == "new-homes":
            section = "for-sale"
            if not filters.new_homes and not any(k == "new_homes" for k, _ in extra):
                extra.append(("new_homes", "only"))
        return SearchQuery(
            location=place.lower(),
            channel=channel_name(section),
            filters=filters,
            extra=[(k, v) for k, v in extra if k not in ("search_source", "pn")],
            kind=kind.lower(),
        )
    slug = location_slug(text)
    return SearchQuery(
        location=slug, channel=channel, filters=filters, text=None if "/" in slug else text
    )


def apply_search_path(query: SearchQuery, path: str) -> SearchQuery:
    """Point ``query`` at a search path from Zoopla's resolver (keeps its filters)."""
    parts = urlsplit(path)
    match = _SEARCH_PATH.match(parts.path)
    if not match:
        raise InputError(f"not a Zoopla search path: {path}")
    query.location = match.group(3).lower()
    query.kind = match.group(2).lower()
    own = {k for k, _ in query.extra}
    query.extra += [(k, v) for k, v in parse_qsl(parts.query) if k == "q" and k not in own]
    query.text = None
    return query


def resolver_url(text: str, section: str) -> str:
    """Zoopla's own location resolver: free text in, the search path it uses out."""
    return f"{BASE}/api/search/resolver/?" + urlencode({"q": str(text).strip(), "section": section})


def resolved_path(body: str) -> str | None:
    """The path in a resolver answer (``None`` when Zoopla could not place the text)."""
    match = _RESOLVED.search(html_unescape(str(body or "")))
    return match.group(1) if match else None


def listing_ref(ref: Any) -> tuple[int, str | None]:
    """``(listing_id, section)`` from a listing id or Zoopla listing URL."""
    text = str(ref).strip()
    if text.isdigit():
        return int(text), None
    if is_zoopla_url(text):
        match = _LISTING_PATH.search(urlsplit(text).path)
        if match:
            return int(match.group(2)), match.group(1).lower()
    raise InputError(f"not a Zoopla listing id or URL: {ref!r}")


def listing_url(listing_id: int, section: str | None = None) -> str:
    """The details page; Zoopla redirects an id to its sale, rent or new-homes page."""
    return f"{BASE}/{section or 'for-sale'}/details/{int(listing_id)}/"


def uprn_ref(ref: Any) -> int:
    """A property's UPRN from the number or a ``/property/uprn/<n>/`` URL."""
    text = str(ref).strip()
    if text.isdigit():
        return int(text)
    if is_zoopla_url(text):
        match = _UPRN_PATH.search(urlsplit(text).path)
        if match:
            return int(match.group(1))
    raise InputError(f"not a Zoopla property UPRN or /property/uprn/ URL: {ref!r}")


def property_url(uprn: int) -> str:
    return f"{BASE}/property/uprn/{int(uprn)}/"


@dataclass
class SoldFilters:
    """Filters for sold house prices (``None`` / ``"any"`` = not filtered)."""

    property_type: str | None = None
    months: int | None = None
    beds_min: int | None = None
    beds_max: int | None = None
    baths_min: int | None = None
    baths_max: int | None = None
    sort: str | None = None

    def describe(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if getattr(self, f.name) not in (None, "", "any")
        }

    def to_params(self) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        if self.months not in (None, "", "all", "all-time"):
            months = _int("months", self.months, 1)
            if months not in SOLD_MONTHS:
                allowed = ", ".join(str(m) for m in SOLD_MONTHS)
                raise InputError(f"months must be one of {allowed} (or all), not {months}")
            params.append(("numMonths", str(months)))
        if self.property_type not in (None, "", "any"):
            code = _choice(
                "sold property type",
                self.property_type,
                SOLD_TYPES,
                {"semi-detached": "S", "semi_detached": "S", "terrace": "T", "flats": "F"},
            )
            params.append(("propertyTypeCode", code.upper()))
        for name in ("beds_min", "beds_max", "baths_min", "baths_max"):
            value = getattr(self, name)
            if value is not None:
                params.append((name, str(_int(name, value))))
        if self.sort:
            order, direction = SOLD_SORTS[_choice("sold sort order", self.sort, list(SOLD_SORTS))]
            params += [("sortOrder", order), ("sortDirection", direction)]
        return params


def sold_location(location: str) -> str:
    """The ``/house-prices/<slug>/`` slug for a place, postcode, pasted URL or resolver path."""
    text = str(location or "").strip()
    if is_zoopla_url(text) or text.startswith("/house-prices/"):
        match = _SOLD_PATH.match(urlsplit(text).path)
        if not match:
            raise InputError(f"not a Zoopla house prices URL: {text}")
        return match.group(1).lower()
    return location_slug(text)


def needs_resolver(location: str) -> bool:
    """Free text (not a URL or a ``/``-separated Zoopla slug) may need the resolver."""
    text = str(location or "").strip()
    return not is_zoopla_url(text) and "/" not in text


def sold_url(location: str, filters: SoldFilters | None = None, page: int = 1) -> str:
    params = (filters or SoldFilters()).to_params()
    if page > 1:
        params.append(("pn", str(page)))
    query = urlencode(params)
    slug = quote(sold_location(location), safe="/")
    return f"{BASE}/house-prices/{slug}/" + (f"?{query}" if query else "")


def absolute(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else BASE + path
