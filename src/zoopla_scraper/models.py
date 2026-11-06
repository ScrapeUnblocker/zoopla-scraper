"""Records returned by the scraper: dataclasses with ``to_dict``, ``to_row`` and table layouts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _money(value: float | None, suffix: str | None = None) -> str:
    if value is None:
        return "-"
    text = f"£{value:,.0f}" if float(value).is_integer() else f"£{value:,.2f}"
    return f"{text} {suffix}" if suffix else text


def _num(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _rooms(beds: int | None, baths: int | None) -> str:
    return f"{_num(beds)}bd/{_num(baths)}ba"


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[call-overload]

    def to_row(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass
class Agent(_Record):
    """The estate agent, letting agent or developer branch behind a listing."""

    name: str | None = None
    branch_id: int | None = None
    phone: str | None = None
    url: str | None = None
    logo: str | None = None
    is_developer: bool | None = None


@dataclass
class Listing(_Record):
    """One property on a Zoopla search results page."""

    listing_id: int
    url: str
    channel: str
    title: str | None = None
    address: str | None = None
    outcode: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    receptions: int | None = None
    size_sqft: int | None = None
    size_source: str | None = None
    #: The headline price: the asking price, or the monthly rent for rentals.
    price: float | None = None
    #: ``pcm`` or ``pw`` for rentals, ``None`` for sales.
    price_frequency: str | None = None
    price_label: str | None = None
    price_qualifier: str | None = None
    rent_pcm: float | None = None
    rent_pw: float | None = None
    currency: str | None = None
    price_drop_amount: float | None = None
    price_drop_percent: float | None = None
    price_reduced_on: str | None = None
    first_price_on: str | None = None
    listed_on: str | None = None
    status: str | None = None
    under_offer: bool | None = None
    available_from: str | None = None
    new_home: bool = False
    tags: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    buyer_incentives: list[str] = field(default_factory=list)
    summary: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    agent: Agent = field(default_factory=Agent)
    image: str | None = None
    images: list[str] = field(default_factory=list)
    image_count: int | None = None
    floor_plan_count: int | None = None
    video_count: int | None = None
    #: Zoopla's advert tier: ``standard``, ``premium`` or ``premium_plus``.
    listing_tier: str | None = None
    #: A paid "featured" slot at the top of the results (the same listing can also be
    #: in the regular results).
    featured: bool = False
    page: int | None = None
    position: int | None = None

    TABLE_HEADER = ("id", "price", "rooms", "type", "sqft", "address", "listed", "status")

    def to_row(self) -> dict[str, Any]:
        row = self.to_dict()
        agent = row.pop("agent") or {}
        row["agent_name"] = agent.get("name")
        row["agent_phone"] = agent.get("phone")
        row["agent_url"] = agent.get("url")
        row["images"] = "; ".join(self.images)
        return row

    def table_row(self) -> tuple[str, ...]:
        return (
            str(self.listing_id),
            _money(self.price, self.price_frequency),
            _rooms(self.bedrooms, self.bathrooms),
            self.property_type or "-",
            _num(self.size_sqft),
            self.address or "-",
            self.listed_on or "-",
            self.status or ("under offer" if self.under_offer else "-"),
        )


@dataclass
class SearchPage(_Record):
    """One page of search results plus what Zoopla says about the search."""

    url: str
    channel: str
    page: int
    page_count: int | None
    total_results: int | None
    listings: list[Listing] = field(default_factory=list)
    featured: list[Listing] = field(default_factory=list)
    #: Zoopla's own wording for the search, e.g. "3+ bedroom houses for sale".
    description: str | None = None
    #: The filters Zoopla says it applied (sort, prices, beds, radius, area).
    applied: dict[str, Any] = field(default_factory=dict)
    #: Filters you asked for that Zoopla did not apply.
    warnings: list[str] = field(default_factory=list)

    @property
    def has_next(self) -> bool:
        return bool(self.page_count) and self.page < int(self.page_count or 0)


@dataclass
class Photo(_Record):
    url: str
    caption: str | None = None


@dataclass
class PriceChange(_Record):
    date: str | None
    is_drop: bool | None


@dataclass
class ListingDetails(_Record):
    """Everything on a Zoopla listing page."""

    listing_id: int
    url: str
    channel: str
    title: str | None = None
    address: str | None = None
    postcode: str | None = None
    outcode: str | None = None
    area: str | None = None
    post_town: str | None = None
    region: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    receptions: int | None = None
    floor_area_sqft: float | None = None
    size_source: str | None = None
    price: float | None = None
    price_frequency: str | None = None
    price_label: str | None = None
    price_qualifier: str | None = None
    rent_pcm: float | None = None
    rent_pw: float | None = None
    currency: str | None = None
    is_auction: bool | None = None
    listing_status: str | None = None
    listing_condition: str | None = None
    status: str | None = None
    published_at: str | None = None
    price_changes: list[PriceChange] = field(default_factory=list)
    tenure: str | None = None
    lease_years_remaining: int | None = None
    council_tax_band: str | None = None
    ground_rent: str | None = None
    service_charge: str | None = None
    deposit: str | None = None
    #: Every "key information" row Zoopla shows (tenure, council tax, ground rent,
    #: service charge, deposit, ...), keyed by Zoopla's own name.
    key_facts: dict[str, str] = field(default_factory=dict)
    #: Water, heating, electricity, sewerage, broadband, mobile coverage, parking.
    utilities: dict[str, str] = field(default_factory=dict)
    epc_rating: str | None = None
    chain_free: bool | None = None
    furnished_state: str | None = None
    shared_ownership: bool | None = None
    retirement_home: bool | None = None
    buyer_incentives: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    description: str | None = None
    description_html: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nearest_stations: list[dict[str, Any]] = field(default_factory=list)
    agent: Agent = field(default_factory=Agent)
    photos: list[Photo] = field(default_factory=list)
    floor_plans: list[str] = field(default_factory=list)
    epc_images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    virtual_tours: list[str] = field(default_factory=list)
    brochures: list[str] = field(default_factory=list)

    TABLE_HEADER = ("id", "price", "rooms", "type", "sqft", "tenure", "epc", "postcode", "agent")

    def to_row(self) -> dict[str, Any]:
        row = self.to_dict()
        agent = row.pop("agent") or {}
        row["agent_name"] = agent.get("name")
        row["agent_phone"] = agent.get("phone")
        row["agent_url"] = agent.get("url")
        row["photos"] = "; ".join(p.url for p in self.photos)
        row["price_changes"] = "; ".join(
            f"{c.date}{' (drop)' if c.is_drop else ''}" for c in self.price_changes
        )
        row["nearest_stations"] = "; ".join(
            f"{s.get('name')} ({s.get('miles')} mi)" for s in self.nearest_stations
        )
        row.pop("description_html", None)
        return row

    def table_row(self) -> tuple[str, ...]:
        return (
            str(self.listing_id),
            _money(self.price, self.price_frequency),
            _rooms(self.bedrooms, self.bathrooms),
            self.property_type or "-",
            _num(self.floor_area_sqft),
            self.tenure or "-",
            self.epc_rating or "-",
            self.postcode or "-",
            self.agent.name or "-",
        )


@dataclass
class SoldPrice(_Record):
    """One sold property: the last price paid (HM Land Registry data shown by Zoopla)."""

    uprn: int | None
    address: str | None
    postcode: str | None = None
    sold_on: str | None = None
    price: int | None = None
    property_type: str | None = None
    tenure: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    receptions: int | None = None
    floor_area_sqm: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_url: str | None = None
    page: int | None = None
    position: int | None = None

    TABLE_HEADER = ("sold", "price", "type", "beds", "sqm", "tenure", "address")

    def table_row(self) -> tuple[str, ...]:
        return (
            self.sold_on or "-",
            _money(self.price),
            self.property_type or "-",
            _num(self.bedrooms),
            _num(self.floor_area_sqm),
            self.tenure or "-",
            self.address or "-",
        )


@dataclass
class SoldPricesPage(_Record):
    """One page of sold prices for a town, area, outcode or postcode."""

    url: str
    location: str
    page: int
    area: str | None = None
    area_type: str | None = None
    total_results: int | None = None
    has_next: bool = False
    #: Average sold price over the last 12 months by property type (``None`` = no sales).
    average_prices: dict[str, int | None] = field(default_factory=dict)
    sort: str | None = None
    records: list[SoldPrice] = field(default_factory=list)


@dataclass
class PropertySale(_Record):
    date: str | None
    price: int | None
    change_amount: int | None = None
    change_percent: float | None = None


@dataclass
class PreviousListing(_Record):
    date: str | None
    price: int | None
    price_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    receptions: int | None = None
    url: str | None = None
    images: list[str] = field(default_factory=list)
    floor_plans: list[str] = field(default_factory=list)


@dataclass
class PropertyHistory(_Record):
    """A property's page: its details, every recorded sale and its past Zoopla listings."""

    uprn: int
    url: str
    address: str | None = None
    postcode: str | None = None
    outcode: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    property_type: str | None = None
    tenure: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    receptions: int | None = None
    floor_area_sqm: float | None = None
    epc_rating: str | None = None
    listed_now: bool = False
    sales: list[PropertySale] = field(default_factory=list)
    sales_source: str | None = None
    previous_listings: list[PreviousListing] = field(default_factory=list)

    TABLE_HEADER = ("uprn", "address", "type", "beds", "last sold", "price", "sales")

    def to_row(self) -> dict[str, Any]:
        row = self.to_dict()
        row["sales"] = "; ".join(f"{s.date} {_money(s.price)}" for s in self.sales)
        row["previous_listings"] = "; ".join(
            f"{p.date} {_money(p.price)}" for p in self.previous_listings
        )
        return row

    def table_row(self) -> tuple[str, ...]:
        last = self.sales[0] if self.sales else None
        return (
            str(self.uprn),
            self.address or "-",
            self.property_type or "-",
            _num(self.bedrooms),
            (last.date if last else None) or "-",
            _money(last.price if last else None),
            str(len(self.sales)),
        )


