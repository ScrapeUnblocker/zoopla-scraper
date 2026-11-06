"""Turn Zoopla pages into records.

Search and listing pages are Next.js App Router pages: their data is streamed in
``self.__next_f.push([1, "..."])`` script chunks (the React "flight" payload). Joined
and unescaped they hold the search results (``regularListingsFormatted``), paging and
the listing details (an object with ``"__typename": "ListingData"``); long texts such as
the description are separate ``<id>:T<length>,<text>`` rows referenced as ``"$<id>"``.

Sold-price and property pages are classic Next.js pages with a ``__NEXT_DATA__`` JSON
script.

Every parser raises ``ValueError`` when a page does not hold the data it expects.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime
from typing import Any

from .errors import ListingNotFoundError, LocationNotFoundError
from .models import (
    Agent,
    Listing,
    ListingDetails,
    Photo,
    PreviousListing,
    PriceChange,
    PropertyHistory,
    PropertySale,
    SearchPage,
    SoldPrice,
    SoldPricesPage,
)
from .urls import absolute, property_url

#: Full-size listing photos and floor plans live on Zoopla's image CDN.
IMAGE_BASE = "https://lid.zoocdn.com/u/1024/768/"

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_TEXT_ROW = re.compile(rb"(?:^|\n)([0-9a-f]+):T([0-9a-f]+),")
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_OUTCODE = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)$")
_MONEY = re.compile(r"[\d,]+(?:\.\d+)?")
_ORDINAL = re.compile(r"(\d+)(st|nd|rd|th)\b", re.I)
_LEASE = re.compile(r"\((\d[\d,]*)\s+years?\)", re.I)
_FILE_NAME = re.compile(r"\.(jpe?g|png|gif|webp|heic)$", re.I)

_DECODER = json.JSONDecoder()


# -- low-level helpers -----------------------------------------------------------------


def flight(page: str) -> str:
    """The joined React flight payload of an App Router page ('' if there is none)."""
    return "".join(json.loads('"' + chunk + '"') for chunk in _PUSH.findall(page))


def text_rows(payload: str) -> dict[str, str]:
    """``<id>:T<hex length>,<text>`` rows of a flight payload (the length is in bytes)."""
    data = payload.encode("utf-8")
    rows = {}
    for match in _TEXT_ROW.finditer(data):
        size = int(match.group(2), 16)
        rows[match.group(1).decode()] = data[match.end() : match.end() + size].decode(
            "utf-8", "replace"
        )
    return rows


def first_value(payload: str, key: str, want: type | tuple[type, ...] = (list, dict)) -> Any:
    """The first JSON value of type ``want`` stored under ``"key":`` in a payload."""
    marker = f'"{key}":'
    start = payload.find(marker)
    while start != -1:
        at = start + len(marker)
        while payload[at : at + 1].isspace():
            at += 1
        try:
            value, _ = _DECODER.raw_decode(payload, at)
        except ValueError:
            value = None
        if isinstance(value, want):
            return value
        start = payload.find(marker, start + 1)
    return None


def objects(payload: str, marker: str) -> list[Any]:
    """Every JSON object in the payload that starts with ``marker``."""
    found = []
    start = payload.find(marker)
    while start != -1:
        try:
            value, _ = _DECODER.raw_decode(payload, start)
            found.append(value)
        except ValueError:
            pass
        start = payload.find(marker, start + 1)
    return found


def next_data(page: str) -> dict[str, Any]:
    match = _NEXT_DATA.search(page)
    if not match:
        raise ValueError("no __NEXT_DATA__ on the page")
    data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("__NEXT_DATA__ is not an object")
    return data


def page_title(page: str) -> str:
    match = _TITLE.search(page)
    return html_lib.unescape(match.group(1)).strip() if match else ""


def money(text: Any) -> float | None:
    """``"£1,750 pcm"`` -> ``1750``, ``"£403.85 pw"`` -> ``403.85``."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = _MONEY.search(str(text))
    if not match:
        return None
    number = float(match.group(0).replace(",", ""))
    return number


