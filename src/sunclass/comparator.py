from __future__ import annotations

from datetime import date

from .models import Discrepancy, DiscrepancyKind, Reservation


def _overlaps(a_in: date, a_out: date, b_in: date, b_out: date) -> bool:
    """True if two date ranges overlap (exclusive end date convention)."""
    return a_in < b_out and b_in < a_out


def _date_range_close(
    a_in: date, a_out: date, b_in: date, b_out: date, tolerance: int
) -> bool:
    return (
        abs((a_in - b_in).days) <= tolerance
        and abs((a_out - b_out).days) <= tolerance
    )


def match_reservations(
    ical_reservations: list[Reservation],
    scraped_reservations: list[Reservation],
    date_tolerance_days: int = 0,
) -> list[Discrepancy]:
    """
    Compare blocked date ranges from iCal feeds against Sunclass reservations.

    iCal feeds only expose blocked intervals (no guest names), so matching is
    purely date-range based.

    Returns a list of Discrepancy objects for every mismatch found.
    """
    discrepancies: list[Discrepancy] = []

    ical_index: dict[tuple[date, date], Reservation] = {
        r.canonical_key: r for r in ical_reservations
    }
    scrape_index: dict[tuple[date, date], Reservation] = {
        r.canonical_key: r for r in scraped_reservations
    }

    matched_ical: set[tuple[date, date]] = set()
    matched_scrape: set[tuple[date, date]] = set()

    # Step 1 — exact date-range match
    for key in ical_index.keys() & scrape_index.keys():
        matched_ical.add(key)
        matched_scrape.add(key)
        # Exact match: dates agree, no discrepancy

    unmatched_ical = [r for k, r in ical_index.items() if k not in matched_ical]
    unmatched_scrape = [r for k, r in scrape_index.items() if k not in matched_scrape]

    # Step 2 — fuzzy date window for unmatched pairs
    if date_tolerance_days > 0:
        still_unmatched_ical = []
        fuzzy_matched_scrape: set[tuple[date, date]] = set()

        for ir in unmatched_ical:
            candidate = None
            for sr in unmatched_scrape:
                if sr.canonical_key in fuzzy_matched_scrape:
                    continue
                if _date_range_close(
                    ir.check_in, ir.check_out,
                    sr.check_in, sr.check_out,
                    date_tolerance_days,
                ):
                    candidate = sr
                    break

            if candidate:
                fuzzy_matched_scrape.add(candidate.canonical_key)
                guest = candidate.guest_name or "unknown"
                discrepancies.append(
                    Discrepancy(
                        kind=DiscrepancyKind.SUSPICIOUS_MATCH,
                        reservations=[ir, candidate],
                        detail=(
                            f"Fuzzy date match — iCal {ir.check_in}→{ir.check_out} "
                            f"vs Sunclass '{guest}' {candidate.check_in}→{candidate.check_out} "
                            f"(within ±{date_tolerance_days}d) — needs review"
                        ),
                    )
                )
            else:
                still_unmatched_ical.append(ir)

        unmatched_scrape = [
            r for r in unmatched_scrape if r.canonical_key not in fuzzy_matched_scrape
        ]
        unmatched_ical = still_unmatched_ical

    # Step 3 — remaining unmatched: check for overlapping ranges (partial mismatch)
    still_unmatched_ical_2 = []
    for ir in unmatched_ical:
        overlap_candidates = [
            sr for sr in unmatched_scrape
            if _overlaps(ir.check_in, ir.check_out, sr.check_in, sr.check_out)
            and sr.canonical_key not in matched_scrape
        ]
        if overlap_candidates:
            for sr in overlap_candidates:
                matched_scrape.add(sr.canonical_key)
                guest = sr.guest_name or "unknown"
                discrepancies.append(
                    Discrepancy(
                        kind=DiscrepancyKind.DATE_MISMATCH,
                        reservations=[ir, sr],
                        detail=(
                            f"Overlapping but mismatched dates — "
                            f"iCal {ir.check_in}→{ir.check_out} vs "
                            f"Sunclass '{guest}' {sr.check_in}→{sr.check_out}"
                        ),
                    )
                )
            matched_ical.add(ir.canonical_key)
        else:
            still_unmatched_ical_2.append(ir)

    unmatched_scrape = [r for r in unmatched_scrape if r.canonical_key not in matched_scrape]
    unmatched_ical = still_unmatched_ical_2

    # Step 4 — truly unmatched
    for r in unmatched_ical:
        discrepancies.append(
            Discrepancy(
                kind=DiscrepancyKind.ONLY_IN_ICAL,
                reservations=[r],
                detail=(
                    f"Date range {r.check_in}→{r.check_out} blocked in {r.source} "
                    f"but no matching reservation in Sunclass"
                ),
            )
        )

    for r in unmatched_scrape:
        guest = r.guest_name or "unknown"
        discrepancies.append(
            Discrepancy(
                kind=DiscrepancyKind.ONLY_IN_SCRAPE,
                reservations=[r],
                detail=(
                    f"Sunclass reservation '{guest}' {r.check_in}→{r.check_out} "
                    f"not blocked in any iCal feed"
                ),
            )
        )

    return discrepancies
