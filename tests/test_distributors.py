"""
Tests for the distributor layer.

No test here touches the network, and that is not only for speed. The Mouser and
Digi-Key adapters have never been run against the live APIs from this project --
credentials need an account, and the account terms are the account holder's to
accept. So these tests prove the parsing, the auth sequence, the throttling and
the failure handling against recorded response shapes, and they prove nothing
about the network. The code says so, the report says so, and
`test_an_unverified_adapter_admits_it_is_unverified` makes sure it keeps saying
so.

The fixtures below are shaped from the published API documentation. Where a real
response differs, these tests are how the difference gets found: change the
fixture, watch what breaks.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from helix_bom.distributors import (
    DigiKeyDistributor,
    Lifecycle,
    LookupCache,
    MouserDistributor,
    OfflineDistributor,
    Offer,
    Outcome,
    PartRecord,
    PriceBreak,
    normalise_mpn,
    parse_money,
    read_lifecycle,
)
from helix_bom.distributors.base import Lookup

NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


class _Response:
    def __init__(self, payload, status=200):
        self._raw = (payload if isinstance(payload, bytes)
                     else json.dumps(payload).encode("utf-8"))

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(payload):
    captured = []

    def open_it(request, timeout=0):
        captured.append(request)
        return _Response(payload)
    open_it.captured = captured
    return open_it


# --------------------------------------------------------------------
# Money
# --------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("$0.19", "0.19"),
    ("0.19", "0.19"),
    ("0,19 €", "0.19"),          # a comma decimal, as half the world writes it
    ("1,234.56", "1234.56"),     # thousands comma
    ("1.234,56", "1234.56"),     # the same number, written the other way
    ("1,234", "1234"),           # three digits after the comma: a group, not a decimal
    ("  0.0550  ", "0.0550"),
    ("USD 12", "12"),
])
def test_prices_are_read_in_whatever_dialect_they_arrive(raw, expected):
    """Getting this wrong by a factor of a thousand on a reel of ten thousand
    parts is not a rounding error. The ambiguous cases are decided by where the
    separators sit, not by assuming everyone writes numbers the same way."""
    assert parse_money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "n/a", "call for pricing", None, "abc"])
def test_an_unreadable_price_is_none_and_never_zero(raw):
    """Zero is a price. "I could not read this" is not, and a report that
    silently costs an unreadable line at nothing under-states the build."""
    assert parse_money(raw) is None


def test_a_number_that_is_already_a_number_survives():
    assert parse_money(Decimal("0.055")) == Decimal("0.055")
    assert parse_money(12) == Decimal("12")


# --------------------------------------------------------------------
# Lifecycle and part numbers
# --------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Active", Lifecycle.ACTIVE),
    ("Obsolete", Lifecycle.OBSOLETE),
    ("End of Life", Lifecycle.OBSOLETE),
    ("Discontinued at Digi-Key", Lifecycle.OBSOLETE),
    ("Not Recommended for New Designs", Lifecycle.NRND),
    ("NRND", Lifecycle.NRND),
    ("Last Time Buy", Lifecycle.NRND),
    ("", Lifecycle.UNKNOWN),
    ("Whatever they invent next", Lifecycle.UNKNOWN),
])
def test_lifecycle_wording_maps_onto_a_state(text, expected):
    assert read_lifecycle(text) is expected


def test_the_worse_reading_wins_when_a_status_says_two_things():
    """"Active - NRND" happens. Reading it as active would let an obsolescent
    part through a check that exists to catch exactly that."""
    assert read_lifecycle("Active - NRND") is Lifecycle.NRND
    assert read_lifecycle("Active, being discontinued") is Lifecycle.OBSOLETE


def test_part_numbers_are_folded_for_case_and_nothing_else():
    """The restraint is the point. TPS61023DRLR and TPS61023DRLT differ only in
    the reel and are different orderable parts; a normaliser clever enough to
    call them equal would approve a BOM that cannot be assembled."""
    assert normalise_mpn(" tps61023drlr ") == "TPS61023DRLR"
    assert normalise_mpn("TPS61023DRLR") != normalise_mpn("TPS61023DRLT")
    assert normalise_mpn("GRM188R71H104KA93D") != normalise_mpn("GRM188R71H104KA93")


# --------------------------------------------------------------------
# Price breaks
# --------------------------------------------------------------------

def _offer(breaks=((1, "1.00"), (10, "0.80"), (100, "0.50")), **kw):
    return Offer(distributor="test", distributor_part_number="X", url="",
                 price_breaks=tuple(PriceBreak(q, Decimal(p)) for q, p in breaks),
                 fetched_at=NOW, **kw)


@pytest.mark.parametrize("quantity,expected", [
    (1, "1.00"), (9, "1.00"), (10, "0.80"), (99, "0.80"),
    (100, "0.50"), (5000, "0.50"),
])
def test_the_price_is_the_price_at_the_quantity_being_bought(quantity, expected):
    """The check this whole layer exists for. A BOM costed at the one-off price
    over-states a production run; one costed at the reel price under-states a
    prototype. Both are common and both are invisible without this."""
    assert _offer().unit_price_at(quantity) == Decimal(expected)


def test_a_quantity_below_the_smallest_break_has_no_price():
    """Reel-only parts have a single break at 3000. Asking for three of them
    has no answer, and inventing one would be the exact failure this library
    was written to prevent."""
    offer = _offer(breaks=((3000, "0.05"),))
    assert offer.unit_price_at(3) is None
    assert offer.extended_price_at(3) is None


def test_extended_price_multiplies_out():
    assert _offer().extended_price_at(100) == Decimal("50.00")


def test_an_offer_knows_how_old_it_is():
    offer = _offer()
    assert offer.age_hours(NOW) == 0
    assert offer.age_hours(NOW + timedelta(hours=6)) == 6


# --------------------------------------------------------------------
# The three-valued outcome
# --------------------------------------------------------------------

def test_a_not_checked_result_must_say_why():
    """"Not checked" without a reason gives the reader nothing to act on, and
    the action differs: a missing key, a dead network and a spent quota are
    three different problems."""
    with pytest.raises(ValueError, match="why"):
        Lookup(query="X", outcome=Outcome.NOT_CHECKED)
    assert Lookup(query="X", outcome=Outcome.NOT_CHECKED, reason="no key").reason


def test_not_found_and_not_checked_are_different_values():
    assert Outcome.NOT_FOUND is not Outcome.NOT_CHECKED


# --------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------

def _cached_lookup():
    return Lookup(query="BME280", outcome=Outcome.MATCHED,
                  record=PartRecord(manufacturer_part_number="BME280",
                                    manufacturer="Bosch",
                                    lifecycle=Lifecycle.ACTIVE,
                                    lifecycle_text="Active",
                                    offers=(_offer(stock=10),)))


def test_a_cached_lookup_survives_a_round_trip_with_its_types(tmp_path):
    """Decimals must come back as Decimals. A price that becomes a float on the
    way through the cache is a price that drifts."""
    path = tmp_path / "c.json"
    cache = LookupCache(path=path)
    cache.put("mouser", "BME280", _cached_lookup(), now=NOW)
    cache.save()

    reloaded = LookupCache(path=path).get("mouser", "BME280", now=NOW)
    assert reloaded.outcome is Outcome.MATCHED
    assert reloaded.record.lifecycle is Lifecycle.ACTIVE
    price = reloaded.record.offers[0].unit_price_at(10)
    assert isinstance(price, Decimal) and price == Decimal("0.80")
    assert reloaded.record.offers[0].fetched_at == NOW


def test_an_entry_older_than_the_ttl_is_a_miss(tmp_path):
    """A cached price presented as current is worse than no price, because
    somebody quotes it."""
    cache = LookupCache(path=tmp_path / "c.json", ttl_hours=12)
    cache.put("mouser", "BME280", _cached_lookup(), now=NOW)
    assert cache.get("mouser", "BME280", now=NOW + timedelta(hours=11))
    assert cache.get("mouser", "BME280", now=NOW + timedelta(hours=13)) is None


def test_a_result_that_was_never_obtained_is_never_stored(tmp_path):
    """Caching a NOT_CHECKED would turn one missing API key into twelve hours
    of a report insisting nothing could be checked, long after the key was
    set."""
    cache = LookupCache(path=tmp_path / "c.json")
    cache.put("mouser", "X",
              Lookup(query="X", outcome=Outcome.NOT_CHECKED, reason="no key"),
              now=NOW)
    assert cache.get("mouser", "X", now=NOW) is None


def test_a_corrupt_cache_is_a_miss_rather_than_a_crash(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert LookupCache(path=path).get("mouser", "BME280", now=NOW) is None


def test_the_cache_is_case_insensitive_on_part_numbers(tmp_path):
    cache = LookupCache(path=tmp_path / "c.json")
    cache.put("mouser", "bme280", _cached_lookup(), now=NOW)
    assert cache.get("mouser", "BME280", now=NOW) is not None


def test_a_disabled_cache_never_answers(tmp_path):
    cache = LookupCache(path=tmp_path / "c.json", enabled=False)
    cache.put("mouser", "BME280", _cached_lookup(), now=NOW)
    assert cache.get("mouser", "BME280", now=NOW) is None


# --------------------------------------------------------------------
# Mouser
# --------------------------------------------------------------------

MOUSER_PART = {
    "ManufacturerPartNumber": "GRM188R71H104KA93D",
    "Manufacturer": "Murata Electronics",
    "Description": "Multilayer Ceramic Capacitors MLCC 100nF 50V X7R 0603",
    "MouserPartNumber": "81-GRM188R71H104KA93D",
    "ProductDetailUrl": "https://www.mouser.com/ProductDetail/81-GRM188R71H104KA93D",
    "DataSheetUrl": "https://example.com/ds.pdf",
    "LifecycleStatus": "Active",
    "Availability": "220000 In Stock",
    "AvailabilityInStock": "220000",
    "Min": "1",
    "Mult": "1",
    "LeadTime": "42 Days",
    "Packaging": "Cut Tape",
    "PriceBreaks": [
        {"Quantity": 1, "Price": "$0.22", "Currency": "USD"},
        {"Quantity": 100, "Price": "$0.11", "Currency": "USD"},
        {"Quantity": 1000, "Price": "$0.055", "Currency": "USD"},
    ],
}


def _mouser_payload(parts, errors=()):
    return {"Errors": list(errors),
            "SearchResults": {"NumberOfResult": len(parts), "Parts": list(parts)}}


def _mouser(payload, key="secret-key-do-not-print", sleep=None, **kw):
    return MouserDistributor(environment={"MOUSER_API_KEY": key},
                             opener=_opener(payload),
                             sleep=sleep or (lambda s: None),
                             now=lambda: NOW, **kw)


def test_mouser_parses_a_part_into_the_shared_shape():
    result = _mouser(_mouser_payload([MOUSER_PART])).lookup("GRM188R71H104KA93D")
    assert result.outcome is Outcome.MATCHED
    record = result.record
    assert record.manufacturer == "Murata Electronics"
    assert record.lifecycle is Lifecycle.ACTIVE
    offer = record.best_offer
    assert offer.stock == 220000
    assert offer.unit_price_at(100) == Decimal("0.11")
    assert offer.lead_time_days == 42
    assert offer.distributor_part_number == "81-GRM188R71H104KA93D"


def test_mouser_returning_a_different_part_is_candidates_never_a_match():
    """The suffix trap. Mouser answering with TPS61023DRLR when asked for
    TPS61023DRLT is not a match, and treating it as one would swap a reel for
    a tape on somebody's production order."""
    other = dict(MOUSER_PART, ManufacturerPartNumber="TPS61023DRLR")
    result = _mouser(_mouser_payload([other])).lookup("TPS61023DRLT")
    assert result.outcome is Outcome.CANDIDATES
    assert result.record is None
    assert result.candidates[0].manufacturer_part_number == "TPS61023DRLR"


