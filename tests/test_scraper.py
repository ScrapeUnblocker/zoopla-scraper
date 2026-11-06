import json

import pytest
from conftest import (
    BlockedError,
    TargetNotFoundError,
    empty_location_page,
    flight_page,
    json_row,
    listing_page,
    property_page,
    rent_card,
    sale_card,
    search_page,
    sold_node,
    sold_page,
)

from zoopla_scraper import (
    ListingNotFoundError,
    LocationNotFoundError,
    ParseError,
    SearchFilters,
)

BASE = "https://www.zoopla.co.uk"
BRISTOL = f"{BASE}/for-sale/property/bristol/"


def test_search_builds_the_url_and_parses(make_scraper):
    url = f"{BRISTOL}?beds_min=3&results_sort=newest_listings"
    scraper, client = make_scraper({url: search_page()})
    result = scraper.search("Bristol", filters=SearchFilters(beds_min=3, sort="newest"))
    assert [c.listing_id for c in result.listings] == [74000001]
    assert result.warnings == []
    assert client.calls == [(url, {})]


def test_country_is_passed_to_the_sdk(make_scraper):
    scraper, client = make_scraper({BRISTOL: search_page()}, country="GB")
    scraper.search("bristol")
    assert client.calls[0][1] == {"proxy_country": "gb"}


def test_filters_zoopla_did_not_apply_are_reported(make_scraper):
    url = f"{BRISTOL}?beds_min=3&price_max=400000&results_sort=newest_listings"
    page = search_page(sort="recommended", beds_min="3", price_max=None)
    scraper, _ = make_scraper({url: page})
    result = scraper.search(
        "bristol", filters=SearchFilters(beds_min=3, price_max=400000, sort="newest")
    )
    assert result.warnings == [
        "Zoopla sorted by 'recommended', not 'newest_listings'",
        "Zoopla did not apply price_max=400000",
    ]


def test_transient_errors_are_retried_with_backoff(make_scraper):
    scraper, client = make_scraper({BRISTOL: [BlockedError("x"), BlockedError("y"), search_page()]})
    assert scraper.search("bristol").listings
    assert len(client.calls) == 3
    assert scraper.sleeps == [2.0, 4.0]


def test_retries_give_up(make_scraper):
    scraper, client = make_scraper({BRISTOL: BlockedError("blocked")}, max_retries=1)
    with pytest.raises(BlockedError):
        scraper.search("bristol")
    assert len(client.calls) == 2


def test_other_sdk_errors_are_not_retried(make_scraper):
    scraper, client = make_scraper({BRISTOL: PermissionError("bad key")})
    with pytest.raises(PermissionError):
        scraper.search("bristol")
    assert len(client.calls) == 1


def test_a_page_without_data_is_fetched_once_more(make_scraper):
    broken = flight_page([json_row("1", {"x": 1})])
    scraper, client = make_scraper({BRISTOL: [broken, search_page()]})
    assert scraper.search("bristol").listings
    assert len(client.calls) == 2
    scraper, client = make_scraper({BRISTOL: broken})
    with pytest.raises(ParseError):
        scraper.search("bristol")
    assert len(client.calls) == 2


def test_unplaced_names_go_through_zoopla_resolver(make_scraper):
    leeds = f"{BASE}/for-sale/property/leeds/"
    resolver = f"{BASE}/api/search/resolver/?q=Leeds&section=for-sale"
    resolved = f"{BASE}/for-sale/property/west-yorkshire/leeds/?q=Leeds"
    scraper, client = make_scraper(
        {
            leeds: empty_location_page(),
            resolver: "/for-sale/property/west-yorkshire/leeds/?q=Leeds\n",
            resolved: search_page(page=1, page_max=2),
            f"{resolved}&pn=2": search_page([sale_card(2)], page=2, page_max=2),
        }
    )
    listings = scraper.search_listings("Leeds", max_pages=2)
    assert [c.listing_id for c in listings] == [74000001, 2]
    # The resolver is asked once; page 2 goes straight to the resolved path.
    assert [url for url, _ in client.calls] == [leeds, resolver, resolved, f"{resolved}&pn=2"]


