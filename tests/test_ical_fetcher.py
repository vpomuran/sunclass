from pathlib import Path
from unittest.mock import patch

import pytest

from sunclass.fetchers.ical import ICalFetcher
from sunclass.fetchers.base import FetchError


def _make_settings():
    from unittest.mock import MagicMock
    s = MagicMock()
    s.ical_fetch_timeout_seconds = 30
    s.canonical_tz = "Europe/Brussels"
    s.property_label = None
    return s


FIXTURE_ICS = (Path(__file__).parent / "fixtures" / "sample.ics").read_bytes()


def _fetcher(source="ical_bookingcom"):
    return ICalFetcher(
        url="https://example.com/cal.ics",
        source=source,
        label="Test Feed",
        settings=_make_settings(),
    )


class TestICalFetcher:
    def test_parses_fixture_count(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.content = FIXTURE_ICS
            mock_get.return_value.raise_for_status = lambda: None
            reservations = _fetcher().fetch()

        assert len(reservations) == 3

    def test_guest_name_is_none(self):
        """iCal feeds never carry guest names."""
        with patch("requests.get") as mock_get:
            mock_get.return_value.content = FIXTURE_ICS
            mock_get.return_value.raise_for_status = lambda: None
            reservations = _fetcher().fetch()

        assert all(r.guest_name is None for r in reservations)

    def test_dates_parsed_correctly(self):
        from datetime import date

        with patch("requests.get") as mock_get:
            mock_get.return_value.content = FIXTURE_ICS
            mock_get.return_value.raise_for_status = lambda: None
            reservations = _fetcher().fetch()

        dates = {(r.check_in, r.check_out) for r in reservations}
        assert (date(2026, 6, 15), date(2026, 6, 20)) in dates
        assert (date(2026, 7, 1), date(2026, 7, 7)) in dates
        assert (date(2026, 8, 1), date(2026, 8, 8)) in dates

    def test_raises_fetch_error_on_http_failure(self):
        import requests

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("timeout")
            with pytest.raises(FetchError):
                _fetcher().fetch()

    def test_source_name_set_correctly(self):
        f = _fetcher(source="ical_airbnb")
        assert f.source_name == "ical_airbnb"
