from urllib.parse import parse_qsl, urlsplit

import pytest

from zoopla_scraper import InputError, SearchFilters, SoldFilters, search_query
from zoopla_scraper import urls as u


@pytest.mark.parametrize(
    "text, slug",
    [
        ("Bristol", "bristol"),
        ("Milton Keynes", "milton-keynes"),
        ("BS9 4LY", "bs9-4ly"),
        ("  bs9 ", "bs9"),
        ("west-yorkshire/leeds", "west-yorkshire/leeds"),
        ("Brighton & Hove", "brighton-and-hove"),
    ],
)
def test_location_slug(text, slug):
    assert u.location_slug(text) == slug


def test_location_slug_needs_text():
    with pytest.raises(InputError):
        u.location_slug("  ")


def _params(url):
    return parse_qsl(urlsplit(url).query)


def test_sale_filters_to_params():
    filters = SearchFilters(
        beds_min=3,
        price_max=450000,
        property_types=["semi", "terraced"],
        radius=0.5,
        keywords=" garden ",
        added="7d",
        sort="newest",
        size_min=900,
        reduced_only=True,
        new_homes="exclude",
        include_sold=True,
        chain_free=True,
        auction="exclude",
        shared_ownership="exclude",
        retirement="exclude",
    )
    assert filters.to_params("sale") == [
        ("beds_min", "3"),
        ("price_max", "450000"),
        ("property_sub_type", "semi_detached"),
        ("property_sub_type", "terraced"),
        ("radius", "0.5"),
        ("keywords", "garden"),
        ("added", "7_days"),
        ("results_sort", "newest_listings"),
        ("floor_area_min", "900"),
        ("floor_area_units", "sq_feet"),
        ("reduced_price_only", "true"),
        ("is_retirement_home", "false"),
        ("new_homes", "exclude"),
        ("include_sold", "true"),
        ("chain_free", "true"),
        ("is_auction", "false"),
        ("is_shared_ownership", "false"),
    ]


def test_rent_filters_to_params():
    filters = SearchFilters(
        price_max=500,
        price_frequency="week",
        furnished="part_furnished",
        pets_allowed=True,
        bills_included=True,
        available="3m",
        student="exclude",
        house_share="only",
    )
    assert filters.to_params("rent") == [
        ("price_max", "500"),
        ("price_frequency", "per_week"),
        ("furnished_state", "part_furnished"),
        ("pets_allowed", "true"),
        ("bills_included", "true"),
        ("available_from", "3months"),
        ("is_student_accommodation", "false"),
        ("is_shared_accommodation", "true"),
    ]


def test_zoopla_values_are_accepted_as_they_are():
    filters = SearchFilters(sort="most_reduced", added="24_hours", property_types=["flats"])
    assert ("results_sort", "most_reduced") in filters.to_params()
    assert ("added", "24_hours") in filters.to_params()


@pytest.mark.parametrize(
    "filters, channel",
    [
        (SearchFilters(furnished="furnished"), "sale"),
        (SearchFilters(pets_allowed=True), "sale"),
        (SearchFilters(include_sold=True), "rent"),
        (SearchFilters(chain_free=True), "rent"),
        (SearchFilters(beds_min=4, beds_max=2), "sale"),
        (SearchFilters(radius=2), "sale"),
        (SearchFilters(sort="cheapest"), "sale"),
        (SearchFilters(property_types=["castle"]), "sale"),
        (SearchFilters(beds_min="three"), "sale"),
        (SearchFilters(added="2d"), "sale"),
    ],
)
def test_bad_filters(filters, channel):
    with pytest.raises(InputError):
        filters.to_params(channel)


def test_describe_lists_only_set_filters():
    assert SearchFilters(beds_min=2, chain_free=True).describe() == {
        "beds_min": 2,
        "chain_free": True,
    }


def test_search_query_url():
    query = search_query("Bristol", "sale", SearchFilters(beds_min=2))
    assert query.url() == "https://www.zoopla.co.uk/for-sale/property/bristol/?beds_min=2"
    assert query.url(3).endswith("?beds_min=2&pn=3")
    assert query.text == "Bristol"
    rent = search_query("london", "to-rent")
    assert rent.channel == "rent"
    assert rent.url() == "https://www.zoopla.co.uk/to-rent/property/london/"


def test_slug_with_a_slash_skips_the_resolver():
    assert search_query("west-yorkshire/leeds").text is None


