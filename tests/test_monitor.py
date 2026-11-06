from zoopla_scraper.models import Listing
from zoopla_scraper.monitor import diff, load_state, save_state, snapshot


def _listing(listing_id, price, **extra):
    return Listing(
        listing_id=listing_id, url=f"https://x/{listing_id}", channel="sale", price=price, **extra
    )


def test_snapshot_keeps_what_watch_compares():
    state = snapshot([_listing(1, 300000, address="Elm Road", status="Just added")])
    assert state == {
        "1": {
            "price": 300000,
            "price_frequency": None,
            "price_label": None,
            "under_offer": None,
            "status": "Just added",
            "address": "Elm Road",
            "url": "https://x/1",
        }
    }


def test_diff_kinds():
    before = snapshot(
        [
            _listing(1, 300000),
            _listing(2, 300000),
            _listing(3, 300000, under_offer=False),
            _listing(4, 300000, under_offer=True),
            _listing(5, 300000),
        ]
    )
    now = snapshot(
        [
            _listing(1, 290000),
            _listing(2, 310000),
            _listing(3, 300000, under_offer=True),
            _listing(4, 300000, under_offer=False),
            _listing(6, 250000),
        ]
    )
    changes = {c.listing_id: c for c in diff(before, now)}
    assert {k: c.kind for k, c in changes.items()} == {
        1: "price_drop",
        2: "price_increase",
        3: "under_offer",
        4: "back_on_market",
        5: "removed",
        6: "new",
    }
    assert changes[1].change_percent == -3.3
    assert (changes[6].old_price, changes[6].new_price) == (None, 250000)
    assert (changes[5].old_price, changes[5].new_price) == (300000, None)


def test_removed_only_when_complete():
    before = snapshot([_listing(1, 1), _listing(2, 1)])
    now = snapshot([_listing(1, 1)])
    assert diff(before, now, complete=False) == []
    assert [c.kind for c in diff(before, now, complete=True)] == ["removed"]


def test_rent_in_another_unit_is_not_a_price_change():
    before = snapshot([_listing(1, 400, price_frequency="pw")])
    now = snapshot([_listing(1, 1733, price_frequency="pcm")])
    assert diff(before, now) == []


def test_state_round_trip(tmp_path):
    path = tmp_path / "nested" / "state.json"
    assert load_state(str(path)) is None
    save_state(str(path), {"1": {"price": 5}})
    assert load_state(str(path)) == {"1": {"price": 5}}
