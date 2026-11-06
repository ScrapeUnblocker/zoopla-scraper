"""Is a listing priced in line with recent sales nearby?

Opens a listing, then reads HM Land Registry sold prices Zoopla shows for the same
postcode (widened to the postcode district when there are too few sales), filtered to
the same property type and bedroom count, and compares the asking price with the median.

Run: python examples/sold_comps.py [LISTING_ID]  (needs SCRAPEUNBLOCKER_KEY)
"""

import sys

from zoopla_scraper import SearchFilters, ZooplaScraper

zoopla = ZooplaScraper()
if len(sys.argv) > 1:
    listing_id = sys.argv[1]
else:
    newest = zoopla.search("Manchester", filters=SearchFilters(beds_min=2, sort="newest"))
    listing_id = newest.listings[0].listing_id

comps = zoopla.comparables(listing_id, months=12)
print(f"{comps.address}  asking £{comps.asking_price:,.0f}  ({comps.listing_url})")
print(f"{comps.count} comparable sales in {comps.scope} {comps.location}: {comps.filters}")
if comps.count:
    print(f"median £{comps.median_price:,.0f}, range £{comps.min_price:,} - £{comps.max_price:,}")
    print(f"asking price vs median: {comps.asking_vs_median_percent:+.1f}%")
    for sale in comps.records[:5]:
        print(f"  {sale.sold_on}  £{sale.price:>9,}  {sale.address}")
