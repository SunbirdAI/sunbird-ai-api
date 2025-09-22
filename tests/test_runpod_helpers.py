import pathlib
import sys

import pytest

# Ensure the project root is on sys.path so tests can import `app`.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.inference_services.runpod_helpers import normalize_runpod_response


def test_normalize_non_dict_input():
    resp = "plain string output"
    out = normalize_runpod_response(resp)
    assert isinstance(out, dict)
    assert out["output"] == resp
    assert out["delayTime"] is None


def test_normalize_already_full_shape():
    resp = {
        "delayTime": 0.1,
        "executionTime": 0.2,
        "id": "job-123",
        "output": {"translated_text": "hola"},
        "status": "COMPLETED",
        "workerId": "worker-1",
    }
    out = normalize_runpod_response(resp)
    # Should return unchanged reference-like content
    assert out is resp or out["id"] == "job-123"


def test_normalize_with_nested_output_field():
    resp = {"output": {"text": "hello", "translated": "salut"}}
    out = normalize_runpod_response(resp)
    assert out["output"] == resp["output"]
    assert out["status"] == "COMPLETED"


def test_normalize_empty_dict():
    resp = {}
    out = normalize_runpod_response(resp)
    # empty dict -> treated as output={}, so status should be None
    assert out["output"] == {}
    assert out["status"] is None
