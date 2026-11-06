# Zoopla Scraper

[![CI](https://github.com/ScrapeUnblocker/zoopla-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/zoopla-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [Zoopla](https://www.zoopla.co.uk), the UK property portal, into clean JSON or
CSV: homes for sale and to rent with Zoopla's own filters, full listing details, sold
house prices for any town, postcode district or postcode, a property's complete sale
history, and sold comparables for any listing.**
For every listing in the search results you get the listing id, URL, address and postcode
district, property type, bedrooms, bathrooms and receptions, floor area, the asking price
with its qualifier ("Guide price", "Offers over"), monthly **and** weekly rent for
rentals, the last price reduction (amount, percent, date), listed-on date, "Just added" /
"Back to market" status, tags (chain free, freehold, shared ownership, ...), feature tags,
coordinates, the agent with phone and branch page, and full-size photo URLs. Open a
listing to get its full postcode, tenure and years left on the lease, council tax band,
ground rent, service charge, deposit, EPC rating, every price change, the description,
nearest stations, utilities, floor plans, EPC graphs, videos, virtual tours and brochures.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
every page is fetched with the `getPageSource` API through the official Python SDK, and the
scraper reads the data Zoopla embeds in its own pages. You don't need a Zoopla account,
cookies, a headless browser or retry logic of your own.

## Features

- **Search homes for sale or to rent** in any town, area, postcode district or postcode,
  with Zoopla's filters: bedrooms, bathrooms, price, property type (detached,
  semi-detached, terraced, flats, bungalows, land, park homes), radius, keywords, added
  within, floor area, reduced only, new homes (include, exclude, only), under offer and
  sold STC, chain free, auctions, shared ownership and retirement homes, and for rentals
  furnishing, pets allowed, bills included, available from, student lets and house shares.
  Five sort orders. 25 listings per page, up to Zoopla's 40 pages, several places merged
  without duplicates. Paste any zoopla.co.uk search URL and its filters are kept.
- **Filter check**: Zoopla reports which sort, price, bedroom and radius filters it
  applied; anything it ignored is printed as a warning instead of silently returning
  unfiltered results.
- **Place names that need resolving** ("Leeds" is `west-yorkshire/leeds` on Zoopla) go
  through Zoopla's own location resolver, the one its search box uses.
- **Rent in both units**: some rentals are advertised per week and some per month, and
  Zoopla's raw price field follows the advertiser. Every rental gets `rent_pcm` and
  `rent_pw` from Zoopla's own labels, so prices compare.
- **Full listing details** by id or URL, for sale, rental and new-home listings.
- **Sold house prices** (HM Land Registry data shown by Zoopla) for a town, area,
  postcode district or full postcode: sold date and price, property type, tenure,
  bedrooms, bathrooms, floor area, coordinates and UPRN, filtered by property type,
  sold-within window and bedrooms, sorted by date, price or address, plus the 12-month
  average sold price by property type.
- **Property history** by UPRN: every recorded sale with the change since the previous
  one, and the property's past Zoopla listings with their photos and floor plans.
- **Sold comparables**: the listing's recent sales in its postcode (widened to the
  postcode district when there are fewer than five), same property type and bedrooms,
  with the median, mean, range and how the asking price compares with the median.
- **Watch mode**: run a search daily and get new listings, price drops and increases,
  homes that went under offer or came back, and listings that disappeared.
- **JSON, JSON Lines, CSV (Excel-friendly) or a terminal table**, from a CLI or a Python
  library. Typed dataclasses, retries with backoff, offline tests.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/zoopla-scraper.git
cd zoopla-scraper
pip install .            # or: pip install -r requirements.txt
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and put it in the environment (the official SDK reads `SCRAPEUNBLOCKER_KEY`):

```bash
cp .env.example .env     # then edit .env, or:
export SCRAPEUNBLOCKER_KEY=your_key_here
```

## CLI usage

