"""Scrape Zoopla (zoopla.co.uk) property data via the ScrapeUnblocker API.

Search homes for sale or to rent with Zoopla's own filters, open full listing details,
pull sold house prices for any town, outcode or postcode, read a property's sale
history, and compare a listing with recent sales nearby::

    from zoopla_scraper import SearchFilters, ZooplaScraper

    zoopla = ZooplaScraper()  # reads SCRAPEUNBLOCKER_KEY from the environment
    homes = zoopla.search_listings(
        "bristol", filters=SearchFilters(beds_min=3, price_max=450_000), max_pages=2
    )
    details = zoopla.listing(homes[0].listing_id)
    comps = zoopla.comparables(details)

Every request goes through the ScrapeUnblocker ``getPageSource`` API using the
official ``scrapeunblocker`` SDK:
https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos
"""

from .errors import (
    InputError,
    ListingNotFoundError,
    LocationNotFoundError,
    NotFoundError,
    ParseError,
    ZooplaError,
)
from .export import render, to_csv_file, write
from .models import (
    Agent,
    Change,
    Comparables,
    Listing,
    ListingDetails,
    Photo,
    PreviousListing,
    PriceChange,
    PropertyHistory,
    PropertySale,
    SearchPage,
    SoldPrice,
    SoldPricesPage,
)
from .scraper import ZooplaScraper
from .urls import SearchFilters, SearchQuery, SoldFilters, search_query

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "Change",
    "Comparables",
    "InputError",
    "Listing",
    "ListingDetails",
    "ListingNotFoundError",
    "LocationNotFoundError",
    "NotFoundError",
    "ParseError",
    "Photo",
    "PreviousListing",
    "PriceChange",
    "PropertyHistory",
    "PropertySale",
    "SearchFilters",
    "SearchPage",
    "SearchQuery",
    "SoldFilters",
    "SoldPrice",
    "SoldPricesPage",
    "ZooplaError",
    "ZooplaScraper",
    "__version__",
    "render",
    "search_query",
    "to_csv_file",
    "write",
]