def test_mouser_with_no_results_is_not_found():
    result = _mouser(_mouser_payload([])).lookup("NOSUCHPART")
    assert result.outcome is Outcome.NOT_FOUND


def test_mouser_reporting_an_error_is_not_checked_not_not_found():
    """An API complaining about the request has told us nothing about the part.
    Recording that as "not found" would put a critical finding on a BOM line
    that is perfectly fine."""
    payload = _mouser_payload([], errors=[{"Message": "Invalid API key"}])
    result = _mouser(payload).lookup("BME280")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "Invalid API key" in result.reason


def test_mouser_without_a_key_says_so_and_names_the_variable():
    distributor = MouserDistributor(environment={}, opener=_opener({}))
    result = distributor.lookup("BME280")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "MOUSER_API_KEY" in result.reason
    assert distributor.usable()[0] is False


def test_an_http_failure_never_repeats_the_key():
    """The URL carries the key in the query string, and an error message is the
    most likely thing in this program to be pasted into a bug report."""
    import urllib.error

    def boom(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    distributor = MouserDistributor(environment={"MOUSER_API_KEY": "SECRET123"},
                                    opener=boom, sleep=lambda s: None)
    result = distributor.lookup("BME280")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "403" in result.reason
    assert "SECRET123" not in result.reason


def test_mouser_waits_between_calls():
    """Thirty a minute is one every two seconds. There is no version of this
    that goes faster, and pretending otherwise gets a key revoked."""
    slept = []
    distributor = _mouser(_mouser_payload([MOUSER_PART]), sleep=slept.append)
    distributor.lookup("GRM188R71H104KA93D")
    distributor.lookup("GRM188R71H104KA93D")
    assert slept and slept[0] > 1.0


def test_mouser_declares_its_limits_and_its_unverified_state():
    capabilities = MouserDistributor(environment={}).capabilities
    assert capabilities.rate_limit_per_minute == 30
    assert capabilities.rate_limit_per_day == 1000
    assert capabilities.terms_url.startswith("https://")


# --------------------------------------------------------------------
# Digi-Key
# --------------------------------------------------------------------

DIGIKEY_PRODUCT = {
    "ManufacturerProductNumber": "GRM188R71H104KA93D",
    "Manufacturer": {"Id": 10, "Name": "Murata Electronics"},
    "Description": {"ProductDescription": "CAP CER 0.1UF 50V X7R 0603"},
    "ProductStatus": {"Id": 0, "Name": "Active"},
    "DatasheetUrl": "https://example.com/ds.pdf",
    "ProductUrl": "https://www.digikey.com/en/products/detail/x",
    "QuantityAvailable": 190000,
    "ManufacturerLeadWeeks": "8",
    "ProductVariations": [{
        "DigiKeyProductNumber": "490-1234-1-ND",
        "PackageType": {"Id": 2, "Name": "Cut Tape (CT)"},
        "MinimumOrderQuantity": 1,
        "StandardPackage": 1,
        "StandardPricing": [
            {"BreakQuantity": 1, "UnitPrice": 0.23},
            {"BreakQuantity": 100, "UnitPrice": 0.12},
        ],
    }],
}

DIGIKEY_ENV = {"DIGIKEY_CLIENT_ID": "cid", "DIGIKEY_CLIENT_SECRET": "shh"}


def _digikey_opener(product_payload, token_payload=None, captured=None):
    token_payload = token_payload or {"access_token": "tok", "expires_in": 600,
                                      "token_type": "Bearer"}
    captured = captured if captured is not None else []

    def open_it(request, timeout=0):
        captured.append(request)
        if "oauth2/token" in request.full_url:
            return _Response(token_payload)
        return _Response(product_payload)
    open_it.captured = captured
    return open_it


def test_digikey_unwraps_the_v4_named_fields():
    """v4 sends {"Id": n, "Name": "..."} where v3 sent a string. Reading those
    as strings gives every part a manufacturer of "{'Id': 10, ...}"."""
    opener = _digikey_opener({"Products": [DIGIKEY_PRODUCT]})
    distributor = DigiKeyDistributor(environment=dict(DIGIKEY_ENV), opener=opener,
                                     now=lambda: NOW)
    result = distributor.lookup("GRM188R71H104KA93D")
    assert result.outcome is Outcome.MATCHED
    assert result.record.manufacturer == "Murata Electronics"
    assert result.record.description.startswith("CAP CER")
    assert result.record.lifecycle is Lifecycle.ACTIVE
    offer = result.record.best_offer
    assert offer.stock == 190000
    assert offer.unit_price_at(100) == Decimal("0.12")
    assert offer.lead_time_days == 56
    assert offer.distributor_part_number == "490-1234-1-ND"


def test_digikey_sends_the_client_id_header_as_well_as_the_token():
    """Sending the bearer token without X-DIGIKEY-Client-Id is rejected, and
    it is a mistake worth making only once."""
    captured = []
    opener = _digikey_opener({"Products": [DIGIKEY_PRODUCT]}, captured=captured)
    DigiKeyDistributor(environment=dict(DIGIKEY_ENV), opener=opener).lookup("X")
    search = [r for r in captured if "oauth2" not in r.full_url][0]
    assert search.headers["Authorization"] == "Bearer tok"
    assert search.headers["X-digikey-client-id"] == "cid"


def test_digikey_reuses_a_token_until_it_is_nearly_expired():
    """Ten minutes is short enough that a long BOM crosses the boundary, so the
    token is renewed a little early rather than after a request has failed."""
    captured, clock = [], [0.0]
    opener = _digikey_opener({"Products": [DIGIKEY_PRODUCT]}, captured=captured)
    distributor = DigiKeyDistributor(environment=dict(DIGIKEY_ENV), opener=opener,
                                     monotonic=lambda: clock[0])
    distributor.lookup("X")
    distributor.lookup("X")
    assert sum("oauth2" in r.full_url for r in captured) == 1

    clock[0] = 600.0                       # past the ten-minute lifetime
    distributor.lookup("X")
    assert sum("oauth2" in r.full_url for r in captured) == 2


def test_bad_digikey_credentials_say_which_variables_to_check():
    import urllib.error

    def open_it(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    result = DigiKeyDistributor(environment=dict(DIGIKEY_ENV),
                                opener=open_it).lookup("X")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "DIGIKEY_CLIENT_ID" in result.reason
    assert "shh" not in result.reason


def test_digikey_without_credentials_names_both_variables():
    result = DigiKeyDistributor(environment={}, opener=_digikey_opener({})).lookup("X")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "DIGIKEY_CLIENT_ID" in result.reason
    assert "DIGIKEY_CLIENT_SECRET" in result.reason


def test_the_sandbox_flag_moves_every_request_off_production():
    captured = []
    opener = _digikey_opener({"Products": []}, captured=captured)
    environment = dict(DIGIKEY_ENV, DIGIKEY_SANDBOX="1")
    DigiKeyDistributor(environment=environment, opener=opener).lookup("X")
    assert captured and all("sandbox-api.digikey.com" in r.full_url for r in captured)


# --------------------------------------------------------------------
# What has and has not been proven
# --------------------------------------------------------------------

@pytest.mark.parametrize("build", [
    lambda: MouserDistributor(environment={}),
    lambda: DigiKeyDistributor(environment={}),
])
def test_an_unverified_adapter_admits_it_is_unverified(build):
    """These adapters have never spoken to the live service from this project.
    The flag is what the report prints, and it must stay False until somebody
    runs `helix-bom enrich --check-key` with a real key and says it worked.

    If you are changing this to True: only do it because that happened."""
    capabilities = build().capabilities
    assert capabilities.verified_against_live_api is False
    assert capabilities.live is True


def test_the_offline_distributor_declares_itself_not_live():
    capabilities = OfflineDistributor().capabilities
    assert capabilities.live is False
    assert "not from any distributor" in capabilities.notes


def test_the_offline_catalogue_never_claims_a_part_does_not_exist():
    """It knows six parts. "No distributor has this" is a claim six invented
    parts cannot support -- and before this was fixed, a real BOM run against
    it produced nine CRITICAL findings against parts every distributor stocks."""
    result = OfflineDistributor().lookup("STM32F401RET6")
    assert result.outcome is Outcome.NOT_CHECKED
    assert "six parts" in result.reason


def test_no_distributor_has_a_way_to_spend_money():
    """This layer answers questions about parts. Buying them is a person's
    decision made on a distributor's own site, and a method that does not exist
    cannot be called by mistake or reached by an agent improvising."""
    forbidden = {"order", "buy", "purchase", "cart", "addtocart", "checkout",
                 "submitorder", "pay"}
    for cls in (MouserDistributor, DigiKeyDistributor, OfflineDistributor):
        for name in dir(cls):
            assert name.lower().replace("_", "") not in forbidden, \
                f"{cls.__name__} grew {name}()"
