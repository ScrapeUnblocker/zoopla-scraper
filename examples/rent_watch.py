"""New rentals and rent changes in a city since the last run (run it daily, e.g. from cron).

The first run saves a baseline; later runs print what is new, cheaper, dearer, under offer or
gone. The snapshot lives in rent-watch.json next to where you run it.

Run: python examples/rent_watch.py  (needs SCRAPEUNBLOCKER_KEY)
"""

from zoopla_scraper import SearchFilters, ZooplaScraper

zoopla = ZooplaScraper()
filters = SearchFilters(beds_min=2, price_max=1_800, sort="newest")
changes = zoopla.watch("Leeds", "rent-watch.json", channel="rent", filters=filters, max_pages=2)

if not changes:
    print("no changes (or first run: baseline saved to rent-watch.json)")
for change in changes:
    old = f"£{change.old_price:,.0f}" if change.old_price else "-"
    new = f"£{change.new_price:,.0f}" if change.new_price else "-"
    print(f"{change.kind:<15} {old:>7} -> {new:<7} {change.address}  {change.url}")
