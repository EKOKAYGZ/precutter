"""Build keep-segments from detected silences and compute a summary."""
from typing import Dict, List, Tuple

from . import config

Segment = Tuple[float, float]

_EPS = 1e-6


def invert_to_keep(silences: List[Segment], duration: float) -> List[Segment]:
    """Invert silence intervals into keep-segments covering [0, duration]."""
    keep: List[Segment] = []
    cursor = 0.0
    for start, end in sorted(silences, key=lambda s: s[0]):
        start = max(start, 0.0)
        end = min(end, duration)
        if start - cursor > _EPS:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor > _EPS:
        keep.append((cursor, duration))
    return keep


def apply_padding(segments: List[Segment], padding: float, duration: float) -> List[Segment]:
    """Expand each keep-segment by padding seconds, clamped to [0, duration]."""
    padded: List[Segment] = []
    for start, end in segments:
        new_start = max(0.0, start - padding)
        new_end = min(duration, end + padding)
        if new_end - new_start > _EPS:
            padded.append((new_start, new_end))
    return padded


def merge_segments(segments: List[Segment]) -> List[Segment]:
    """Merge overlapping or touching segments."""
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: s[0])
    merged: List[Segment] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + _EPS:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def filter_short(segments: List[Segment], min_duration: float = config.MIN_SEGMENT_DURATION) -> List[Segment]:
    """Drop segments shorter than min_duration."""
    return [(s, e) for s, e in segments if e - s >= min_duration - _EPS]


def build_segments(
    silences: List[Segment],
    duration: float,
    padding: float = config.PADDING,
) -> List[Segment]:
    """Full pipeline: invert -> pad -> merge -> drop tiny segments."""
    keep = invert_to_keep(silences, duration)
    padded = apply_padding(keep, padding, duration)
    merged = merge_segments(padded)
    return filter_short(merged)


def _removed_regions(segments: List[Segment], duration: float) -> List[Segment]:
    """Complement of kept segments within [0, duration]."""
    removed: List[Segment] = []
    cursor = 0.0
    for start, end in segments:
        if start - cursor > _EPS:
            removed.append((cursor, start))
        cursor = max(cursor, end)
    if duration - cursor > _EPS:
        removed.append((cursor, duration))
    return removed


def summarize(original: float, segments: List[Segment]) -> Dict[str, float]:
    """Compute duration statistics for the kept segments."""
    new_duration = sum(end - start for start, end in segments)
    saved = max(0.0, original - new_duration)
    percent = (saved / original * 100.0) if original > _EPS else 0.0
    cut_count = len(_removed_regions(segments, original))
    return {
        "original_duration": round(original, 3),
        "new_duration": round(new_duration, 3),
        "saved_seconds": round(saved, 3),
        "saved_percent": round(percent, 2),
        "cut_count": cut_count,
        "segment_count": len(segments),
    }