@dataclass
class Comparables(_Record):
    """Recent sold prices near a listing, with summary statistics of the records found."""

    listing_id: int
    listing_url: str
    asking_price: float | None
    address: str | None
    scope: str
    location: str | None
    filters: dict[str, Any] = field(default_factory=dict)
    count: int = 0
    median_price: float | None = None
    mean_price: float | None = None
    min_price: int | None = None
    max_price: int | None = None
    #: How far the asking price is above (+) or below (-) the median sold price, in percent.
    asking_vs_median_percent: float | None = None
    records: list[SoldPrice] = field(default_factory=list)

    TABLE_HEADER = ("listing", "asking", "scope", "sold", "median", "min", "max", "vs median")

    def to_row(self) -> dict[str, Any]:
        row = self.to_dict()
        row.pop("records")
        return row

    def csv_rows(self) -> list[dict[str, Any]]:
        """CSV: one row per sold comparable."""
        return [{"comparable_for": self.listing_id, **r.to_row()} for r in self.records]

    def table_row(self) -> tuple[str, ...]:
        diff = self.asking_vs_median_percent
        return (
            str(self.listing_id),
            _money(self.asking_price),
            f"{self.scope} {self.location or ''}".strip(),
            str(self.count),
            _money(self.median_price),
            _money(self.min_price),
            _money(self.max_price),
            "-" if diff is None else f"{diff:+.1f}%",
        )


@dataclass
class Change(_Record):
    """A difference between two runs of :meth:`ZooplaScraper.watch`."""

    kind: str
    listing_id: int
    url: str | None = None
    address: str | None = None
    old_price: float | None = None
    new_price: float | None = None
    price_frequency: str | None = None
    change_percent: float | None = None
    status: str | None = None

    #: Every kind of change ``watch`` reports.
    KINDS = (
        "new",
        "price_drop",
        "price_increase",
        "under_offer",
        "back_on_market",
        "removed",
    )
    TABLE_HEADER = ("change", "id", "old", "new", "pct", "address")

    def table_row(self) -> tuple[str, ...]:
        pct = "-" if self.change_percent is None else f"{self.change_percent:+.1f}%"
        return (
            self.kind,
            str(self.listing_id),
            _money(self.old_price, self.price_frequency),
            _money(self.new_price, self.price_frequency),
            pct,
            self.address or "-",
        )