def test_names_the_resolver_cannot_place(make_scraper):
    scraper, client = make_scraper(
        {
            f"{BASE}/for-sale/property/nowhere/": empty_location_page(),
            f"{BASE}/api/search/resolver/*": "<html><body><pre>{}</pre></body></html>",
        }
    )
    with pytest.raises(LocationNotFoundError):
        scraper.search("Nowhere")
    assert len(client.calls) == 2


def test_explicit_slugs_are_not_resolved(make_scraper):
    scraper, client = make_scraper({f"{BASE}/for-sale/property/a/b/": empty_location_page()})
    with pytest.raises(LocationNotFoundError):
        scraper.search("a/b")
    assert len(client.calls) == 1


def test_search_listings_merges_pages_and_skips_featured(make_scraper):
    featured = [sale_card(9)]
    scraper, client = make_scraper(
        {
            BRISTOL: search_page([sale_card(1), sale_card(2)], featured=featured, page_max=3),
            f"{BRISTOL}?pn=2": search_page([sale_card(2), sale_card(3)], page=2, featured=featured),
            f"{BRISTOL}?pn=3": search_page([sale_card(4)], page=3, featured=featured),
        }
    )
    listings = scraper.search_listings("bristol", max_pages=None)
    assert [c.listing_id for c in listings] == [1, 2, 3, 4]
    assert len(client.calls) == 3
    with_featured = scraper.search_listings("bristol", max_pages=1, include_featured=True)
    assert [c.listing_id for c in with_featured] == [9, 1, 2]


def test_search_listings_limits(make_scraper):
    scraper, client = make_scraper({BRISTOL: search_page([sale_card(1), sale_card(2)])})
    assert len(scraper.search_listings("bristol", max_results=1)) == 1
    assert len(client.calls) == 1


def test_rent_search(make_scraper):
    url = f"{BASE}/to-rent/property/manchester/?furnished_state=furnished"
    scraper, _ = make_scraper({url: search_page([rent_card()])})
    page = scraper.search("manchester", "rent", SearchFilters(furnished="furnished"))
    assert page.listings[0].rent_pcm == 8017


def test_listing(make_scraper):
    scraper, client = make_scraper({f"{BASE}/for-sale/details/74000001/": listing_page()})
    details = scraper.listing("https://www.zoopla.co.uk/for-sale/details/74000001/?x=1")
    assert details.postcode == "BS8 2AB"
    assert len(client.calls) == 1


def test_listing_not_found(make_scraper):
    scraper, _ = make_scraper({f"{BASE}/for-sale/details/1/": TargetNotFoundError("404")})
    with pytest.raises(ListingNotFoundError):
        scraper.listing(1)
    scraper, client = make_scraper({f"{BASE}/for-sale/details/2/": search_page([])})
    with pytest.raises(ListingNotFoundError):
        scraper.listing(2)
    assert len(client.calls) == 1


def test_sold_prices_and_paging(make_scraper):
    url = f"{BASE}/house-prices/bs9/?propertyTypeCode=F"
    scraper, client = make_scraper(
        {
            url: sold_page(has_next=True),
            f"{url}&pn=2": sold_page([sold_node(101, 400000), sold_node(103, 300000)]),
        }
    )
    from zoopla_scraper import SoldFilters

    records = scraper.sold_price_records("BS9", SoldFilters(property_type="flat"), max_pages=5)
    # 101 sold at the same date and price on both pages: kept once.
    assert [r.uprn for r in records] == [101, 102, 103]
    assert len(client.calls) == 2


def test_sold_prices_fall_back_to_the_resolver(make_scraper):
    scraper, client = make_scraper(
        {
            f"{BASE}/house-prices/leeds/": TargetNotFoundError("404"),
            f"{BASE}/api/search/resolver/?q=Leeds&section=house-prices": (
                "/house-prices/west-yorkshire/leeds/?q=Leeds"
            ),
            f"{BASE}/house-prices/west-yorkshire/leeds/": sold_page(has_next=True),
            f"{BASE}/house-prices/west-yorkshire/leeds/?pn=2": sold_page([sold_node(5, 1)]),
        }
    )
    pages = list(scraper.iter_sold_pages("Leeds", max_pages=2))
    assert pages[0].location == "west-yorkshire/leeds"
    assert len(pages) == 2
    assert len(client.calls) == 4


