"""
Tests for SunclassScraper._parse_row using real HTML from the live portal.
We test the parsing logic directly without Playwright by building a minimal
stub that mimics the Playwright element API.
"""
from datetime import date
from unittest.mock import MagicMock


def _make_cell(text: str, link_href: str | None = None) -> MagicMock:
    cell = MagicMock()
    cell.inner_text.return_value = text
    if link_href is not None:
        link = MagicMock()
        link.get_attribute.return_value = link_href
        cell.query_selector.return_value = link
    else:
        cell.query_selector.return_value = None
    return cell


def _make_row(cells: list[MagicMock]) -> MagicMock:
    row = MagicMock()
    row.query_selector_all.return_value = cells
    return row


def _make_settings():
    s = MagicMock()
    s.sunclass_email = "test@example.com"
    s.sunclass_password = "secret"
    s.sunclass_url = "https://mijn.sunclassdurbuy.com/reservations"
    s.scraper_timeout_ms = 30000
    s.property_label = None
    return s


def _make_scraper():
    from sunclass.fetchers.sunclass import SunclassScraper
    return SunclassScraper(_make_settings())


def _row_cells(href, reservation_num, obj, name, city, arrival, departure):
    """Build a 9-cell row matching the confirmed column layout."""
    return [
        _make_cell(reservation_num, link_href=href),  # col 0: reservation number + link
        _make_cell(obj),                              # col 1: object
        _make_cell(name),                             # col 2: guest name
        _make_cell(city),                             # col 3: city
        _make_cell(arrival),                          # col 4: arrival date
        _make_cell(departure),                        # col 5: departure date
        _make_cell("€ 0,00"),                         # col 6: revenue
        _make_cell(""),                               # col 7: notes
        _make_cell("Ja"),                             # col 8: owner-introduced
    ]


class TestParseRow:
    def test_normal_reservation(self):
        scraper = _make_scraper()
        cells = _row_cells(
            href="/reservations/26553821",
            reservation_num="126003737",
            obj="Chalet 102 (NL1231669)",
            name="Renson, Julie",
            city="Bruxelles",
            arrival="23-05-2026",
            departure="25-05-2026",
        )
        r = scraper._parse_row(_make_row(cells))
        assert r is not None
        assert r.check_in == date(2026, 5, 23)
        assert r.check_out == date(2026, 5, 25)
        assert r.guest_name == "Renson, Julie"
        assert r.external_uid == "reservations_26553821"
        assert r.source == "sunclass"

    def test_owner_booking_strips_prefix(self):
        scraper = _make_scraper()
        cells = _row_cells(
            href="/booking/26493770",
            reservation_num="126003521",
            obj="Chalet 102 (NL1231669)",
            name="(EIG102)Pomuran, V.M",
            city="Amsterdam",
            arrival="27-03-2026",
            departure="28-03-2026",
        )
        r = scraper._parse_row(_make_row(cells))
        assert r is not None
        assert r.guest_name == "Pomuran, V.M"
        assert r.external_uid == "booking_26493770"

    def test_nbsp_in_name_stripped(self):
        scraper = _make_scraper()
        cells = _row_cells(
            href="/reservations/25723080",
            reservation_num="126000333",
            obj="Chalet 102",
            name="\xa0VanderZee Haak, Marianne",  # &nbsp; prefix
            city="Zwolle",
            arrival="02-01-2026",
            departure="04-01-2026",
        )
        r = scraper._parse_row(_make_row(cells))
        assert r is not None
        assert r.guest_name == "VanderZee Haak, Marianne"

    def test_skips_row_with_too_few_cells(self):
        scraper = _make_scraper()
        row = _make_row([_make_cell("only one cell")])
        assert scraper._parse_row(row) is None

    def test_skips_row_with_empty_name(self):
        scraper = _make_scraper()
        cells = _row_cells(
            href="/reservations/99",
            reservation_num="999",
            obj="Chalet 102",
            name="",
            city="",
            arrival="01-06-2026",
            departure="05-06-2026",
        )
        assert scraper._parse_row(_make_row(cells)) is None

    def test_accent_in_name_preserved(self):
        scraper = _make_scraper()
        cells = _row_cells(
            href="/reservations/24295527",
            reservation_num="125003170",
            obj="Chalet 102",
            name="Esprit, Aurélie",
            city="Saint Pol De Leon",
            arrival="19-10-2025",
            departure="26-10-2025",
        )
        r = scraper._parse_row(_make_row(cells))
        assert r is not None
        assert r.guest_name == "Esprit, Aurélie"
        assert r.check_in == date(2025, 10, 19)
        assert r.check_out == date(2025, 10, 26)
