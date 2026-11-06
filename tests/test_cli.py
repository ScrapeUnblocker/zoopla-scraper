import json

import pytest
from conftest import FakeClient, listing_page, sale_card, search_page, sold_page

from zoopla_scraper import cli


def _parse(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_search_arguments_become_filters():
    args = _parse(
        "search",
        "bristol",
        "bath",
        "--beds-min",
        "3",
        "--price-max",
        "450000",
        "--type",
        "semi,terraced",
        "--type",
        "detached",
        "--radius",
        "0.5",
        "--sort",
        "most-reduced",
        "--chain-free",
        "--new-homes",
        "exclude",
        "--pages",
        "2",
    )
    assert args.locations == ["bristol", "bath"]
    assert args.channel == "sale"
    filters = cli.search_filters(args)
    assert filters.property_types == ["semi", "terraced", "detached"]
    assert filters.radius == 0.5
    assert filters.chain_free is True
    assert ("results_sort", "most_reduced") in filters.to_params("sale")


def test_rent_arguments():
    args = _parse("search", "london", "--rent", "--furnished", "furnished", "--price-per", "week")
    assert args.channel == "rent"
    params = cli.search_filters(args).to_params("rent")
    assert ("furnished_state", "furnished") in params
    assert ("price_frequency", "per_week") in params


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "bristol", "--radius", "2"],
        ["search", "bristol", "--sort", "cheapest"],
        ["sold-prices", "bs9", "--months", "7"],
        ["comps", "1", "--scope", "county"],
        ["watch", "bristol"],
    ],
)
def test_invalid_arguments_exit(argv):
    with pytest.raises(SystemExit):
        _parse(*argv)


def test_format_follows_the_output_extension():
    assert cli._format(_parse("search", "x", "-o", "a.csv")) == "csv"
    assert cli._format(_parse("search", "x", "-o", "a.jsonl")) == "jsonl"
    assert cli._format(_parse("search", "x")) == "table"
    assert cli._format(_parse("listing", "1")) == "json"
    assert cli._format(_parse("search", "x", "-f", "json", "-o", "a.csv")) == "json"


@pytest.fixture
def fake_api(monkeypatch):
    """Point the CLI's scraper at a fake client."""
    from zoopla_scraper import scraper as scraper_module

    routes = {}
    real = scraper_module.ZooplaScraper

    def build(*args, **kwargs):
        return real(client=FakeClient(routes), sleep=lambda s: None, **kwargs)

    monkeypatch.setattr(cli, "ZooplaScraper", build)
    return routes


def test_search_command_writes_csv(fake_api, tmp_path, capsys):
    base = "https://www.zoopla.co.uk/for-sale/property/bristol/"
    fake_api[f"{base}?beds_min=3"] = search_page([sale_card(1), sale_card(2)], page_max=2)
    fake_api[f"{base}?beds_min=3&pn=2"] = search_page(
        [sale_card(2), sale_card(3)], page=2, page_max=2
    )
    out = tmp_path / "homes.csv"
    code = cli.main(["search", "bristol", "--beds-min", "3", "--all", "-o", str(out)])
    assert code == 0
    text = out.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("listing_id,url,channel")
    assert len(text.splitlines()) == 4
    err = capsys.readouterr().err
    assert "70 results, 2 pages (3+ bedroom houses for sale)" in err
    assert "3 listings" in err


def test_search_limit(fake_api, capsys):
    fake_api["https://www.zoopla.co.uk/for-sale/property/bath/"] = search_page(
        [sale_card(1), sale_card(2)]
    )
    assert cli.main(["search", "bath", "--limit", "1", "-f", "jsonl"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and json.loads(out[0])["listing_id"] == 1


def test_listing_command(fake_api, capsys):
    fake_api["https://www.zoopla.co.uk/for-sale/details/74000001/"] = listing_page()
    assert cli.main(["listing", "74000001"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["postcode"] == "BS8 2AB"


def test_sold_prices_averages(fake_api, capsys):
    fake_api["https://www.zoopla.co.uk/house-prices/bristol/"] = sold_page()
    assert cli.main(["sold-prices", "bristol", "--averages"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "location,area,all,detached,flat,terraced,semi"
    assert out[1].startswith("bristol,Bristol,387951,546953,,")


def test_errors_exit_with_one(fake_api, capsys):
    fake_api["https://www.zoopla.co.uk/for-sale/details/1/"] = search_page([])
    assert cli.main(["listing", "1"]) == 1
    assert "no longer on Zoopla" in capsys.readouterr().err


def test_listing_needs_refs(fake_api):
    with pytest.raises(SystemExit):
        cli.main(["listing"])
