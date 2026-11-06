"""Search snapshots and change detection for :meth:`ZooplaScraper.watch`."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import Any

from .models import Change, Listing

_KEEP = ("price", "price_frequency", "price_label", "under_offer", "status", "address", "url")


def snapshot(listings: Iterable[Listing]) -> dict[str, dict[str, Any]]:
    """The state saved between runs: one entry per listing id."""
    return {str(item.listing_id): {k: getattr(item, k) for k in _KEEP} for item in listings}


def _change(
    kind: str, listing_id: str, now: dict[str, Any], before: dict[str, Any] | None
) -> Change:
    old = (before or {}).get("price") if kind != "new" else None
    new = now.get("price") if kind != "removed" else None
    percent = None
    if old and new is not None and kind in ("price_drop", "price_increase"):
        percent = round((new - old) / old * 100, 1)
    return Change(
        kind=kind,
        listing_id=int(listing_id),
        url=now.get("url"),
        address=now.get("address"),
        old_price=old,
        new_price=new,
        price_frequency=now.get("price_frequency"),
        change_percent=percent,
        status=now.get("status"),
    )


def _kind(before: dict[str, Any], now: dict[str, Any]) -> str | None:
    """The most telling difference between two snapshots of one listing, if any."""
    old, new = before.get("price"), now.get("price")
    same_unit = before.get("price_frequency") == now.get("price_frequency")
    if old is not None and new is not None and old != new and same_unit:
        return "price_drop" if new < old else "price_increase"
    if now.get("under_offer") and not before.get("under_offer"):
        return "under_offer"
    if before.get("under_offer") and now.get("under_offer") is False:
        return "back_on_market"
    return None


def diff(
    before: dict[str, dict[str, Any]],
    now: dict[str, dict[str, Any]],
    *,
    complete: bool = True,
) -> list[Change]:
    """Changes from the ``before`` snapshot to ``now``.

    Listings missing from ``now`` are reported as ``removed`` only when ``complete``
    (every result page was read); otherwise they may simply be on a page not fetched.
    """
    changes = []
    for key, current in now.items():
        previous = before.get(key)
        if previous is None:
            changes.append(_change("new", key, current, None))
            continue
        kind = _kind(previous, current)
        if kind:
            changes.append(_change(kind, key, current, previous))
    if complete:
        for key, previous in before.items():
            if key not in now:
                changes.append(_change("removed", key, previous, previous))
    return changes


def load_state(path: str) -> dict[str, dict[str, Any]] | None:
    """The saved snapshot, or ``None`` on the first run."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else None


def save_state(path: str, state: dict[str, dict[str, Any]]) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