```bash
# 3+ bed houses in Bristol under £450k, newest first, as a table
zoopla-scraper search bristol --beds-min 3 --price-max 450000 --type semi,terraced --sort newest

# Every page Zoopla shows, saved as CSV (the format follows the file extension)
zoopla-scraper search "Milton Keynes" --type detached --chain-free --all -o mk-detached.csv

# Rentals: 2-bed furnished flats in Leeds up to £1,500 a month that allow pets
zoopla-scraper search leeds --rent --beds-min 2 --type flats --price-max 1500 \
    --furnished furnished --pets-allowed

# Keep the filters of a search you set up on zoopla.co.uk
zoopla-scraper search "https://www.zoopla.co.uk/for-sale/property/bs9/?radius=1&price_max=600000"

# Full listing details (several ids or URLs, or --from-file)
zoopla-scraper listing 74693032 https://www.zoopla.co.uk/to-rent/details/74699742/

# Flats sold in BS9 in the last 5 years, most expensive first
zoopla-scraper sold-prices BS9 --type flat --months 60 --sort price-high -f table

# Average sold prices over the last 12 months, by property type
zoopla-scraper sold-prices manchester "BS9 4LY" --averages

# A property's sale history and past listings (UPRN from sold-prices)
zoopla-scraper property 52771

# Is a listing priced in line with recent sales nearby?
zoopla-scraper comps 74694318 -f table

# Run daily: new listings and price changes since the last run
zoopla-scraper watch bath --sort newest --state bath-watch.json --pages 3
```

Places can be a town or city (`bristol`, `"Milton Keynes"`), a postcode district (`bs9`),
a full postcode (`"BS9 4LY"`), a Zoopla slug with a `/` (`west-yorkshire/leeds`, taken
from a zoopla.co.uk URL) or a pasted zoopla.co.uk search URL.

### Search filters

| Option | Applies to | Values |
| --- | --- | --- |
| `--rent` | | search homes to rent (default: for sale) |
| `--beds-min/--beds-max`, `--baths-min/--baths-max` | both | numbers |
| `--price-min/--price-max` | both | pounds; per month for rentals (`--price-per week` to change) |
| `--type` | both | `detached`, `semi_detached`, `terraced`, `flats`, `bungalow`, `farms_land`, `park_home` (also `semi`, `flat`) |
| `--radius` | both | `0`, `0.25`, `0.5`, `1`, `3`, `5`, `10`, `15`, `20`, `30`, `40` miles |
| `--keywords` | both | words in the listing, e.g. `"garden parking"` |
| `--added` | both | `24h`, `3d`, `7d`, `14d`, `30d` |
| `--size-min/--size-max` | both | floor area in sq ft |
| `--sort` | both | `recommended`, `newest`, `price-high`, `price-low`, `most-reduced` |
| `--reduced-only`, `--retirement only/exclude` | both | |
| `--new-homes` | sale | `include`, `exclude`, `only` |
| `--include-sold` | sale | also list homes under offer or sold STC |
| `--chain-free`, `--auction only/exclude`, `--shared-ownership only/exclude` | sale | |
| `--furnished` | rent | `furnished`, `part_furnished`, `unfurnished` |
| `--pets-allowed`, `--bills-included` | rent | |
| `--available` | rent | `now`, `1m`, `3m`, `6m`, `12m` |
| `--student`, `--house-share` | rent | `only`, `exclude` |

