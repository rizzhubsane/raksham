"""Output rows, ranks, and the run summary."""

from deckeval.constants import RANK, STATUS, STATUS_DOWNLOAD_FAILED, STATUS_SCORED, TOTAL
from deckeval.report import apply_output_ranks, distribution


def test_output_ranks_share_ties_and_leave_failures_blank():
    rows = [
        {STATUS: STATUS_SCORED, TOTAL: "9.0"},
        {STATUS: STATUS_SCORED, TOTAL: "8.5"},
        {STATUS: STATUS_SCORED, TOTAL: "8.5"},
        {STATUS: STATUS_SCORED, TOTAL: "7.0"},
        {STATUS: STATUS_DOWNLOAD_FAILED, TOTAL: ""},
    ]
    apply_output_ranks(rows)
    assert [row[RANK] for row in rows] == ["1", "2", "2", "4", ""]


def test_score_distribution_bins():
    assert dict(distribution([0.0, 1.9, 2.0, 8.0, 10.0])) == {
        "[0,2)": 2,
        "[2,4)": 1,
        "[4,6)": 0,
        "[6,8)": 0,
        "[8,10]": 2,
    }
