"""Small English sentence splitter used when sentencex's native wheel is blocked.

Pipecat imports ``sentencex`` for sentence-boundary detection. Some managed
Windows installs prohibit loading that optional native extension. This keeps
the Pipecat pipeline available there while preserving punctuation boundaries
for the assistant's English responses.
"""
from __future__ import annotations

import re
from collections.abc import Iterator

_BOUNDARY = re.compile(r"([.!?;…。？！；｡]+[\"'’”」』)\]]*)\s+")
_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "vs.", "etc.",
    "e.g.", "i.e.", "st.", "no.", "u.s.", "u.k.",
}


def segment(language: str, text: str) -> Iterator[str]:
    """Yield text through sentence-ending punctuation, retaining whitespace."""
    start = 0
    for match in _BOUNDARY.finditer(text):
        end = match.end(1)
        punctuation = match.group(1)
        prefix = text[start:end]
        tail = prefix.rstrip()
        last_word = re.search(r"(?:[A-Za-z](?:\.[A-Za-z])*)\.$", tail)
        if punctuation.endswith(".") and last_word:
            token = last_word.group(0).lower()
            if token in _ABBREVIATIONS or re.fullmatch(r"[a-z]\.", token):
                continue
        yield text[start : match.end()]
        start = match.end()
    if start < len(text):
        yield text[start:]
