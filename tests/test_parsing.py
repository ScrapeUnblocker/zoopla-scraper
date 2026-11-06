import copy

import pytest
from conftest import (
    LISTING_DATA,
    empty_location_page,
    flight_page,
    home_page,
    json_row,
    listing_page,
    property_page,
    rent_card,
    rent_listing_data,
    sale_card,
    search_page,
    search_rows,
    sold_node,
    sold_page,
    text_row,
)

from zoopla_scraper import ListingNotFoundError, LocationNotFoundError
from zoopla_scraper import parsing as p

# -- helpers ---------------------------------------------------------------------------


def test_flight_joins_and_unescapes_chunks():
    page = flight_page([json_row("1", {"a": 'say "hi"', "b": "£5"})])
    assert p.flight(page) == '1:{"a":"say \\"hi\\"","b":"£5"}\n'


def test_text_rows_use_byte_lengths():
    payload = text_row("a1", "£5 – the avenue’s") + json_row("2", [1])
    assert p.text_rows(payload) == {"a1": "£5 – the avenue’s"}


def test_first_value_skips_values_of_the_wrong_type():
    payload = '{"pagination":null}{"pagination":{"pageNumber":2}}'
    assert p.first_value(payload, "pagination", dict) == {"pageNumber": 2}
    assert p.first_value(payload, "missing") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("£1,750 pcm", 1750.0),
        ("£403.85 pw", 403.85),
        ("Offers over £350,000", 350000.0),
        ("POA", None),
        (None, None),
        (5, 5.0),
    ],
)
def test_money(text, expected):
    assert p.money(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5th Nov 2026", "2026-11-05"),
        ("Last reduced: 27th Oct 2026", "2026-10-27"),
        ("21st Jul 2026", "2026-07-21"),
        ("Available from 13 January 2027", "2027-01-13"),
        ("immediately", "immediately"),
        (None, None),
    ],
)
def test_uk_date(text, expected):
    assert p.uk_date(text) == expected


def test_html_to_text():
    html = "<b>Big</b> house<br><br><ul><li>Garden</li><li>Garage &amp; drive</li></ul>"
    assert p.html_to_text(html) == "Big house\n\n- Garden\n- Garage & drive"
    assert p.html_to_text("") is None


def test_outcode():
    assert p.outcode("Elm Road, Clifton, Bristol BS8") == "BS8"
    assert p.outcode("Flatts Close, Stoke Gifford BS34") == "BS34"
    assert p.outcode("Leftbank, Manchester M3") == "M3"
    assert p.outcode("Somewhere without a code") is None


# -- search ----------------------------------------------------------------------------


def test_parse_search_page():
    page = search_page(
        [sale_card(1), sale_card(2, priceDrop=None)], featured=[sale_card(9)], total=70
    )
    result = p.parse_search(page, "https://x/", "sale")
    assert (result.page, result.page_count, result.total_results) == (1, 3, 70)
    assert [c.listing_id for c in result.listings] == [1, 2]
    assert [c.position for c in result.listings] == [1, 2]
    assert [c.listing_id for c in result.featured] == [9]
    assert result.featured[0].featured is True
    assert result.has_next is True
    assert result.description == "3+ bedroom houses for sale"
    assert result.applied["sort"] == "newest_listings"
    assert result.applied["beds_min"] == 3


def test_sale_card_fields():
    card = p.parse_search(search_page(), "https://x/", "sale").listings[0]
    assert card.url == "https://www.zoopla.co.uk/for-sale/details/74000001/"
    assert (card.bedrooms, card.bathrooms, card.receptions, card.size_sqft) == (3, 2, 1, 1076)
    assert card.price == 375000
    assert card.price_frequency is None
    assert card.price_qualifier == "Guide price"
    assert card.outcode == "BS8"
    assert card.listed_on == "2026-11-05"
    assert card.tags == ["Chain free", "Freehold"]
    assert card.highlights == ["Good Schools"]
    assert card.summary == "A bright three bedroom home & garden."
    assert card.agent.name == "Example Homes - Bristol"
    assert card.agent.url.endswith("/find-agents/branch/example-homes-bristol-1001/")
    # The cover photo is not in the gallery list; it comes first, at full size.
    assert card.images == [
        "https://lid.zoocdn.com/u/1024/768/a1.jpg",
        "https://lid.zoocdn.com/u/1024/768/b2.jpg",
        "https://lid.zoocdn.com/u/1024/768/c3.jpg",
    ]