def test_unknown_sold_location(make_scraper):
    scraper, _ = make_scraper(
        {
            f"{BASE}/house-prices/nowhere/": TargetNotFoundError("404"),
            f"{BASE}/api/search/resolver/*": "",
        }
    )
    with pytest.raises(LocationNotFoundError):
        scraper.sold_prices("nowhere")


def test_property_history(make_scraper):
    scraper, _ = make_scraper({f"{BASE}/property/uprn/159652/": property_page()})
    assert scraper.property_history("159652").sales[0].price == 325000


def test_comparables_widen_from_postcode_to_outcode(make_scraper):
    query = "?numMonths=12&propertyTypeCode=S&beds_min=3&beds_max=3"
    query += "&sortOrder=last_sale_date&sortDirection=desc"
    outcode = [sold_node(i, price) for i, price in enumerate([300, 400, 500, 600, 700, 800])]
    scraper, client = make_scraper(
        {
            f"{BASE}/for-sale/details/74000001/": listing_page(),
            f"{BASE}/house-prices/bs8-2ab/{query}": sold_page([sold_node(1, 350000)]),
            f"{BASE}/house-prices/bs8/{query}": sold_page(outcode, total=6),
        }
    )
    comps = scraper.comparables(74000001)
    assert comps.scope == "outcode" and comps.location == "BS8"
    assert comps.count == 6
    assert comps.median_price == 550.0
    assert (comps.min_price, comps.max_price) == (300, 800)
    assert comps.asking_price == 375000
    assert comps.filters["property_type"] == "semi"
    assert len(client.calls) == 3


def test_comparables_postcode_only(make_scraper):
    scraper, client = make_scraper(
        {
            f"{BASE}/for-sale/details/74000001/": listing_page(),
            f"{BASE}/house-prices/bs8-2ab/*": TargetNotFoundError("404"),
        }
    )
    comps = scraper.comparables(74000001, scope="postcode", same_type=False, same_beds=False)
    assert comps.count == 0 and comps.median_price is None
    # A postcode without sales is not sent to the resolver.
    assert len(client.calls) == 2


def test_watch(make_scraper, tmp_path):
    state = tmp_path / "state.json"
    first = search_page([sale_card(1), sale_card(2)], page_max=1, total=2)
    second = search_page([sale_card(1, price="£360,000"), sale_card(3)], page_max=1, total=2)
    scraper, _ = make_scraper({BRISTOL: [first, second]})
    assert scraper.watch("bristol", str(state)) == []
    assert set(json.loads(state.read_text(encoding="utf-8"))) == {"1", "2"}
    changes = scraper.watch("bristol", str(state))
    assert sorted((c.kind, c.listing_id) for c in changes) == [
        ("new", 3),
        ("price_drop", 1),
        ("removed", 2),
    ]
    drop = next(c for c in changes if c.kind == "price_drop")
    assert (drop.old_price, drop.new_price, drop.change_percent) == (375000, 360000, -4.0)
    assert set(json.loads(state.read_text(encoding="utf-8"))) == {"1", "3"}


def test_watch_does_not_report_removals_from_a_partial_run(make_scraper, tmp_path):
    state = tmp_path / "state.json"
    first = search_page([sale_card(1), sale_card(2)], page_max=5, total=120)
    second = search_page([sale_card(1)], page_max=5, total=120)
    scraper, _ = make_scraper({BRISTOL: [first, second]})
    scraper.watch("bristol", str(state), max_pages=1)
    assert scraper.watch("bristol", str(state), max_pages=1) == []
    # Listings not seen this time stay in the snapshot.
    assert set(json.loads(state.read_text(encoding="utf-8"))) == {"1", "2"}
