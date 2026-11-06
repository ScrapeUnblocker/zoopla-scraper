import csv
import io
import json

import pytest
from conftest import listing_page, search_page

from zoopla_scraper import parsing
from zoopla_scraper.export import render, write
from zoopla_scraper.models import Comparables, SoldPrice


@pytest.fixture
def listings():
    return parsing.parse_search(search_page(), "https://x/", "sale").listings


def test_json_and_jsonl(listings):
    data = json.loads(render(listings, "json"))
    assert data[0]["agent"]["name"] == "Example Homes - Bristol"
    lines = render(listings, "jsonl").splitlines()
    assert json.loads(lines[0])["listing_id"] == 74000001


def test_csv_flattens_agent_and_lists(listings):
    rows = list(csv.DictReader(io.StringIO(render(listings, "csv"))))
    assert rows[0]["agent_name"] == "Example Homes - Bristol"
    assert rows[0]["tags"] == "Chain free; Freehold"
    assert "agent" not in rows[0]
    assert rows[0]["images"].startswith("https://lid.zoocdn.com/")


def test_csv_file_has_a_bom_for_excel(listings, tmp_path):
    path = tmp_path / "out.csv"
    write(listings, "csv", str(path))
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_table(listings):
    table = render(listings, "table")
    assert table.splitlines()[0].split()[:3] == ["id", "price", "rooms"]
    assert "£375,000" in table


def test_listing_details_csv_drops_html():
    details = parsing.parse_listing(listing_page(), "https://x/")
    row = next(csv.DictReader(io.StringIO(render(details, "csv"))))
    assert "description_html" not in row
    assert row["price_changes"] == "2026-05-13 (drop); 2026-10-21 (drop)"


def test_comparables_csv_is_one_row_per_sale():
    comps = Comparables(
        listing_id=1,
        listing_url="u",
        asking_price=300000,
        address="a",
        scope="outcode",
        location="BS8",
        records=[SoldPrice(uprn=5, address="x", price=1), SoldPrice(uprn=6, address="y", price=2)],
    )
    rows = list(csv.DictReader(io.StringIO(render(comps, "csv"))))
    assert [r["uprn"] for r in rows] == ["5", "6"]
    assert rows[0]["comparable_for"] == "1"
    assert "vs median" in render(comps, "table")


def test_unknown_format(listings):
    with pytest.raises(ValueError):
        render(listings, "xml")