def test_rent_card_takes_the_price_from_the_labels():
    card = p.parse_search(search_page([rent_card()]), "https://x/", "rent").listings[0]
    # priceUnformatted (1850) is weekly here; the headline label is per month.
    assert card.price == 8017
    assert card.price_frequency == "pcm"
    assert (card.rent_pcm, card.rent_pw) == (8017, 1850)
    assert card.available_from == "2026-11-14"
    assert card.channel == "rent"


def test_price_drop_fields():
    drop = {
        "firstPriceDate": "2nd Sep 2026",
        "lastPriceChangeDate": "Last reduced: 27th Oct 2026",
        "percentageChangeLabel": "2.5",
        "priceChangeLabel": "£10,000",
    }
    card = p.parse_listing_card(sale_card(priceDrop=drop), "sale")
    assert card.price_drop_amount == 10000
    assert card.price_drop_percent == 2.5
    assert card.price_reduced_on == "2026-10-27"
    assert card.first_price_on == "2026-09-02"


def test_new_home_card():
    card = p.parse_listing_card(
        sale_card(listingUris={"detail": "/new-homes/details/5/"}, derivedBuyerIncentives=["x"]),
        "sale",
    )
    assert card.new_home is True
    assert card.buyer_incentives == ["x"]


def test_unknown_location_pages():
    with pytest.raises(LocationNotFoundError):
        p.parse_search(empty_location_page(), "https://x/", "sale")
    with pytest.raises(LocationNotFoundError):
        p.parse_search(home_page(), "https://x/", "sale")


def test_missing_results_is_a_value_error():
    page = flight_page([json_row("1", {"something": "else"})])
    with pytest.raises(ValueError):
        p.parse_search(page, "https://x/", "sale")


def test_zero_results_is_not_an_error():
    rows = search_rows([], page_max=1, total=0)
    result = p.parse_search(flight_page(rows), "https://x/", "sale")
    assert result.listings == [] and result.total_results == 0 and not result.has_next


# -- listing details -------------------------------------------------------------------


def test_parse_listing():
    details = p.parse_listing(listing_page(), "https://x/")
    assert details.listing_id == 74000001
    assert details.url == "https://www.zoopla.co.uk/for-sale/details/74000001/"
    assert details.channel == "sale"
    assert details.postcode == "BS8 2AB"
    assert details.price == 375000
    assert details.price_qualifier == "Offers over"
    assert details.floor_area_sqft == 1076
    assert (details.bedrooms, details.bathrooms, details.receptions) == (3, 2, 1)
    assert details.tenure == "Leasehold (125 years)"
    assert details.lease_years_remaining == 125
    assert details.council_tax_band == "D"
    assert details.service_charge == "£1,200 per year"
    assert details.key_facts == {
        "tenure": "Leasehold (125 years)",
        "council_tax_band": "D",
        "service_charge": "£1,200 per year",
    }
    assert details.utilities == {"water": "Mains", "parking": "Driveway"}
    assert details.epc_rating == "C"
    assert details.chain_free is True
    assert details.features == ["Garden & garage", "No onward chain"]
    assert details.description == "Bright family home.\n\nClose to the Downs & the avenue’s shops."
    assert details.description_html.startswith("<b>Bright</b>")
    assert [c.date for c in details.price_changes] == ["2026-05-13", "2026-10-21"]
    assert details.nearest_stations == [
        {"name": "Clifton Down", "miles": 0.4},
        {"name": "Redland", "miles": 0.9},
    ]
    assert details.agent.phone == "0117 000 0000"
    assert details.photos[0].caption == "Kitchen"
    # A caption that is just the uploaded file name is dropped.
    assert details.photos[1].caption is None
    assert details.floor_plans == ["https://lid.zoocdn.com/u/1024/768/fp1.jpg"]
    assert details.epc_images == ["https://lid.zoocdn.com/u/1024/768/epc1.png"]
    assert details.virtual_tours == ["https://example.com/tour"]
    assert details.videos == ["https://example.com/video"]
    assert details.brochures == ["https://example.com/b.pdf"]


