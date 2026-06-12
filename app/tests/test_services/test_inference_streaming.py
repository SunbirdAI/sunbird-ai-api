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


def _make_chunk(
    content: Optional[str] = None,
    usage: Optional[Dict[str, int]] = None,
    role: Optional[str] = None,
) -> SimpleNamespace:
    """Build a fake OpenAI streaming chunk object."""
    choices = []
    if content is not None or role is not None:
        choices = [
            SimpleNamespace(
                delta=SimpleNamespace(role=role, content=content),
                index=0,
                finish_reason=None,
            )
        ]
    usage_ns = SimpleNamespace(**usage) if usage else None
    return SimpleNamespace(choices=choices, usage=usage_ns)


def _make_completion(content: str) -> SimpleNamespace:
    """Build a fake non-streaming OpenAI completion response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content))
        ],
        usage=SimpleNamespace(
            completion_tokens=3, prompt_tokens=5, total_tokens=8
        ),
    )


class TestRunInferencePassthroughParams:
    """run_inference must forward max_tokens/top_p/stop to the API payload."""

    def _service_with_mock_client(self) -> tuple:
        service = InferenceService(
            runpod_api_key="test-key", qwen_endpoint_id="test-endpoint"
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_completion(
            "Oli otya?"
        )
        return service, mock_client

    def test_passthrough_params_in_payload(self) -> None:
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.run_inference(
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=128,
                top_p=0.9,
                stop=["\n"],
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 128
        assert kwargs["top_p"] == 0.9
        assert kwargs["stop"] == ["\n"]

    def test_omitted_params_not_in_payload(self) -> None:
        service, mock_client = self._service_with_mock_client()
        with patch.object(service, "_get_client", return_value=mock_client):
            service.run_inference(
                messages=[{"role": "user", "content": "Hello"}]
            )
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "max_tokens" not in kwargs
        assert "top_p" not in kwargs
        assert "stop" not in kwargs