def test_pasted_search_url_keeps_its_filters():
    url = (
        "https://www.zoopla.co.uk/to-rent/flats/london/islington/"
        "?beds_min=1&price_max=2000&search_source=to-rent&pn=4"
    )
    query = search_query(url, "sale", SearchFilters(price_max=2500))
    assert query.channel == "rent"
    assert query.kind == "flats"
    assert query.location == "london/islington"
    assert query.text is None
    built = query.url(2)
    assert urlsplit(built).path == "/to-rent/flats/london/islington/"
    # Filters given here win over the URL's own; pn and search_source are dropped.
    assert _params(built) == [("beds_min", "1"), ("price_max", "2500"), ("pn", "2")]


def test_pasted_new_homes_url():
    query = search_query("https://www.zoopla.co.uk/new-homes/property/bristol/")
    assert query.channel == "sale"
    assert ("new_homes", "only") in query.extra


def test_not_a_search_url():
    with pytest.raises(InputError):
        search_query("https://www.zoopla.co.uk/for-sale/details/123/")


def test_apply_search_path():
    query = search_query("Leeds", "sale", SearchFilters(beds_min=2))
    u.apply_search_path(query, "/for-sale/property/west-yorkshire/leeds/?q=Leeds")
    assert query.location == "west-yorkshire/leeds"
    assert query.text is None
    assert query.url() == (
        "https://www.zoopla.co.uk/for-sale/property/west-yorkshire/leeds/?q=Leeds&beds_min=2"
    )


@pytest.mark.parametrize(
    "body, path",
    [
        (
            "/for-sale/property/west-yorkshire/leeds/?q=Leeds\n",
            "/for-sale/property/west-yorkshire/leeds/?q=Leeds",
        ),
        (
            "<html><body><pre>/to-rent/property/leeds/?beds_min=2&amp;q=Leeds</pre></body></html>",
            "/to-rent/property/leeds/?beds_min=2&q=Leeds",
        ),
        ("/house-prices/bs9/?q=BS9", "/house-prices/bs9/?q=BS9"),
        ("<html><body><pre>{}</pre></body></html>", None),
        ("", None),
    ],
)
def test_resolved_path(body, path):
    assert u.resolved_path(body) == path


def test_resolver_url():
    assert u.resolver_url(" Leeds ", "house-prices") == (
        "https://www.zoopla.co.uk/api/search/resolver/?q=Leeds&section=house-prices"
    )


def test_listing_and_property_refs():
    assert u.listing_ref("74693032") == (74693032, None)
    assert u.listing_ref("https://www.zoopla.co.uk/to-rent/details/74699742/?search=x") == (
        74699742,
        "to-rent",
    )
    assert u.listing_url(5) == "https://www.zoopla.co.uk/for-sale/details/5/"
    assert u.uprn_ref("https://www.zoopla.co.uk/property/uprn/159652/") == 159652
    assert u.property_url(159652) == "https://www.zoopla.co.uk/property/uprn/159652/"
    for bad in ("abc", "https://example.com/for-sale/details/1/"):
        with pytest.raises(InputError):
            u.listing_ref(bad)
    with pytest.raises(InputError):
        u.uprn_ref("https://www.zoopla.co.uk/for-sale/details/1/")


def test_sold_filters_and_url():
    filters = SoldFilters(property_type="flat", months=12, beds_min=2, sort="price-high")
    assert u.sold_url("BS9 4LY", filters, page=2) == (
        "https://www.zoopla.co.uk/house-prices/bs9-4ly/?numMonths=12&propertyTypeCode=F"
        "&beds_min=2&sortOrder=last_sale_price&sortDirection=desc&pn=2"
    )
    assert SoldFilters(months="all", property_type="any").to_params() == []
    assert u.sold_url("bristol") == "https://www.zoopla.co.uk/house-prices/bristol/"


@pytest.mark.parametrize("filters", [SoldFilters(months=7), SoldFilters(property_type="castle")])
def test_bad_sold_filters(filters):
    with pytest.raises(InputError):
        filters.to_params()


def test_sold_location_and_resolver_need():
    assert u.sold_location("https://www.zoopla.co.uk/house-prices/west-yorkshire/leeds/") == (
        "west-yorkshire/leeds"
    )
    assert u.sold_location("/house-prices/bs9/?q=BS9") == "bs9"
    assert u.needs_resolver("Leeds") is True
    assert u.needs_resolver("west-yorkshire/leeds") is False
    assert u.needs_resolver("https://www.zoopla.co.uk/house-prices/bs9/") is False
