"""
Tests for InferenceService streaming support: the ThinkTagFilter, the
run_inference_stream generator, and OpenAI passthrough params on
run_inference.
"""

from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.services.inference_service import InferenceService, ThinkTagFilter


class TestThinkTagFilter:
    """Unit tests for the stateful <think> tag stripper."""

    def _run(self, chunks: List[str]) -> str:
        f = ThinkTagFilter()
        out = "".join(f.feed(c) for c in chunks)
        return out + f.flush()

    def test_passthrough_without_tags(self) -> None:
        assert self._run(["Hello ", "world"]) == "Hello world"

    def test_strips_complete_tag_in_one_chunk(self) -> None:
        assert self._run(["<think>reasoning</think>Answer"]) == "Answer"

    def test_strips_tag_split_across_chunks(self) -> None:
        assert (
            self._run(["<thi", "nk>secret", " stuff</th", "ink>Visible"])
            == "Visible"
        )

    def test_strips_multiple_tags(self) -> None:
        assert (
            self._run(["a<think>x</think>b<think>y</think>c"]) == "abc"
        )

    def test_unterminated_think_is_discarded(self) -> None:
        assert self._run(["before<think>never closed"]) == "before"

    def test_partial_open_tag_that_never_completes_is_emitted(self) -> None:
        # "<thi" looks like a tag prefix but the stream ends; flush must
        # release it because it never became a real tag.
        assert self._run(["text <thi"]) == "text <thi"

    def test_lone_angle_bracket_passes_through(self) -> None:
        assert self._run(["a < b and a <t", "ag> done"]) == "a < b and a <tag> done"

    def test_stray_close_tag_passes_through(self) -> None:
        # A </think> with no open tag is passed through verbatim, matching
        # the non-streaming _clean_response regex behavior.
        assert self._run(["text</think>more"]) == "text</think>more"

    def test_close_tag_split_across_chunks(self) -> None:
        assert (
            self._run(["<think>secret</thi", "nk>visible"]) == "visible"
        )

    def test_empty_chunk_is_safe(self) -> None:
        assert self._run(["", "Hello", "", " world", ""]) == "Hello world"
