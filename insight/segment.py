"""Split a review into sentence-like segments that are exact substrings of the original.

The evidence quote is always one of these segments, sliced from the original string, so
`evidence_quote in review_text` holds by construction. A classifier picks a segment number;
it never retypes the text.
"""

import re

SEGMENTER_VERSION = "segments-v1"
MAX_SEGMENT_CHARS = 220
MAX_SEGMENTS = 12
_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\s*[\r\n]+\s*")
# Whitespace after , ; : or before a conjunction. Splitting inside the matched whitespace
# keeps every visible character in exactly one segment.
_SOFT_BREAK = re.compile(r"(?<=[,;:])\s+|\s+(?=(?:but|and|so|because)\b)", re.IGNORECASE)


def _trim(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_long(text, start, end):
    """Break an over-long span at the last soft break before the limit."""
    out = []
    while end - start > MAX_SEGMENT_CHARS:
        window = text[start:start + MAX_SEGMENT_CHARS]
        cut = None
        for m in _SOFT_BREAK.finditer(window):
            if m.start() > 40:
                cut = m
        if cut is None:
            space = window.rfind(" ", 40)
            if space == -1:
                break
            split_at, resume_at = start + space, start + space + 1
        else:
            split_at, resume_at = start + cut.start(), start + cut.end()
        s, e = _trim(text, start, split_at)
        if e > s:
            out.append((s, e))
        start = resume_at
    s, e = _trim(text, start, end)
    if e > s:
        out.append((s, e))
    return out


def segment_spans(text: str) -> list:
    """Return [(start, end), ...] covering every non-whitespace character of `text`."""
    spans, pos = [], 0
    for m in _BOUNDARY.finditer(text):
        s, e = _trim(text, pos, m.start())
        if e > s:
            spans.append((s, e))
        pos = m.end()
    s, e = _trim(text, pos, len(text))
    if e > s:
        spans.append((s, e))
    # Merge fragments with no letters or digits (e.g. "!!!", emoji runs) into the previous span.
    merged = []
    for s, e in spans:
        piece = text[s:e]
        if merged and not any(ch.isalnum() for ch in piece) and len(piece) <= 12:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    out = []
    for s, e in merged:
        out.extend(_split_long(text, s, e) if e - s > MAX_SEGMENT_CHARS else [(s, e)])
    if len(out) > MAX_SEGMENTS:
        out = out[:MAX_SEGMENTS - 1] + [(out[MAX_SEGMENTS - 1][0], out[-1][1])]
    return out


def segments(text: str) -> list:
    return [text[s:e] for s, e in segment_spans(text)]