def test_parse_rental_listing():
    details = p.parse_listing(listing_page(rent_listing_data()), "https://x/")
    assert details.channel == "rent"
    assert details.url == "https://www.zoopla.co.uk/to-rent/details/74000001/"
    assert (details.price, details.price_frequency) == (2450, "pcm")
    assert (details.rent_pcm, details.rent_pw) == (2450, 565)
    assert details.deposit == "£2,826"


def test_removed_listing_raises_not_found():
    # Zoopla answers a removed listing with a search page for its street.
    with pytest.raises(ListingNotFoundError):
        p.parse_listing(search_page([]), "https://x/")


def test_listing_without_data_is_a_value_error():
    with pytest.raises(ValueError):
        p.parse_listing(flight_page([json_row("1", {"x": 1})]), "https://x/")


def test_listing_without_description_row():
    data = copy.deepcopy(LISTING_DATA)
    data["detailedDescription"] = "$zz"
    details = p.parse_listing(listing_page(data), "https://x/")
    assert details.description is None and details.description_html is None


# -- sold prices and property ----------------------------------------------------------


def test_parse_sold():
    result = p.parse_sold(sold_page(has_next=True, total=713), "https://x/", "bristol", 2)
    assert (result.page, result.total_results, result.has_next) == (2, 713, True)
    assert result.area == "Bristol" and result.area_type == "town"
    assert result.average_prices["all"] == 387951
    assert result.average_prices["flat"] is None
    first = result.records[0]
    assert (first.uprn, first.price, first.sold_on) == (101, 400000, "2026-08-20")
    assert first.property_url == "https://www.zoopla.co.uk/property/uprn/101/"
    assert first.floor_area_sqm == 96
    assert (first.page, first.position) == (2, 1)


def test_parse_sold_needs_results():
    from conftest import next_page

    with pytest.raises(ValueError):
        p.parse_sold(next_page({"other": 1}), "https://x/", "bristol")
    with pytest.raises(ValueError):
        p.parse_sold("<html>no data</html>", "https://x/", "bristol")


def test_sold_record_with_missing_attributes():
    node = sold_node(7, 135000, bedrooms=None, tenure=None, floorAreaSqM=None)
    record = p.parse_sold(sold_page([node], total=1), "https://x/", "x").records[0]
    assert record.bedrooms is None and record.tenure is None and record.floor_area_sqm is None


def test_parse_property():
    history = p.parse_property(property_page(), "https://x/")
    assert history.uprn == 159652
    assert history.url == "https://www.zoopla.co.uk/property/uprn/159652/"
    assert history.postcode == "BS13 8LE"
    assert history.epc_rating == "D"
    assert history.listed_now is False
    assert [(s.date, s.price) for s in history.sales] == [
        ("2026-08-28", 325000),
        ("2000-08-01", 125500),
    ]
    assert history.sales[0].change_percent == 159.0
    assert history.sales[0].change_amount == 199500
    assert history.sales_source == "landRegistry"
    previous = history.previous_listings[0]
    assert previous.price == 325000
    assert previous.url.startswith("https://www.zoopla.co.uk/property-history/")
    assert previous.images == ["https://lid.zoocdn.com/1024/768/i.jpg"]
