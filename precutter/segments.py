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


def apply_padding(
    segments: List[Segment], pad_pre: float, pad_post: float, duration: float
) -> List[Segment]:
    """Expand each keep-segment by pre/post padding, clamped to [0, duration]."""
    padded: List[Segment] = []
    for start, end in segments:
        new_start = max(0.0, start - pad_pre)
        new_end = min(duration, end + pad_post)
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


def snap_to_frames(segments: List[Segment], fps: float, duration: float) -> List[Segment]:
    """Round each segment bound to the nearest video frame boundary.

    Video can only start/end on whole frames; unaligned bounds make the
    encoder snap lengths (e.g. 0.37 s -> 0.4 s) while audio stays exact,
    drifting the total. Snapping first keeps every part an exact frame
    count, so video and audio lengths agree sample-for-sample.
    """
    if fps <= 0:
        return list(segments)
    snapped = []
    for start, end in segments:
        s = min(max(round(start * fps) / fps, 0.0), duration)
        e = min(max(round(end * fps) / fps, 0.0), duration)
        if e - s > _EPS:
            snapped.append((s, e))
    return filter_short(merge_segments(snapped))


def subtract_segments(keep: List[Segment], cut: List[Segment]) -> List[Segment]:
    """Remove `cut` ranges (e.g. filler words) from keep-segments."""
    result: List[Segment] = []
    for ks, ke in sorted(keep):
        cursor = ks
        for cs, ce in sorted(cut):
            if ce <= cursor or cs >= ke:
                continue
            if cs > cursor:
                result.append((cursor, min(cs, ke)))
            cursor = max(cursor, ce)
            if cursor >= ke:
                break
        if ke - cursor > _EPS:
            result.append((cursor, ke))
    return [(s, e) for s, e in result if e - s > _EPS]


def merge_close_segments(segments: List[Segment], max_gap: float) -> List[Segment]:
    """Merge keeps separated by a gap shorter than max_gap (one breath)."""
    if not segments or max_gap <= _EPS:
        return list(segments)
    ordered = sorted(segments, key=lambda s: s[0])
    merged: List[Segment] = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start - last_end <= max_gap + _EPS:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def build_segments(
    silences: List[Segment],
    duration: float,
    padding_pre: float = config.PADDING_PRE,
    padding_post: float = config.PADDING_POST,
    min_keep: float = config.MIN_KEEP,
    merge_gap: float = config.MERGE_GAP,
) -> List[Segment]:
    """Full pipeline: invert -> pad (pre/post) -> merge -> merge-close -> drop tiny."""
    keep = invert_to_keep(silences, duration)
    padded = apply_padding(keep, padding_pre, padding_post, duration)
    merged = merge_segments(padded)
    closed = merge_close_segments(merged, merge_gap)
    return filter_short(closed, min_keep)


def complement(keep: List[Segment], duration: float) -> List[Segment]:
    """Gaps not covered by keep-segments within [0, duration]."""
    return _removed_regions(
        [(s, e) for s, e in sorted(keep)], duration)


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