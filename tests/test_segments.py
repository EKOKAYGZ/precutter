"""Tests for the segment building logic."""
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
    padded = segments.apply_padding([(1.0, 3.0)], 0.5, 10.0)
    assert padded == [(0.5, 3.5)]
    padded_edge = segments.apply_padding([(0.2, 9.9)], 0.5, 10.0)
    assert padded_edge == [(0.0, 10.0)]


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
    keep = segments.build_segments(silences, 6.0, padding=0.1)
    assert keep == [(0.0, 1.1), (1.9, 4.1), (4.4, 6.0)]


def test_build_segments_padding_merges():
    silences = [(1.0, 1.2)]
    keep = segments.build_segments(silences, 3.0, padding=0.2)
    assert keep == [(0.0, 3.0)]


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
    keep = segments.build_segments([], 5.0, padding=0.0)
    assert keep == [(0.0, 5.0)]