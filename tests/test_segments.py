"""Tests for the segment building logic."""
import pytest

from precutter import segments


def test_invert_silences_middle():
    silences = [(2.0, 4.0)]
    keep = segments.invert_to_keep(silences, 10.0)
    assert keep == [(0.0, 2.0), (4.0, 10.0)]


def test_invert_leading_and_trailing():
    silences = [(0.0, 1.0), (8.0, 10.0)]
    keep = segments.invert_to_keep(silences, 10.0)
    assert keep == [(1.0, 8.0)]


def test_apply_padding_clamps():
    padded = segments.apply_padding([(1.0, 3.0)], 0.5, 0.5, 10.0)
    assert padded == [(0.5, 3.5)]
    padded_edge = segments.apply_padding([(0.2, 9.9)], 0.5, 0.5, 10.0)
    assert padded_edge == [(0.0, 10.0)]


def test_apply_padding_asymmetric():
    padded = segments.apply_padding([(1.0, 3.0)], 0.2, 0.5, 10.0)
    assert padded == [(0.8, 3.5)]


def test_merge_overlaps():
    merged = segments.merge_segments([(0.0, 2.0), (1.5, 4.0), (6.0, 7.0)])
    assert merged == [(0.0, 4.0), (6.0, 7.0)]


def test_merge_touching():
    merged = segments.merge_segments([(0.0, 2.0), (2.0, 3.0)])
    assert merged == [(0.0, 3.0)]


def test_filter_short():
    filtered = segments.filter_short([(0.0, 0.05), (0.0, 0.2)], 0.1)
    assert filtered == [(0.0, 0.2)]


def test_build_segments_pipeline():
    silences = [(1.0, 2.0), (4.0, 4.5)]
    keep = segments.build_segments(silences, 6.0, padding_pre=0.1,
                                    padding_post=0.1, merge_gap=0.0)
    assert keep == [(0.0, 1.1), (1.9, 4.1), (4.4, 6.0)]


def test_build_segments_padding_merges():
    silences = [(1.0, 1.2)]
    keep = segments.build_segments(silences, 3.0, padding_pre=0.2,
                                    padding_post=0.2)
    assert keep == [(0.0, 3.0)]


def test_build_segments_merge_close_and_min_keep():
    # 0.2 s gap merges with merge_gap=0.3.
    keep = segments.build_segments([(1.0, 1.2), (2.0, 5.0)], 6.0,
                                    padding_pre=0.0, padding_post=0.0,
                                    min_keep=0.1, merge_gap=0.3)
    assert keep == [(0.0, 2.0), (5.0, 6.0)]
    # A 0.3 s piece is dropped by min_keep=0.4.
    keep = segments.build_segments([(0.5, 5.7)], 6.0,
                                    padding_pre=0.0, padding_post=0.0,
                                    min_keep=0.4, merge_gap=0.0)
    assert keep == [(0.0, 0.5)]


def test_summarize():
    summary = segments.summarize(10.0, [(0.0, 3.0), (5.0, 8.0)])
    assert summary["original_duration"] == 10.0
    assert summary["new_duration"] == 6.0
    assert summary["saved_seconds"] == 4.0
    assert summary["saved_percent"] == 40.0
    assert summary["cut_count"] == 2
    assert summary["segment_count"] == 2


def test_summarize_no_cuts():
    summary = segments.summarize(10.0, [(0.0, 10.0)])
    assert summary["saved_seconds"] == 0.0
    assert summary["cut_count"] == 0


def test_build_segments_empty_silences():
    keep = segments.build_segments([], 5.0, padding_pre=0.0, padding_post=0.0)
    assert keep == [(0.0, 5.0)]


def test_subtract_segments_middle():
    keep = [(0.0, 10.0)]
    assert segments.subtract_segments(keep, [(2.0, 4.0), (6.0, 8.0)]) == [
        (0.0, 2.0), (4.0, 6.0), (8.0, 10.0)]


def test_subtract_segments_edges_and_overlap():
    keep = [(0.0, 5.0), (6.0, 10.0)]
    assert segments.subtract_segments(keep, [(4.0, 7.0)]) == [(0.0, 4.0), (7.0, 10.0)]
    assert segments.subtract_segments(keep, []) == keep
    assert segments.subtract_segments(keep, [(0.0, 10.0)]) == []


def test_snap_to_frames():
    snapped = segments.snap_to_frames([(0.011, 0.37), (1.0, 1.5)], 30.0, 10.0)
    assert len(snapped) == 2
    assert snapped[0][0] == pytest.approx(0.0, abs=1e-9)
    assert snapped[0][1] == pytest.approx(11 / 30, abs=1e-9)
    assert snapped[1] == pytest.approx((1.0, 1.5))
    for start, end in snapped:
        assert abs(start * 30 - round(start * 30)) < 1e-6
        assert abs(end * 30 - round(end * 30)) < 1e-6


def test_snap_to_frames_clamps_and_drops():
    snapped = segments.snap_to_frames([(-0.5, 0.2), (9.9, 12.0)], 30.0, 10.0)
    assert snapped[0][0] == pytest.approx(0.0, abs=1e-9)
    assert snapped[0][1] == pytest.approx(0.2, abs=1e-9)
    assert snapped[-1][0] == pytest.approx(9.9, abs=1e-9)
    assert snapped[-1][1] == pytest.approx(10.0, abs=1e-9)
    assert segments.snap_to_frames([(1.0, 2.0)], 0.0, 10.0) == [(1.0, 2.0)]