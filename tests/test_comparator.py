from datetime import date


from sunclass.comparator import match_reservations
from sunclass.models import Reservation, DiscrepancyKind


def _ical(uid, ci, co):
    """Create an iCal-style reservation (no guest name)."""
    return Reservation(
        source="ical_bookingcom",
        external_uid=uid,
        check_in=ci,
        check_out=co,
        guest_name=None,
        property_label=None,
    )


def _sunclass(uid, ci, co, name="Jan Janssen"):
    """Create a Sunclass-style reservation (has guest name)."""
    return Reservation(
        source="sunclass",
        external_uid=uid,
        check_in=ci,
        check_out=co,
        guest_name=name,
        property_label=None,
    )


class TestMatchReservations:
    def test_exact_match_no_discrepancy(self):
        ci, co = date(2026, 6, 15), date(2026, 6, 20)
        result = match_reservations([_ical("u1", ci, co)], [_sunclass("s1", ci, co)])
        assert result == []

    def test_only_in_ical(self):
        ci, co = date(2026, 6, 15), date(2026, 6, 20)
        result = match_reservations([_ical("u1", ci, co)], [])
        assert len(result) == 1
        assert result[0].kind == DiscrepancyKind.ONLY_IN_ICAL
        assert "ical_bookingcom" in result[0].detail

    def test_only_in_scrape(self):
        ci, co = date(2026, 6, 15), date(2026, 6, 20)
        result = match_reservations([], [_sunclass("s1", ci, co, "Marie Dupont")])
        assert len(result) == 1
        assert result[0].kind == DiscrepancyKind.ONLY_IN_SCRAPE
        assert "Marie Dupont" in result[0].detail

    def test_overlapping_date_mismatch(self):
        # iCal says 15-20, Sunclass says 15-21 (overlap but different checkout)
        ical = [_ical("u1", date(2026, 6, 15), date(2026, 6, 20))]
        scraped = [_sunclass("s1", date(2026, 6, 15), date(2026, 6, 21))]
        result = match_reservations(ical, scraped)
        assert len(result) == 1
        assert result[0].kind == DiscrepancyKind.DATE_MISMATCH

    def test_fuzzy_within_tolerance(self):
        # iCal 1-7, Sunclass 2-7 — ±1 day tolerance should fuzzy-match
        ical = [_ical("u1", date(2026, 7, 1), date(2026, 7, 7))]
        scraped = [_sunclass("s1", date(2026, 7, 2), date(2026, 7, 7))]
        result = match_reservations(ical, scraped, date_tolerance_days=1)
        assert len(result) == 1
        assert result[0].kind == DiscrepancyKind.SUSPICIOUS_MATCH

    def test_multiple_clean_matches(self):
        ical = [
            _ical("u1", date(2026, 6, 15), date(2026, 6, 20)),
            _ical("u2", date(2026, 7, 1), date(2026, 7, 7)),
        ]
        scraped = [
            _sunclass("s1", date(2026, 6, 15), date(2026, 6, 20), "Anna Bauer"),
            _sunclass("s2", date(2026, 7, 1), date(2026, 7, 7), "Luc Martin"),
        ]
        result = match_reservations(ical, scraped)
        assert result == []

    def test_no_false_positive_on_adjacent_ranges(self):
        # Non-overlapping adjacent ranges should not trigger DATE_MISMATCH
        ical = [_ical("u1", date(2026, 6, 15), date(2026, 6, 20))]
        scraped = [_sunclass("s1", date(2026, 6, 20), date(2026, 6, 25))]
        result = match_reservations(ical, scraped)
        # Both should show as unmatched (ONLY_IN_ICAL + ONLY_IN_SCRAPE), not DATE_MISMATCH
        kinds = {d.kind for d in result}
        assert DiscrepancyKind.DATE_MISMATCH not in kinds
        assert DiscrepancyKind.ONLY_IN_ICAL in kinds
        assert DiscrepancyKind.ONLY_IN_SCRAPE in kinds
