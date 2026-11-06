"""Offline fixtures: small Zoopla pages built from the shapes of real ones, and a fake SDK.

Nothing here talks to the network or spends API credit.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

# -- page builders ---------------------------------------------------------------------


def flight_page(rows: list[str], title: str = "Property for sale - Zoopla") -> str:
    """An App Router page whose React payload is ``rows`` (split over two script chunks)."""
    payload = "".join(rows)
    middle = len(payload) // 2
    chunks = [payload[:middle], payload[middle:]]
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(chunk)}])</script>" for chunk in chunks
    )
    return f"<html><head><title>{title}</title></head><body>{scripts}</body></html>"


def json_row(row_id: str, value: Any) -> str:
    # Compact, like the real payload.
    return f"{row_id}:{json.dumps(value, ensure_ascii=False, separators=(',', ':'))}\n"


def text_row(row_id: str, text: str) -> str:
    return f"{row_id}:T{len(text.encode('utf-8')):x},{text}"


def next_page(page_props: dict[str, Any], title: str = "Zoopla") -> str:
    data = {"props": {"pageProps": page_props}, "page": "/x", "query": {}}
    return (
        f"<html><head><title>{title}</title></head><body>"
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        "</body></html>"
    )


# -- search results --------------------------------------------------------------------


def sale_card(listing_id: int = 74000001, **extra: Any) -> dict[str, Any]:
    card = {
        "address": "Elm Road, Clifton, Bristol BS8",
        "alternativeRentFrequencyLabel": None,
        "branch": {
            "branchDetailsUri": "/find-agents/branch/example-homes-bristol-1001/",
            "branchId": 1001,
            "logoUrl": "https://st.zoocdn.com/zoopla_static_agent_logo_(1).png",
            "name": "Example Homes - Bristol",
            "phone": "0117 000 0000",
        },
        "derivedBuyerIncentives": None,
        "highlights": [{"description": None, "label": "Good Schools"}],
        "priceCurrency": "GBP",
        "displayType": "standard",
        "featuredType": None,
        "features": [
            {"content": 2, "iconId": "bath"},
            {"content": 3, "iconId": "bed"},
            {"content": 1, "iconId": "chair"},
            {"content": 1076, "iconId": "area"},
        ],
        "gallery": ["b2.jpg", "c3.jpg"],
        "image": {"src": "https://lid.zoocdn.com/645/430/a1.jpg"},
        "isPremium": False,
        "listingId": str(listing_id),
        "listingUris": {"detail": f"/for-sale/details/{listing_id}/"},
        "numberOfFloorPlans": 1,
        "numberOfImages": 3,
        "numberOfVideos": 0,
        "price": "£375,000",
        "priceTitle": "Guide price",
        "priceUnformatted": 375000,
        "propertyType": "semi_detached",
        "publishedOn": "5th Nov 2026",
        "publishedOnLabel": "Listed on",
        "sizeSqft": 1076,
        "sizeSource": "comparables_epc",
        "summaryDescription": "A bright three bedroom home &amp; garden.",
        "enrichmentTags": ["garden", "freehold"],
        "tags": [{"content": "Chain free"}, {"content": "Freehold"}],
        "title": "3 bed semi-detached house for sale",
        "flag": "Just added",
        "underOffer": False,
        "availableFrom": None,
        "priceDrop": None,
        "pos": {"lat": 51.46, "lng": -2.61},
        "listingType": "regular",
    }
    card.update(extra)
    return card


def rent_card(listing_id: int = 74000101) -> dict[str, Any]:
    # A weekly-advertised rental: priceUnformatted is per week, the label per month.
    return sale_card(
        listing_id,
        address="Bendix Street, Manchester M4",
        price="£8,017 pcm",
        priceTitle="",
        priceUnformatted=1850,
        alternativeRentFrequencyLabel="£1850 pw",
        listingUris={"detail": f"/to-rent/details/{listing_id}/"},
        availableFrom="14th Nov 2026",
        title="5 bed terraced house to rent",
        propertyType="terraced",
    )


def search_rows(
    cards: list[dict[str, Any]] | None = None,
    *,
    page: int = 1,
    page_max: int = 3,
    total: int = 70,
    featured: list[dict[str, Any]] | None = None,
    sort: str = "newest_listings",
    beds_min: str | None = "3",
    price_max: str | None = None,
) -> list[str]:
    cards = [sale_card()] if cards is None else cards
    taxonomy = {
        "activity": "listing_search",
        "areaName": "Bristol",
        "bedsMax": None,
        "bedsMin": beds_min,
        "priceMax": price_max,
        "priceMin": None,
        "radius": None,
        "resultsSort": sort,
        "section": "for-sale",
        "totalResults": total,
    }
    return [
        json_row("1", ["$", "div", None, {"taxonomy": taxonomy}]),
        json_row(
            "2",
            {
                "regularListingsFormatted": cards,
                "extendedListingsFormatted": [],
                "featuredProperties": featured or [],
                "breadcrumbs": [
                    {"label": "Zoopla", "uri": "/"},
                    {"label": "3+ bedroom  houses for sale", "uri": None},
                ],
                "pagination": {
                    "pageNumber": page,
                    "pageNumberMax": page_max,
                    "totalResults": total,
                    "totalResultsWasLimited": False,
                },
            },
        ),
    ]


def search_page(*args: Any, **kwargs: Any) -> str:
    return flight_page(search_rows(*args, **kwargs))


def empty_location_page() -> str:
    """What Zoopla shows for a name it cannot place: no results and no paging."""
    rows = [json_row("2", {"regularListingsFormatted": [], "pagination": None})]
    return flight_page(rows, "Property for sale in - Zoopla")


def home_page() -> str:
    return flight_page(
        [json_row("1", {"x": 1})],
        "Zoopla &gt; Search Property to Buy, Rent, House Prices, Estate Agents",
    )


# -- listing details -------------------------------------------------------------------

LISTING_DATA: dict[str, Any] = {
    "__typename": "ListingData",
    "displayAddress": "Elm Road, Clifton, Bristol BS8",
    "listingId": "74000001",
    "section": "for-sale",
    "title": "3 bed semi-detached house for sale",
    "propertyType": "semi_detached",
    "detailedDescription": "$a1",
    "additionalLinks": [{"caption": "Brochure", "original": "https://example.com/b.pdf"}],
    "additionalNtsInfo": [
        {"title": "Water", "key": "water", "value": "Mains"},
        {"title": "Parking", "key": "parking", "value": "Driveway"},
    ],
    "analyticsTaxonomy": {
        "areaName": "Clifton, Bristol",
        "chainFree": True,
        "currencyCode": "GBP",
        "furnishedState": None,
        "incode": "2AB",
        "isRetirementHome": False,
        "isSharedOwnership": False,
        "listingCondition": "pre-owned",
        "listingId": 74000001,
        "listingStatus": "for_sale",
        "nearestStations": ["Clifton Down", "Redland"],
        "nearestStationsInMiles": [0.4, 0.9],
        "outcode": "BS8",
        "postTownName": "Bristol",
    },
    "counts": {"numBathrooms": 2, "numBedrooms": 3, "numLivingRooms": 1},
    "floorArea": {"label": "1,076 sq. ft", "unitsLabel": "sq. ft", "value": 1076},
    "ingested": {"sizeSqft": 1076, "sizeSource": "structured_data"},
    "statusSummary": {"label": "Reduced"},
    "branchV2": {
        "branchDetailsUri": "/find-agents/branch/example-homes-bristol-1001/",
        "branchId": 1001,
        "branchName": "Example Homes - Bristol",
        "logoUrl": "https://st.zoocdn.com/zoopla_static_agent_logo_(1).png",
        "redirectPhone": "0117 000 0000",
        "isDeveloper": False,
    },
    "epc": {"image": [{"caption": "EPC", "filename": "epc1.png"}]},
    "derivedEPC": {"efficiencyRating": "C"},
    "location": {
        "coordinates": {"latitude": 51.46, "longitude": -2.61},
        "outcode": "BS8",
        "region": "South West England",
    },
    "features": {"bullets": ["Garden &amp; garage", "No onward chain"], "highlights": None},
    "propertyImage": [
        {"caption": "Kitchen", "filename": "p1.jpg"},
        {"caption": "IMG_0042.JPG", "filename": "p2.jpg"},
    ],
    "embeddedContent": {
        "tours": [{"url": "https://example.com/tour"}],
        "videos": [{"url": "https://example.com/video"}],
        "links": None,
    },
    "floorPlan": {"image": [{"caption": None, "filename": "fp1.jpg"}], "pdf": None},
    "pricing": {
        "alternateRentFrequencyPrice": None,
        "priceQualifierLabel": "Offers over",
        "label": "£375,000",
        "internalValue": 375000,
        "currencyCode": "GBP",
        "rentFrequencyLabel": None,
        "isAuction": False,
        "qualifier": "offers_over",
    },
    "tagsV2": [{"label": "Chain free"}, {"label": "Leasehold"}],
    "ntsInfo": [
        {"title": "Tenure", "value": "Leasehold (125 years)", "key": "tenure"},
        {"title": "Council tax band", "value": "D", "key": "council_tax_band"},
        {"title": "Service charge", "value": "£1,200 per year", "key": "service_charge"},
        {"title": None, "value": "Not available", "key": None},
    ],
    "derived": {"buyerIncentives": None},
    "publishedOn": "2026-04-14T17:34:00",
    "sharedOwnership": False,
    "priceHistory": {
        "priceChanges": [
            {"isPriceDrop": True, "priceChangeDate": "2026-05-13T10:59:57"},
            {"isPriceDrop": True, "priceChangeDate": "2026-10-21T01:44:00"},
        ]
    },
}

DESCRIPTION = "<b>Bright</b> family home.<br><br>Close to the Downs &amp; the avenue’s shops."


def listing_rows(data: dict[str, Any] | None = None, description: str = DESCRIPTION) -> list[str]:
    data = LISTING_DATA if data is None else data
    # Zoopla repeats the object; one copy only points at the other with "$" references.
    stub = {
        k: (v if not isinstance(v, (dict, list)) else f"$d4:props:{k}") for k, v in data.items()
    }
    return [
        json_row("3", ["$", "$L5", None, stub]),
        text_row("a1", description),
        json_row("4", ["$", "$L6", None, data]),
    ]


def listing_page(data: dict[str, Any] | None = None, **kwargs: Any) -> str:
    return flight_page(listing_rows(data, **kwargs), "Elm Road - Zoopla")


def rent_listing_data() -> dict[str, Any]:
    data = copy.deepcopy(LISTING_DATA)
    data["section"] = "to-rent"
    data["pricing"] = {
        "alternateRentFrequencyPrice": {"label": "£565 pw", "rentFrequencyLabel": "pw"},
        "label": "£2,450 pcm",
        "internalValue": 2450,
        "currencyCode": "GBP",
        "rentFrequencyLabel": "pcm",
        "isAuction": False,
    }
    data["ntsInfo"] = [{"title": "Deposit", "value": "£2,826", "key": "deposit"}]
    return data


# -- sold prices and property pages ----------------------------------------------------


def sold_node(uprn: int, price: int, date: str = "2026-08-20", **attrs: Any) -> dict[str, Any]:
    attributes = {
        "bathrooms": 1,
        "bedrooms": 3,
        "livingRooms": 1,
        "propertyType": "Semi-Detached House",
        "tenure": "Freehold",
        "floorAreaSqM": 96,
    }
    attributes.update(attrs)
    return {
        "node": {
            "uprn": str(uprn),
            "lastSale": {"date": f"{date}T12:00:00.000Z", "price": price},
            "address": {
                "uprn": str(uprn),
                "fullAddress": f"{uprn} Elm Road, Bristol, BS8 2AB",
                "postcode": "BS8 2AB",
                "latitude": 51.46,
                "longitude": -2.61,
            },
            "attributes": attributes,
        }
    }


def sold_page(
    nodes: list[dict[str, Any]] | None = None, *, has_next: bool = False, total: int = 2
) -> str:
    nodes = (
        [sold_node(101, 400000), sold_node(102, 350000, "2026-07-01")] if nodes is None else nodes
    )
    return next_page(
        {
            "propertiesSearch": {
                "pageInfo": {"hasNextPage": has_next},
                "totalResults": total,
                "edges": nodes,
            },
            "activity": {"all": 387951, "detached": 546953, "flat": 0, "terraced": 1, "semi": 2},
            "areaName": "Bristol",
            "pageType": "town",
            "taxonomy": {"resultsSort": "last_sale_date"},
        },
        "Sold house prices in Bristol - Zoopla",
    )


def property_page() -> str:
    return next_page(
        {
            "property": {
                "uprn": "159652",
                "address": {
                    "fullAddress": "37 Elm Road, Bristol, BS13 8LE",
                    "postcode": "BS13 8LE",
                    "country": "England",
                    "outcode": "BS13",
                    "latitude": 51.41,
                    "longitude": -2.61,
                },
                "attributes": {
                    "bedrooms": 5,
                    "bathrooms": None,
                    "livingRooms": None,
                    "tenure": "Freehold",
                    "propertyType": "Semi-Detached House",
                    "floorAreaSqM": None,
                },
                "energy": {"currentEnergyRating": "D"},
                "liveListings": [],
                "history": {
                    "historicListings": [
                        {
                            "attributes": {"bedrooms": 5, "bathrooms": None, "livingRooms": None},
                            "date": "2026-06-01",
                            "floorplans": [{"large": "https://lid.zoocdn.com/u/1024/768/f.jpg"}],
                            "images": [{"large": "https://lid.zoocdn.com/1024/768/i.jpg"}],
                            "price": 325000,
                            "priceType": None,
                            "uri": "/property-history/37-elm-road/bristol/bs13-8le/73335798",
                        }
                    ],
                    "historicSales": [
                        {
                            "date": "2026-08-28",
                            "price": 325000,
                            "percentageChange": 158.9641,
                            "numericChange": 199500,
                        },
                        {
                            "date": "2000-08-01",
                            "price": 125500,
                            "percentageChange": None,
                            "numericChange": None,
                        },
                    ],
                    "soldPricesDataSource": "landRegistry",
                },
            }
        }
    )


# -- fake SDK --------------------------------------------------------------------------


class TargetNotFoundError(Exception):
    """Named like the SDK's 404 error (the scraper matches errors by class name)."""


class BlockedError(Exception):
    """Named like the SDK's transient block error."""


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``: answers by URL, records every call.

    ``routes`` maps a URL (or a URL prefix ending in ``*``) to a page, an exception, or a
    list of those served in turn.
    """

    def __init__(self, routes: dict[str, Any]):
        self.routes = {k: (list(v) if isinstance(v, list) else v) for k, v in routes.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _answer(self, url: str) -> Any:
        if url in self.routes:
            return self.routes[url]
        for key, value in self.routes.items():
            if key.endswith("*") and url.startswith(key[:-1]):
                return value
        raise AssertionError(f"unexpected URL {url}")

    def get_page_source(self, url: str, **kwargs: Any) -> str:
        self.calls.append((url, kwargs))
        answer = self._answer(url)
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def make_scraper():
    from zoopla_scraper import ZooplaScraper

    def build(routes: dict[str, Any], **kwargs: Any):
        client = FakeClient(routes)
        sleeps: list[float] = []
        scraper = ZooplaScraper(client=client, sleep=sleeps.append, **kwargs)
        scraper.sleeps = sleeps  # type: ignore[attr-defined]
        return scraper, client

    return build
