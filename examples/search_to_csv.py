"""Three-bedroom houses for sale in Bristol under £450,000, newest first, saved as CSV.

Run: python examples/search_to_csv.py  (needs SCRAPEUNBLOCKER_KEY)
"""

from zoopla_scraper import SearchFilters, ZooplaScraper, to_csv_file

zoopla = ZooplaScraper()
filters = SearchFilters(
    beds_min=3,
    price_max=450_000,
    property_types=["detached", "semi_detached", "terraced"],
    sort="newest",
)
homes = zoopla.search_listings("Bristol", filters=filters, max_pages=2)
to_csv_file(homes, "bristol-homes.csv")

print(f"{len(homes)} homes saved to bristol-homes.csv ({zoopla.requests} requests)")
for home in homes[:10]:
    size = f"{home.size_sqft:,} sq ft" if home.size_sqft else "-"
    print(f"£{home.price:>9,.0f}  {home.bedrooms} bed  {size:>11}  {home.address}")