def _whole(value: float | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else round(value, 2)


def frequency(label: Any) -> str | None:
    """``pcm`` / ``pw`` at the end of a rent label."""
    text = str(label or "").strip().lower()
    for suffix in ("pcm", "pw"):
        if text.endswith(suffix):
            return suffix
    return None


def uk_date(text: Any) -> str | None:
    """``"5th Nov 2026"`` or ``"Last reduced: 27th Oct 2026"`` -> ``"2026-11-05"``.

    Other values (``"immediately"``) are returned as they are.
    """
    if not text:
        return None
    raw = str(text).strip()
    value = raw.split(":", 1)[1].strip() if ":" in raw else raw
    value = _ORDINAL.sub(r"\1", value)
    value = re.sub(r"^available from\s+", "", value, flags=re.I)
    for fmt in ("%d %b %Y", "%d %B %Y", "%d %b. %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def iso_date(text: Any) -> str | None:
    """The date part of an ISO timestamp."""
    return str(text)[:10] if text else None


def html_to_text(markup: Any) -> str | None:
    """Plain text from Zoopla's description HTML (``<br>`` and ``<p>`` become line breaks)."""
    if not markup:
        return None
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", str(markup), flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip() or None


def clean(text: Any) -> str | None:
    if text is None:
        return None
    value = html_lib.unescape(str(text)).strip()
    return value or None


def outcode(address: Any) -> str | None:
    """The postcode district at the end of an address (``"... Bristol BS9"`` -> ``BS9``)."""
    match = _OUTCODE.search(str(address or "").strip())
    return match.group(1) if match else None


def image_url(filename: Any) -> str | None:
    if not filename or not isinstance(filename, str):
        return None
    return filename if filename.startswith("http") else IMAGE_BASE + filename


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _dict(value: Any) -> dict[str, Any]:
    """A nested object, or ``{}`` for a missing one or an unresolved ``"$ref"`` string."""
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _labels(items: Any, key: str) -> list[str]:
    out = []
    for item in _list(items):
        label = clean(item.get(key)) if isinstance(item, dict) else clean(item)
        if label:
            out.append(label)
    return out


def _caption(value: Any) -> str | None:
    """A photo caption, or ``None`` when the agent's upload left just a file name."""
    text = clean(value)
    if not text or _FILE_NAME.search(text):
        return None
    return text


def _resolve(value: Any, texts: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$") and value[1:] in texts:
        return texts[value[1:]]
    return value


def _channel_of(url: str, section: Any = None) -> str:
    if str(section or "").startswith("to-rent") or "/to-rent/" in url:
        return "rent"
    return "sale"


def _rent(label: Any, alternative: Any) -> tuple[float | None, float | None]:
    """``(per month, per week)`` from a rent label and its alternative-frequency label."""
    pcm = pw = None
    for text in (label, alternative):
        kind = frequency(text)
        if kind == "pcm" and pcm is None:
            pcm = money(text)
        elif kind == "pw" and pw is None:
            pw = money(text)
    return _whole(pcm), _whole(pw)


# -- search results --------------------------------------------------------------------


def _features(raw: Any) -> dict[str, Any]:
    return {
        f.get("iconId"): f.get("content")
        for f in _list(raw)
        if isinstance(f, dict) and f.get("iconId")
    }


def _agent(branch: Any) -> Agent:
    data = _dict(branch)
    return Agent(
        name=clean(data.get("name") or data.get("branchName")),
        branch_id=_int(data.get("branchId")),
        phone=clean(data.get("phone") or data.get("redirectPhone")),
        url=absolute(data.get("branchDetailsUri")),
        logo=data.get("logoUrl") or None,
        is_developer=data.get("isDeveloper"),
    )


def parse_listing_card(
    raw: dict[str, Any], channel: str, *, page: int | None = None, position: int | None = None
) -> Listing:
    """One search result card."""
    listing_id = _int(raw.get("listingId"))
    if listing_id is None:
        raise ValueError("listing card without a listingId")
    detail = _dict(raw.get("listingUris")).get("detail") or f"/for-sale/details/{listing_id}/"
    url = absolute(detail) or ""
    feats = _features(raw.get("features"))
    label = clean(raw.get("price"))
    freq = frequency(label)
    pcm, pw = _rent(label, raw.get("alternativeRentFrequencyLabel"))
    if freq:
        price = pcm if freq == "pcm" else pw
    else:
        # Sale prices: the label and priceUnformatted agree. (For rentals priceUnformatted
        # is in the advertiser's own frequency, which can differ from the label's.)
        price = _whole(money(label)) if money(label) is not None else None
        if price is None:
            price = _whole(_float(raw.get("priceUnformatted")))
    drop = _dict(raw.get("priceDrop"))
    size = _int(raw.get("sizeSqft"))
    if size is None and isinstance(feats.get("area"), (int, float)):
        size = int(feats["area"])
    pos = _dict(raw.get("pos"))
    image = _dict(raw.get("image")).get("src")
    names = [str(n) for n in _list(raw.get("gallery")) if isinstance(n, str)]
    cover = str(image).rsplit("/", 1)[-1] if image else None
    if cover and cover not in names:
        names.insert(0, cover)
    gallery = [image_url(name) for name in names]
    return Listing(
        listing_id=listing_id,
        url=url,
        channel=_channel_of(url) if channel is None else channel,
        title=clean(raw.get("title")),
        address=clean(raw.get("address")),
        outcode=outcode(raw.get("address")),
        property_type=raw.get("propertyType") or None,
        bedrooms=_int(feats.get("bed")),
        bathrooms=_int(feats.get("bath")),
        receptions=_int(feats.get("chair")),
        size_sqft=size,
        size_source=raw.get("sizeSource") or None,
        price=price,
        price_frequency=freq,
        price_label=label,
        price_qualifier=clean(raw.get("priceTitle")),
        rent_pcm=pcm,
        rent_pw=pw,
        currency=raw.get("priceCurrency") or None,
        price_drop_amount=_whole(money(drop.get("priceChangeLabel"))),
        price_drop_percent=_float(drop.get("percentageChangeLabel")),
        price_reduced_on=uk_date(drop.get("lastPriceChangeDate")),
        first_price_on=uk_date(drop.get("firstPriceDate")),
        listed_on=uk_date(raw.get("publishedOn")),
        status=clean(raw.get("flag")),
        under_offer=raw.get("underOffer"),
        available_from=uk_date(raw.get("availableFrom")),
        new_home="/new-homes/" in url,
        tags=_labels(raw.get("tags"), "content"),
        features=[str(t) for t in _list(raw.get("enrichmentTags"))],
        highlights=_labels(raw.get("highlights"), "label"),
        buyer_incentives=[str(t) for t in _list(raw.get("derivedBuyerIncentives"))],
        summary=clean(raw.get("summaryDescription")),
        latitude=_float(pos.get("lat")),
        longitude=_float(pos.get("lng")),
        agent=_agent(raw.get("branch")),
        image=image or (gallery[0] if gallery else None),
        images=[g for g in gallery if g],
        image_count=_int(raw.get("numberOfImages")),
        floor_plan_count=_int(raw.get("numberOfFloorPlans")),
        video_count=_int(raw.get("numberOfVideos")),
        listing_tier=raw.get("displayType") or None,
        featured=bool(raw.get("featuredType")) or raw.get("listingType") == "featured",
        page=page,
        position=position,
    )


def _is_home_page(page: str) -> bool:
    title = page_title(page)
    return title.startswith("Zoopla >") or "Search Property to Buy, Rent" in title


def _search_echo(payload: str) -> dict[str, Any]:
    """The filters Zoopla reports for the search (from its analytics taxonomy)."""
    for obj in objects(payload, '{"activity":"listing_search"'):
        if isinstance(obj, dict) and "resultsSort" in obj:
            return {
                "sort": obj.get("resultsSort"),
                "price_min": _int(obj.get("priceMin")),
                "price_max": _int(obj.get("priceMax")),
                "beds_min": _int(obj.get("bedsMin")),
                "beds_max": _int(obj.get("bedsMax")),
                "radius": _float(obj.get("radius")),
                "area": obj.get("areaName"),
                "section": obj.get("section"),
            }
    return {}


def parse_search(page: str, url: str, channel: str, page_number: int = 1) -> SearchPage:
    """A search results page.

    Raises :class:`LocationNotFoundError` when Zoopla could not place the location (it
    sends the search to its home page, or shows an empty "Property for sale in -" page
    with no paging) and ``ValueError`` when the results are missing.
    """
    payload = flight(page)
    results = first_value(payload, "regularListingsFormatted", list)
    pagination = first_value(payload, "pagination", dict)
    if results is None or pagination is None:
        if _is_home_page(page) or (results == [] and '"pagination":null' in payload):
            raise LocationNotFoundError(f"Zoopla could not place this location: {url}")
        raise ValueError("no search results on the page")
    listings = []
    for raw in results:
        if isinstance(raw, dict) and raw.get("listingId"):
            listings.append(
                parse_listing_card(raw, channel, page=page_number, position=len(listings) + 1)
            )
    featured = []
    for raw in _list(first_value(payload, "featuredProperties", list)):
        if isinstance(raw, dict) and raw.get("listingId"):
            card = parse_listing_card(raw, channel, page=page_number, position=len(featured) + 1)
            card.featured = True
            featured.append(card)
    crumbs = _list(first_value(payload, "breadcrumbs", list))
    description = (
        clean(crumbs[-1].get("label")) if crumbs and isinstance(crumbs[-1], dict) else None
    )
    return SearchPage(
        url=url,
        channel=channel,
        page=_int(pagination.get("pageNumber")) or page_number,
        page_count=_int(pagination.get("pageNumberMax")),
        total_results=_int(pagination.get("totalResults")),
        listings=listings,
        featured=featured,
        description=re.sub(r"\s+", " ", description) if description else None,
        applied=_search_echo(payload),
    )


# -- listing details -------------------------------------------------------------------


def _key_facts(rows: Any) -> dict[str, str]:
    facts = {}
    for row in _list(rows):
        if isinstance(row, dict) and row.get("key") and row.get("value") is not None:
            facts[str(row["key"])] = clean(row["value"]) or ""
    return facts


def _media(items: Any) -> list[str]:
    urls = []
    for item in _list(items):
        if isinstance(item, dict):
            link = item.get("url") or item.get("original")
            if link:
                urls.append(str(link))
    return urls


def _images(block: Any) -> list[str]:
    return [
        u for u in (image_url(i.get("filename")) for i in _list(_dict(block).get("image"))) if u
    ]


def parse_listing(page: str, url: str) -> ListingDetails:
    """A listing page.

    Raises :class:`ListingNotFoundError` when Zoopla answered with a search page (the
    listing was removed) and ``ValueError`` when the listing data is missing.
    """
    payload = flight(page)
    found = [o for o in objects(payload, '{"__typename":"ListingData"') if isinstance(o, dict)]
    if not found:
        if first_value(payload, "regularListingsFormatted", list) is not None:
            raise ListingNotFoundError(f"listing no longer on Zoopla: {url}")
        raise ValueError("no listing data on the page")
    # The data appears more than once; the full copy is the longest one.
    data = max(found, key=lambda o: len(json.dumps(o)))
    texts = text_rows(payload)
    taxonomy = _dict(data.get("analyticsTaxonomy")) or _dict(data.get("adTargeting"))
    pricing = _dict(data.get("pricing"))
    counts = _dict(data.get("counts"))
    location = _dict(data.get("location"))
    coords = _dict(location.get("coordinates"))
    facts = _key_facts(data.get("ntsInfo"))
    listing_id = _int(data.get("listingId")) or _int(taxonomy.get("listingId"))
    if listing_id is None:
        raise ValueError("listing data without a listingId")

    label = clean(pricing.get("label"))
    freq = frequency(label) or pricing.get("rentFrequencyLabel") or None
    alternative = _dict(pricing.get("alternateRentFrequencyPrice")).get("label")
    pcm, pw = _rent(label, alternative)
    if freq:
        price = pcm if freq == "pcm" else pw
    else:
        price = _whole(_float(pricing.get("internalValue")))
        if price is None:
            price = _whole(money(label))

    area = _dict(data.get("floorArea"))
    size = _float(area.get("value")) if "ft" in str(area.get("unitsLabel") or "") else None
    if size is None:
        size = _float(_dict(data.get("ingested")).get("sizeSqft"))
    tenure_text = facts.get("tenure")
    lease = _LEASE.search(tenure_text or "")
    out_code = location.get("outcode") or taxonomy.get("outcode")
    in_code = taxonomy.get("incode")
    stations = []
    names = _list(taxonomy.get("nearestStations"))
    miles = _list(taxonomy.get("nearestStationsInMiles"))
    for i, name in enumerate(names):
        stations.append({"name": name, "miles": miles[i] if i < len(miles) else None})
    description_html = _resolve(data.get("detailedDescription"), texts)
    if isinstance(description_html, str) and description_html.startswith("$"):
        description_html = None
    embedded = _dict(data.get("embeddedContent"))
    changes = [
        PriceChange(date=iso_date(c.get("priceChangeDate")), is_drop=c.get("isPriceDrop"))
        for c in _list(_dict(data.get("priceHistory")).get("priceChanges"))
        if isinstance(c, dict)
    ]
    photos = [
        Photo(url=image_url(p.get("filename")) or "", caption=_caption(p.get("caption")))
        for p in _list(data.get("propertyImage"))
        if isinstance(p, dict) and p.get("filename")
    ]
    final_url = absolute(_canonical_listing_path(data)) or url
    return ListingDetails(
        listing_id=listing_id,
        url=final_url,
        channel=_channel_of(final_url, data.get("section")),
        title=clean(data.get("title")),
        address=clean(data.get("displayAddress")),
        postcode=f"{out_code} {in_code}" if out_code and in_code else None,
        outcode=out_code or None,
        area=clean(taxonomy.get("areaName")),
        post_town=clean(taxonomy.get("postTownName")),
        region=clean(location.get("region")),
        property_type=data.get("propertyType") or taxonomy.get("propertyType") or None,
        bedrooms=_int(counts.get("numBedrooms")),
        bathrooms=_int(counts.get("numBathrooms")),
        receptions=_int(counts.get("numLivingRooms")),
        floor_area_sqft=_whole(size),
        size_source=_dict(data.get("ingested")).get("sizeSource") or None,
        price=price,
        price_frequency=freq,
        price_label=label,
        price_qualifier=clean(pricing.get("priceQualifierLabel")),
        rent_pcm=pcm,
        rent_pw=pw,
        currency=pricing.get("currencyCode") or taxonomy.get("currencyCode") or None,
        is_auction=pricing.get("isAuction"),
        listing_status=taxonomy.get("listingStatus") or None,
        listing_condition=taxonomy.get("listingCondition") or None,
        status=clean(_dict(data.get("statusSummary")).get("label")),
        published_at=data.get("publishedOn") or None,
        price_changes=changes,
        tenure=tenure_text,
        lease_years_remaining=_int(lease.group(1).replace(",", "")) if lease else None,
        council_tax_band=facts.get("council_tax_band"),
        ground_rent=facts.get("ground_rent"),
        service_charge=facts.get("service_charge"),
        deposit=facts.get("deposit"),
        key_facts=facts,
        utilities=_key_facts(data.get("additionalNtsInfo")),
        epc_rating=_dict(data.get("derivedEPC")).get("efficiencyRating")
        or taxonomy.get("epcRating")
        or None,
        chain_free=taxonomy.get("chainFree"),
        furnished_state=taxonomy.get("furnishedState") or None,
        shared_ownership=data.get("sharedOwnership", taxonomy.get("isSharedOwnership")),
        retirement_home=taxonomy.get("isRetirementHome"),
        buyer_incentives=[str(b) for b in _list(_dict(data.get("derived")).get("buyerIncentives"))],
        tags=_labels(data.get("tagsV2"), "label"),
        features=_labels(_dict(data.get("features")).get("bullets"), "text"),
        description=html_to_text(description_html),
        description_html=description_html or None,
        latitude=_float(coords.get("latitude")),
        longitude=_float(coords.get("longitude")),
        nearest_stations=stations,
        agent=_agent(data.get("branchV2")),
        photos=photos,
        floor_plans=_images(data.get("floorPlan")),
        epc_images=_images(data.get("epc")),
        videos=_media(embedded.get("videos")),
        virtual_tours=_media(embedded.get("tours")) + _media(embedded.get("links")),
        brochures=_media(data.get("additionalLinks")),
    )


def _canonical_listing_path(data: dict[str, Any]) -> str | None:
    section = str(data.get("section") or "")
    listing_id = data.get("listingId")
    if not listing_id or section not in ("for-sale", "to-rent", "new-homes"):
        return None
    return f"/{section}/details/{listing_id}/"


# -- sold prices and property pages ----------------------------------------------------


def _sold_record(node: dict[str, Any], page: int, position: int) -> SoldPrice:
    address = _dict(node.get("address"))
    attrs = _dict(node.get("attributes"))
    sale = _dict(node.get("lastSale"))
    uprn = _int(node.get("uprn") or address.get("uprn"))
    return SoldPrice(
        uprn=uprn,
        address=clean(address.get("fullAddress")),
        postcode=clean(address.get("postcode")),
        sold_on=iso_date(sale.get("date")),
        price=_int(sale.get("price")),
        property_type=clean(attrs.get("propertyType")),
        tenure=clean(attrs.get("tenure")),
        bedrooms=_int(attrs.get("bedrooms")),
        bathrooms=_int(attrs.get("bathrooms")),
        receptions=_int(attrs.get("livingRooms")),
        floor_area_sqm=_float(attrs.get("floorAreaSqM")),
        latitude=_float(address.get("latitude")),
        longitude=_float(address.get("longitude")),
        property_url=property_url(uprn) if uprn else None,
        page=page,
        position=position,
    )


def parse_sold(page: str, url: str, location: str, page_number: int = 1) -> SoldPricesPage:
    """A ``/house-prices/<place>/`` page."""
    props = _dict(_dict(next_data(page).get("props")).get("pageProps"))
    search = props.get("propertiesSearch")
    if not isinstance(search, dict):
        raise ValueError("no sold prices on the page")
    records = []
    for edge in _list(search.get("edges")):
        node = _dict(_dict(edge).get("node"))
        if node:
            records.append(_sold_record(node, page_number, len(records) + 1))
    averages = {
        kind: (_int(value) or None)
        for kind, value in _dict(props.get("activity")).items()
        if kind in ("all", "detached", "semi", "terraced", "flat")
    }
    return SoldPricesPage(
        url=url,
        location=location,
        page=page_number,
        area=clean(props.get("areaName")),
        area_type=props.get("pageType") or None,
        total_results=_int(search.get("totalResults")),
        has_next=bool(_dict(search.get("pageInfo")).get("hasNextPage")),
        average_prices=averages,
        sort=_dict(props.get("taxonomy")).get("resultsSort"),
        records=records,
    )


def _photo_set(items: Any, size: str = "large") -> list[str]:
    return [
        str(i.get(size) or i.get("medium") or "")
        for i in _list(items)
        if isinstance(i, dict) and (i.get(size) or i.get("medium"))
    ]


def parse_property(page: str, url: str) -> PropertyHistory:
    """A ``/property/uprn/<n>/`` page."""
    props = _dict(_dict(next_data(page).get("props")).get("pageProps"))
    prop = props.get("property")
    if not isinstance(prop, dict) or not prop.get("uprn"):
        raise ValueError("no property data on the page")
    address = _dict(prop.get("address"))
    attrs = _dict(prop.get("attributes"))
    history = _dict(prop.get("history"))
    sales = [
        PropertySale(
            date=iso_date(s.get("date")),
            price=_int(s.get("price")),
            change_amount=_int(s.get("numericChange")),
            change_percent=round(s["percentageChange"], 1)
            if isinstance(s.get("percentageChange"), (int, float))
            else None,
        )
        for s in _list(history.get("historicSales"))
        if isinstance(s, dict)
    ]
    previous = []
    for item in _list(history.get("historicListings")):
        if not isinstance(item, dict):
            continue
        rooms = _dict(item.get("attributes"))
        previous.append(
            PreviousListing(
                date=iso_date(item.get("date")),
                price=_int(item.get("price")),
                price_type=item.get("priceType") or None,
                bedrooms=_int(rooms.get("bedrooms")),
                bathrooms=_int(rooms.get("bathrooms")),
                receptions=_int(rooms.get("livingRooms")),
                url=absolute(item.get("uri")),
                images=_photo_set(item.get("images")),
                floor_plans=_photo_set(item.get("floorplans")),
            )
        )
    uprn = int(prop["uprn"])
    return PropertyHistory(
        uprn=uprn,
        url=property_url(uprn),
        address=clean(address.get("fullAddress")),
        postcode=clean(address.get("postcode")),
        outcode=clean(address.get("outcode")),
        country=clean(address.get("country")),
        latitude=_float(address.get("latitude")),
        longitude=_float(address.get("longitude")),
        property_type=clean(attrs.get("propertyType")),
        tenure=clean(attrs.get("tenure")),
        bedrooms=_int(attrs.get("bedrooms")),
        bathrooms=_int(attrs.get("bathrooms")),
        receptions=_int(attrs.get("livingRooms")),
        floor_area_sqm=_float(attrs.get("floorAreaSqM")),
        epc_rating=_dict(prop.get("energy")).get("currentEnergyRating") or None,
        listed_now=bool(_list(prop.get("liveListings"))),
        sales=sales,
        sales_source=history.get("soldPricesDataSource") or None,
        previous_listings=previous,
    )