`--pages N` (25 listings each), `--all` (up to Zoopla's 40 pages), `--limit N`,
`--featured` (also include the paid featured slots Zoopla shows above each page's results),
`-f json|jsonl|csv|table`, `-o FILE`, `--retries N`, `-v`.

Sold prices take `--type detached|semi|terraced|flat`, `--months 3|6|12|60|120|240`,
`--beds-min/--beds-max`, `--baths-min/--baths-max` and
`--sort newest|oldest|price-high|price-low|address|address-desc`.

## Library usage

```python
from zoopla_scraper import SearchFilters, SoldFilters, ZooplaScraper

zoopla = ZooplaScraper()  # reads SCRAPEUNBLOCKER_KEY

# One page, with what Zoopla says about the search
page = zoopla.search("bristol", filters=SearchFilters(beds_min=3, sort="newest"))
print(page.total_results, page.page_count, page.description, page.warnings)

# Several pages and places, merged without duplicates
homes = zoopla.search_listings(
    ["bath", "bristol"],
    filters=SearchFilters(price_max=500_000, property_types=["detached"]),
    max_pages=3,
)
for home in homes:
    print(home.listing_id, home.price, home.bedrooms, home.size_sqft, home.address)

# Rentals: rent_pcm and rent_pw for every listing
flats = zoopla.search_listings("leeds", "rent", SearchFilters(beds_min=2, furnished="furnished"))

# Listing details, sold prices, property history, comparables
details = zoopla.listing(homes[0].listing_id)
print(details.postcode, details.tenure, details.council_tax_band, details.epc_rating)

sold = zoopla.sold_prices("bs9", SoldFilters(property_type="flat", months=60))
print(sold.average_prices, [r.price for r in sold.records])

history = zoopla.property_history(sold.records[0].uprn)
comps = zoopla.comparables(details, months=12)
print(comps.median_price, comps.asking_vs_median_percent)
```

Errors: `LocationNotFoundError` (Zoopla cannot place the location), `ListingNotFoundError`
(the listing was sold, let or withdrawn), `NotFoundError` (unknown UPRN), `ParseError`
(the page did not have the expected data twice in a row) and `InputError` (a bad filter
value). All derive from `ZooplaError`.

### Examples

- [`examples/search_to_csv.py`](examples/search_to_csv.py) - 3-bed houses in Bristol under
  £450k, newest first, two pages, saved as CSV.
- [`examples/sold_comps.py`](examples/sold_comps.py) - compare a listing's asking price with
  recent sales of the same type and size nearby.
- [`examples/rent_watch.py`](examples/rent_watch.py) - new rentals and rent changes in Leeds
  since the last run.

## Example output

`zoopla-scraper search bristol --beds-min 3 --price-max 450000 --type semi,terraced --sort newest`

```text
bristol: 932 results, 38 pages (3+ bedroom houses for sale)
25 listings (1 requests)
id        price     rooms    type           sqft   address                                  listed      status
74694318  £325,000  3bd/1ba  semi_detached  775    Fox Court, Longwell Green, Bristol BS30  2026-11-05  Just added
74693450  £450,000  3bd/1ba  terraced       1,194  Green Street, Totterdown BS3             2026-11-05  Just added
73617087  £425,000  3bd/1ba  semi_detached  969    Hallen Drive, Sea Mills, Bristol BS9     2026-07-09  Back to market
74692961  £400,000  3bd/2ba  semi_detached  1,065  Cherry Banks, Lyde Green, Bristol BS16   2026-11-05  Just added
73133298  £375,000  3bd/1ba  semi_detached  1,076  Tudor Road, Bristol BS15                 2026-11-05  Just added
...
```

`zoopla-scraper listing 74693032` (shortened):

```json
{
  "listing_id": 74693032,
  "url": "https://www.zoopla.co.uk/for-sale/details/74693032/",
  "channel": "sale",
  "title": "5 bed detached house for sale",
  "address": "Elmlea Avenue, Westbury-On-Trym, Bristol BS9",
  "postcode": "BS9 3UX",
  "region": "South West England",
  "property_type": "detached",
  "bedrooms": 5,
  "bathrooms": 2,
  "receptions": 3,
  "floor_area_sqft": 1840,
  "price": 850000,
  "price_label": "£850,000",
  "price_qualifier": "Guide price",
  "listing_status": "for_sale",
  "published_at": "2026-11-05T16:23:45",
  "tenure": "Freehold",
  "council_tax_band": "F",
  "epc_rating": "C",
  "chain_free": false,
  "features": [
    "5 Bedrooms spread over 2 floors (1 with an en-suite).",
    "Far reaching semi rural views.",
    "Space and installation of an EV point."
  ],
  "nearest_stations": [
    {"name": "Sea Mills", "miles": 1.2},
    {"name": "Clifton Down", "miles": 1.3}
  ],
  "agent": {
    "name": "Richard Harding Estate Agents",
    "url": "https://www.zoopla.co.uk/find-agents/branch/richard-harding-estate-agents-bristol-6534/"
  },
  "photos": [
    {"url": "https://lid.zoocdn.com/u/1024/768/d885bcfe92a076fe2439a5584027b79e2c06902f.jpg", "caption": "External"}
  ],
  "floor_plans": ["https://lid.zoocdn.com/u/1024/768/7cce0007d4043229d56419fe096b1498338c6449.jpg"]
}
```

`zoopla-scraper sold-prices BS9 --type flat --months 60 --sort price-high --limit 4`

```text
BS9: 468 sales (BS9)
sold        price       type             beds  sqm    tenure     address
2022-04-21  £1,407,176  Flat/Maisonette  3     126.0  Freehold   17 Grange Court Road, Bristol, BS9 4DP
2025-07-10  £925,750    Flat/Maisonette  3     198.0  Leasehold  First Floor Flat, Crete Hill House, Cote House Lane, Bristol, BS9 3UW
2025-10-06  £810,000    Converted Flat   3     154.0  Leasehold  Ground Floor Flat, 34 Downleaze, Stoke Bishop, Bristol, BS9 1LY
2022-09-26  £799,000    Flat/Maisonette  -     141.0  Leasehold  56 Oatley House, Cote Lane, Bristol, BS9 3TN
```

`zoopla-scraper sold-prices manchester "BS9 4LY" --averages`

```text
location,area,all,detached,flat,terraced,semi
manchester,Manchester,273858,444100,210039,250996,333372
BS9 4LY,BS9 4LY,525000,,,525000,
```

`zoopla-scraper comps 74694318 -f table`

```text
25 sales in outcode BS30 ({'property_type': 'semi', 'months': 12, 'beds_min': 3, 'beds_max': 3, 'sort': 'newest'})
listing   asking    scope         sold  median    min       max       vs median
74694318  £325,000  outcode BS30  25    £362,000  £270,000  £471,050  -10.2%
```

`zoopla-scraper watch bath --sort newest --state bath-watch.json -f table` (second run)

```text
3 changes
change          id        old       new       pct    address
back_on_market  71167920  £350,000  £350,000  -      Batheaston, Bath, Somerset BA1
new             71394800  -         £339,950  -      Southlands, Bath BA1
price_drop      70414026  £700,000  £695,000  -0.7%  Brock Street, Bath BA1
```

## How it works

- **Search and listing pages** are Next.js pages that stream their data into the HTML as
  `self.__next_f.push(...)` script chunks. The scraper joins and unescapes them, then reads
  `regularListingsFormatted` (the 25 results), `pagination`, the breadcrumbs, Zoopla's
  own report of the applied filters and, on a listing page, the `ListingData` object. Long
  texts such as the description are separate rows in the same stream, matched up by id.
- **Sold prices and property pages** carry their data in the `__NEXT_DATA__` JSON script.
- Rentals: the price label (`£1,750 pcm`) and its alternative (`£403.85 pw`) give the rent
  in both units. The raw number next to them follows the advertiser's own unit.
- A place Zoopla cannot place from the plain slug gets an empty search page; the scraper
  then asks `zoopla.co.uk/api/search/resolver/` (what Zoopla's search box calls) for the
  real path and remembers it for the rest of the run. A removed listing redirects to a
  search page, which is reported as `ListingNotFoundError`.
- Photos and floor plans are full-size `lid.zoocdn.com` URLs.
- Throttled, blocked and timed-out requests are retried with doubling backoff
  (`--retries`, default 3). A page without the expected data is fetched once more.

The Zoopla estimate on property pages is blurred until a visitor chooses to reveal it, so
it is not part of the output.

## Project layout

```text
zoopla-scraper/
├── src/zoopla_scraper/
│   ├── __init__.py      # public API
│   ├── scraper.py       # ZooplaScraper: fetch, retry, search, listing, sold, comps, watch
│   ├── parsing.py       # page payload -> records
│   ├── urls.py          # locations, filters, URL building
│   ├── models.py        # dataclasses with JSON / CSV / table layouts
│   ├── monitor.py       # watch-mode snapshots and diffs
│   ├── export.py        # JSON, JSON Lines, CSV, table
│   └── cli.py           # zoopla-scraper command
├── examples/            # runnable scripts
├── tests/               # offline tests (fake SDK client, no API calls)
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .github/workflows/ci.yml
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install   # pip install -e ".[dev]"
make lint      # ruff check + ruff format --check
make test      # pytest, offline
```

The tests build small pages in the shape of real Zoopla pages and replace the SDK client
with a fake one, so they run without an API key and spend no credit.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [ScrapeUnblocker documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [Python SDK on PyPI](https://pypi.org/project/scrapeunblocker/)

Use the data responsibly and in line with Zoopla's terms and the law that applies to you;
listing texts and photos belong to the agents who published them.

## License

[MIT](LICENSE)
