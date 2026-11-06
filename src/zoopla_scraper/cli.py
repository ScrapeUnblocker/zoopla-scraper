"""Command-line interface for ``zoopla-scraper``.

Commands: ``search``, ``listing``, ``sold-prices``, ``property``, ``comps``, ``watch``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .errors import InputError, NotFoundError, ZooplaError
from .export import FORMATS, write
from .scraper import ZooplaScraper
from .urls import (
    ADDED,
    AVAILABLE,
    FURNISHED,
    MAX_PAGES,
    NEW_HOMES,
    ONLY_OR_EXCLUDE,
    PRICE_FREQ,
    PROPERTY_TYPES,
    RADII,
    SOLD_MONTHS,
    SOLD_SORTS,
    SOLD_TYPES,
    SORTS,
    SearchFilters,
    SoldFilters,
    search_query,
)

log = logging.getLogger("zoopla_scraper")

_EXTENSIONS = {".csv": "csv", ".jsonl": "jsonl", ".json": "json", ".txt": "table"}


def _split(values: Sequence[str] | None) -> list[str]:
    """Repeatable options that also accept comma-separated values."""
    return [part.strip() for value in values or () for part in value.split(",") if part.strip()]


def _add_common(parser: argparse.ArgumentParser, *, default_format: str = "table") -> None:
    parser.add_argument(
        "-f",
        "--format",
        choices=FORMATS,
        help=f"output format (default: from the --output extension, else {default_format})",
    )
    parser.set_defaults(default_format=default_format)
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")
    parser.add_argument(
        "--country", help="two-letter country to route requests through (default: automatic)"
    )
    parser.add_argument(
        "--retries", type=int, default=3, help="extra attempts per request on transient errors"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")


def _add_search(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "locations",
        nargs="+",
        help="place, outcode, postcode, Zoopla slug (london/islington) or a pasted search URL",
    )
    parser.add_argument(
        "--rent", action="store_const", const="rent", dest="channel", help="homes to rent"
    )
    parser.set_defaults(channel="sale")
    g = parser.add_argument_group("filters (sale and rent)")
    g.add_argument("--beds-min", type=int, metavar="N")
    g.add_argument("--beds-max", type=int, metavar="N")
    g.add_argument("--baths-min", type=int, metavar="N")
    g.add_argument("--baths-max", type=int, metavar="N")
    g.add_argument("--price-min", type=int, metavar="GBP", help="per month for rentals")
    g.add_argument("--price-max", type=int, metavar="GBP", help="per month for rentals")
    g.add_argument(
        "--type",
        action="append",
        metavar="TYPE",
        help=f"property type, repeatable or comma-separated: {', '.join(PROPERTY_TYPES)}",
    )
    g.add_argument(
        "--radius",
        type=float,
        choices=RADII,
        metavar="MILES",
        help=f"search radius in miles: {', '.join(f'{r:g}' for r in RADII)}",
    )
    g.add_argument("--keywords", help="words in the listing, e.g. 'garden parking'")
    g.add_argument("--added", choices=list(ADDED), help="added to Zoopla within")
    g.add_argument("--sort", choices=list(SORTS), help="sort order (default: recommended)")
    g.add_argument("--size-min", type=int, metavar="SQFT", help="minimum floor area in sq ft")
    g.add_argument("--size-max", type=int, metavar="SQFT", help="maximum floor area in sq ft")
    g.add_argument("--reduced-only", action="store_true", help="only reduced listings")
    g.add_argument("--retirement", choices=ONLY_OR_EXCLUDE, help="retirement homes")
    g = parser.add_argument_group("filters (sale only)")
    g.add_argument("--new-homes", choices=NEW_HOMES, help="new-build homes (default: include)")
    g.add_argument(
        "--include-sold", action="store_true", help="also list homes under offer or sold STC"
    )
    g.add_argument("--chain-free", action="store_true", help="only chain-free homes")
    g.add_argument("--auction", choices=ONLY_OR_EXCLUDE, help="auction listings")
    g.add_argument("--shared-ownership", choices=ONLY_OR_EXCLUDE, help="shared ownership")
    g = parser.add_argument_group("filters (rent only)")
    g.add_argument(
        "--price-per",
        choices=list(PRICE_FREQ),
        help="--price-min / --price-max are per month (default) or per week",
    )
    g.add_argument("--furnished", choices=FURNISHED)
    g.add_argument("--pets-allowed", action="store_true")
    g.add_argument("--bills-included", action="store_true")
    g.add_argument("--available", choices=list(AVAILABLE), help="available within")
    g.add_argument("--student", choices=ONLY_OR_EXCLUDE, help="student accommodation")
    g.add_argument("--house-share", choices=ONLY_OR_EXCLUDE, help="house shares and rooms")


def _add_pages(parser: argparse.ArgumentParser, what: str = "25 listings") -> None:
    parser.add_argument(
        "--pages", type=int, default=1, help=f"result pages per search ({what} each)"
    )
    parser.add_argument("--all", action="store_true", help="every page Zoopla shows")
    parser.add_argument("--limit", type=int, help="stop after this many records")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zoopla-scraper",
        description=(
            "Scrape Zoopla property listings, listing details, sold house prices, property "
            "history and sold comparables via the ScrapeUnblocker API."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="homes for sale or to rent (several places are merged)")
    _add_search(p)
    _add_pages(p)
    p.add_argument(
        "--featured", action="store_true", help="also include Zoopla's paid featured slots"
    )
    _add_common(p)

    p = sub.add_parser("listing", help="full listing details by id or URL")
    p.add_argument("listings", nargs="*", help="listing ids or zoopla.co.uk listing URLs")
    p.add_argument("--from-file", help="read listing ids or URLs from a file, one per line")
    _add_common(p, default_format="json")

    p = sub.add_parser("sold-prices", help="sold house prices for a place or postcode")
    p.add_argument("locations", nargs="+", help="town, area, outcode (bs9) or postcode (BS9 4LY)")
    p.add_argument("--type", choices=list(SOLD_TYPES), help="property type")
    p.add_argument(
        "--months",
        type=int,
        choices=SOLD_MONTHS,
        help="sold within this many months (default: all time)",
    )
    p.add_argument("--beds-min", type=int, metavar="N")
    p.add_argument("--beds-max", type=int, metavar="N")
    p.add_argument("--baths-min", type=int, metavar="N")
    p.add_argument("--baths-max", type=int, metavar="N")
    p.add_argument("--sort", choices=list(SOLD_SORTS), help="sort order (default: newest)")
    p.add_argument(
        "--averages",
        action="store_true",
        help="print only the 12-month average sold prices by property type",
    )
    _add_pages(p, "25 sales")
    _add_common(p)

    p = sub.add_parser("property", help="a property's sale history and past listings by UPRN")
    p.add_argument("properties", nargs="+", help="UPRNs or zoopla.co.uk/property/uprn/ URLs")
    _add_common(p, default_format="json")

    p = sub.add_parser("comps", help="recent sold prices near a listing (sold comparables)")
    p.add_argument("listing", help="listing id or URL")
    p.add_argument(
        "--months", type=int, default=12, choices=SOLD_MONTHS, help="sold within (default: 12)"
    )
    p.add_argument(
        "--scope",
        choices=("auto", "postcode", "outcode"),
        default="auto",
        help="auto = the postcode, widened to the outcode when it has fewer than 5 sales",
    )
    p.add_argument("--any-type", action="store_true", help="do not match the property type")
    p.add_argument("--any-beds", action="store_true", help="do not match the bedroom count")
    p.add_argument("--pages", type=int, default=1, help="sold-price pages to read (25 each)")
    _add_common(p, default_format="json")

    p = sub.add_parser("watch", help="new listings and price changes since the last run")
    _add_search(p)
    p.add_argument("--state", required=True, help="JSON file that keeps the last snapshot")
    _add_pages(p)
    _add_common(p)
    return parser


def _format(args: argparse.Namespace) -> str:
    if args.format:
        return args.format
    if args.output:
        ext = os.path.splitext(args.output)[1].lower()
        if ext in _EXTENSIONS:
            return _EXTENSIONS[ext]
    return args.default_format


def _refs(args: argparse.Namespace) -> list[str]:
    refs = list(args.listings)
    if args.from_file:
        with open(args.from_file, encoding="utf-8") as handle:
            refs += [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    if not refs:
        raise InputError("give listing ids or URLs, or --from-file")
    return refs


def search_filters(args: argparse.Namespace) -> SearchFilters:
    return SearchFilters(
        beds_min=args.beds_min,
        beds_max=args.beds_max,
        baths_min=args.baths_min,
        baths_max=args.baths_max,
        price_min=args.price_min,
        price_max=args.price_max,
        property_types=_split(args.type),
        radius=args.radius,
        keywords=args.keywords,
        added=args.added,
        sort=args.sort,
        size_min=args.size_min,
        size_max=args.size_max,
        reduced_only=args.reduced_only,
        retirement=args.retirement,
        new_homes=args.new_homes,
        include_sold=args.include_sold,
        chain_free=args.chain_free,
        auction=args.auction,
        shared_ownership=args.shared_ownership,
        price_frequency=args.price_per,
        furnished=args.furnished,
        pets_allowed=args.pets_allowed,
        bills_included=args.bills_included,
        available=args.available,
        student=args.student,
        house_share=args.house_share,
    )


def _pages(args: argparse.Namespace) -> int | None:
    if args.all:
        return None
    if args.pages < 1:
        raise InputError("--pages must be 1 or more")
    return args.pages


def _search(scraper: ZooplaScraper, args: argparse.Namespace) -> list[Any]:
    filters = search_filters(args)
    queries = [search_query(text, args.channel, filters) for text in args.locations]
    max_pages = _pages(args)
    seen: set[int] = set()
    found: list[Any] = []
    for query in queries:
        for result in scraper.iter_pages(query, max_pages=max_pages):
            if result.page == 1:
                pages = min(result.page_count or 0, MAX_PAGES)
                print(
                    f"{query.location}: {result.total_results or 0:,} results, {pages} pages"
                    + (f" ({result.description})" if result.description else ""),
                    file=sys.stderr,
                )
                for warning in result.warnings:
                    print(f"warning: {warning}", file=sys.stderr)
            cards = (result.featured if args.featured else []) + result.listings
            for card in cards:
                if card.listing_id in seen:
                    continue
                seen.add(card.listing_id)
                found.append(card)
                if args.limit and len(found) >= args.limit:
                    return found
    return found


def _sold(scraper: ZooplaScraper, args: argparse.Namespace) -> Any:
    filters = SoldFilters(
        property_type=args.type,
        months=args.months,
        beds_min=args.beds_min,
        beds_max=args.beds_max,
        baths_min=args.baths_min,
        baths_max=args.baths_max,
        sort=args.sort,
    )
    if args.averages:
        rows = []
        for place in args.locations:
            result = scraper.sold_prices(place, filters)
            rows.append({"location": place, "area": result.area, **result.average_prices})
        return rows
    records: list[Any] = []
    max_pages = _pages(args)
    seen: set[Any] = set()
    for place in args.locations:
        for result in scraper.iter_sold_pages(place, filters, max_pages=max_pages):
            if result.page == 1:
                print(
                    f"{place}: {result.total_results or 0:,} sales ({result.area})",
                    file=sys.stderr,
                )
            for record in result.records:
                key = (record.uprn or record.address, record.sold_on, record.price)
                if key in seen:
                    continue
                seen.add(key)
                records.append(record)
                if args.limit and len(records) >= args.limit:
                    return records
    return records


def _run(args: argparse.Namespace) -> int:
    fmt = _format(args)
    cmd = args.command
    scraper = ZooplaScraper(country=args.country, max_retries=args.retries)

    if cmd == "search":
        listings = _search(scraper, args)
        print(f"{len(listings)} listings ({scraper.requests} requests)", file=sys.stderr)
        write(listings, fmt, args.output)
        return 0

    if cmd == "listing":
        write(scraper.listings(_refs(args)), fmt, args.output)
        return 0

    if cmd == "sold-prices":
        result = _sold(scraper, args)
        if args.averages and fmt == "table":
            fmt = "csv"
        write(result, fmt, args.output)
        return 0

    if cmd == "property":
        write([scraper.property_history(ref) for ref in args.properties], fmt, args.output)
        return 0

    if cmd == "comps":
        comps = scraper.comparables(
            args.listing,
            months=args.months,
            scope=args.scope,
            same_type=not args.any_type,
            same_beds=not args.any_beds,
            max_pages=args.pages,
        )
        print(
            f"{comps.count} sales in {comps.scope} {comps.location} ({comps.filters})",
            file=sys.stderr,
        )
        write(comps, fmt, args.output)
        return 0

    if cmd == "watch":
        first_run = not os.path.exists(args.state)
        changes = scraper.watch(
            [search_query(text, args.channel, search_filters(args)) for text in args.locations],
            args.state,
            max_pages=_pages(args),
        )
        if first_run:
            print(f"first run: baseline saved to {args.state}", file=sys.stderr)
        else:
            print(f"{len(changes)} changes", file=sys.stderr)
        write(changes, fmt, args.output)
        return 0

    raise AssertionError(f"unhandled command {cmd}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return _run(args)
    except NotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except InputError as exc:
        parser.error(str(exc))
    except ZooplaError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except Exception as exc:  # SDK errors: bad key, no credit, network
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
