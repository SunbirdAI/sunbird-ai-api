from datetime import datetime

import pytest

from app.schemas.billing_analytics import BillingRecord
from app.services.billing_analytics.aggregation import (
    bucket_key,
    group_records,
    paginate_sort_search,
    provider_totals,
    rollup_timeseries,
    summarize,
)
from app.services.billing_analytics.ranges import resolve_range


def _rec(**kw):
    base = dict(
        provider="runpod",
        object_id="ep1",
        object_name="ep1",
        timestamp=datetime(2026, 5, 1),
        cost=10.0,
    )
    base.update(kw)
    return BillingRecord(**base)


def test_billing_record_defaults():
    r = _rec()
    assert r.runtime_ms is None
    assert r.storage_gb is None
    assert r.tags == {}
    assert r.resource_breakdown == {}


def test_resolve_range_named_last_7_days():
    now = datetime(2026, 6, 29, 12, 0, 0)
    start, end = resolve_range("last_7_days", None, None, now)
    assert end == now
    assert (end - start).days == 7


def test_resolve_range_this_month():
    now = datetime(2026, 6, 29, 12, 0, 0)
    start, end = resolve_range("this_month", None, None, now)
    assert start == datetime(2026, 6, 1)
    assert end == now


def test_resolve_range_custom_requires_both():
    now = datetime(2026, 6, 29)
    with pytest.raises(ValueError):
        resolve_range("custom", "2026-06-01T00:00:00Z", None, now)


def test_resolve_range_custom_without_dates_raises():
    now = datetime(2026, 6, 29)
    with pytest.raises(ValueError):
        resolve_range("custom", None, None, now)


def test_resolve_range_custom_parses_iso():
    now = datetime(2026, 6, 29)
    start, end = resolve_range(
        "custom", "2026-05-01T00:00:00Z", "2026-06-01T00:00:00Z", now
    )
    assert start == datetime(2026, 5, 1)
    assert end == datetime(2026, 6, 1)


def test_bucket_key_resolutions():
    ts = datetime(2026, 5, 4, 13, 0, 0)  # a Monday
    assert bucket_key(ts, "hour") == "2026-05-04 13:00"
    assert bucket_key(ts, "day") == "2026-05-04"
    assert bucket_key(ts, "month") == "2026-05"
    assert bucket_key(ts, "year") == "2026"
    assert bucket_key(ts, "week") == "2026-W19"


def test_rollup_timeseries_sums_per_bucket():
    recs = [
        _rec(timestamp=datetime(2026, 5, 1), cost=10.0, runtime_ms=1000, storage_gb=5),
        _rec(timestamp=datetime(2026, 5, 1), cost=5.0, runtime_ms=500, storage_gb=2),
        _rec(timestamp=datetime(2026, 5, 2), cost=7.0, runtime_ms=700, storage_gb=3),
    ]
    ts = rollup_timeseries(recs, "day", group_by=None)
    assert ts["labels"] == ["2026-05-01", "2026-05-02"]
    assert ts["cost"] == [15.0, 7.0]
    assert ts["runtime_ms"] == [1500.0, 700.0]
    assert ts["storage_gb"] == [7.0, 3.0]
    assert ts["cost_by_group"] == {}


def test_rollup_timeseries_grouped():
    recs = [
        _rec(provider="runpod", timestamp=datetime(2026, 5, 1), cost=10.0),
        _rec(
            provider="modal",
            object_id="app1",
            object_name="app1",
            timestamp=datetime(2026, 5, 1),
            cost=4.0,
        ),
    ]
    ts = rollup_timeseries(recs, "day", group_by="provider")
    assert ts["cost_by_group"]["runpod"] == [10.0]
    assert ts["cost_by_group"]["modal"] == [4.0]


def test_group_records_by_gpu_skips_none():
    recs = [
        _rec(gpu="NVIDIA A40", cost=10.0, runtime_ms=100, storage_gb=1),
        _rec(gpu="NVIDIA A40", cost=5.0, runtime_ms=50, storage_gb=1),
        _rec(gpu=None, cost=99.0),
    ]
    rows = group_records(recs, "gpu")
    assert len(rows) == 1
    assert rows[0]["key"] == "NVIDIA A40"
    assert rows[0]["cost"] == 15.0
    assert rows[0]["count"] == 2


def test_summarize_counts_and_tops():
    recs = [
        _rec(
            provider="runpod",
            object_id="ep1",
            object_name="ep1",
            timestamp=datetime(2026, 5, 1),
            cost=20.0,
            runtime_ms=2000,
            storage_gb=10,
        ),
        _rec(
            provider="runpod",
            object_id="ep2",
            object_name="ep2",
            timestamp=datetime(2026, 5, 2),
            cost=5.0,
            runtime_ms=500,
            storage_gb=2,
        ),
        _rec(
            provider="modal",
            object_id="app1",
            object_name="app1",
            timestamp=datetime(2026, 5, 2),
            cost=8.0,
        ),
    ]
    s = summarize(recs, num_days=2)
    assert s["total_spend"] == 33.0
    assert s["avg_daily_spend"] == 16.5
    assert s["active_endpoints"] == 2
    assert s["active_modal_apps"] == 1
    assert s["highest_cost_endpoint"]["name"] == "ep1"
    assert s["highest_cost_platform"]["name"] == "runpod"


def test_provider_totals():
    recs = [
        _rec(provider="runpod", cost=10.0, runtime_ms=100, storage_gb=1),
        _rec(provider="modal", object_id="a", object_name="a", cost=4.0),
    ]
    pt = provider_totals(recs)
    assert pt["labels"] == ["runpod", "modal"]
    assert pt["cost"] == [10.0, 4.0]


def test_paginate_sort_search():
    recs = [
        _rec(object_name="alpha", cost=1.0),
        _rec(object_name="beta", cost=3.0),
        _rec(object_name="gamma", cost=2.0),
    ]
    page, total = paginate_sort_search(
        recs, page=1, page_size=2, sort="cost", search=None
    )
    assert total == 3
    assert [r.cost for r in page] == [3.0, 2.0]  # cost desc
    page2, total2 = paginate_sort_search(
        recs, page=1, page_size=10, sort="cost", search="alp"
    )
    assert total2 == 1
    assert page2[0].object_name == "alpha"


def test_billing_record_normalizes_tz_aware_to_naive_utc():
    from datetime import timezone

    r = _rec(timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))
    assert r.timestamp.tzinfo is None
    assert r.timestamp == datetime(2026, 5, 1, 12, 0)


def test_rollup_timeseries_mixed_tz_awareness():
    from datetime import timezone

    # Modal returns tz-aware UTC timestamps; Runpod returns naive. The combined
    # set must sort/bucket without raising "can't compare naive and aware".
    aware = _rec(
        provider="modal",
        object_id="app1",
        object_name="app1",
        timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cost=4.0,
    )
    naive = _rec(provider="runpod", timestamp=datetime(2026, 5, 1), cost=10.0)
    ts = rollup_timeseries([aware, naive], "day", group_by=None)
    assert ts["labels"] == ["2026-05-01"]
    assert ts["cost"] == [14.0]


def test_floor_to_quantum():
    from app.services.billing_analytics.ranges import floor_to_quantum

    dt = datetime(2026, 6, 30, 13, 45, 37, 123456)
    assert floor_to_quantum(dt, 60) == datetime(2026, 6, 30, 13, 45, 0)
    assert floor_to_quantum(dt, 3600) == datetime(2026, 6, 30, 13, 0, 0)
    # quantum < 1 is guarded to 1 second (drops sub-second only)
    assert floor_to_quantum(dt, 0) == datetime(2026, 6, 30, 13, 45, 37)


def test_paginate_sort_search_ascending():
    recs = [
        _rec(object_name="a", cost=1.0),
        _rec(object_name="b", cost=3.0),
        _rec(object_name="c", cost=2.0),
    ]
    page, total = paginate_sort_search(
        recs, page=1, page_size=10, sort="cost", search=None, descending=False
    )
    assert total == 3
    assert [r.cost for r in page] == [1.0, 2.0, 3.0]


def test_paginate_sort_search_timestamp_ascending():
    recs = [
        _rec(timestamp=datetime(2026, 5, 3), cost=1.0),
        _rec(timestamp=datetime(2026, 5, 1), cost=2.0),
        _rec(timestamp=datetime(2026, 5, 2), cost=3.0),
    ]
    page, _ = paginate_sort_search(
        recs, page=1, page_size=10, sort="timestamp", search=None, descending=False
    )
    assert [r.timestamp for r in page] == [
        datetime(2026, 5, 1),
        datetime(2026, 5, 2),
        datetime(2026, 5, 3),
    ]


def test_summarize_excludes_network_volumes_from_endpoint_count():
    recs = [
        _rec(provider="runpod", object_id="ep1", object_name="ep1", cost=20.0),
        _rec(
            provider="runpod",
            object_id="network-volumes",
            object_name="Network Volumes",
            cost=5.0,
            metadata={"kind": "network_volume"},
        ),
    ]
    s = summarize(recs, num_days=1)
    assert s["active_endpoints"] == 1  # network volumes are not an endpoint
    assert s["total_spend"] == 25.0  # but their cost is still in the total
    assert s["highest_cost_endpoint"]["name"] == "ep1"


def test_summarize_avg_storage_gb_from_gb_hours():
    # diskSpaceBilledGb is GB-hours; 350 GB steady over 2 full days = 350*24*2.
    recs = [
        _rec(
            provider="runpod",
            object_id="nv",
            object_name="Network Volumes",
            timestamp=datetime(2026, 5, 1),
            cost=0.8,
            storage_gb=8400,
            metadata={"kind": "network_volume"},
        ),
        _rec(
            provider="runpod",
            object_id="nv",
            object_name="Network Volumes",
            timestamp=datetime(2026, 5, 2),
            cost=0.8,
            storage_gb=8400,
            metadata={"kind": "network_volume"},
        ),
    ]
    s = summarize(recs, num_days=2)
    assert s["total_storage_gb"] == 16800.0  # raw GB-hours
    assert s["avg_storage_gb"] == 350.0  # 16800 / (2 days * 24h)


def test_group_records_by_object_any_provider():
    recs = [
        _rec(provider="vastai", object_id="instance-1", object_name="job-a", cost=10.0),
        _rec(provider="vastai", object_id="instance-1", object_name="job-a", cost=5.0),
        _rec(provider="vastai", object_id="instance-2", object_name="job-b", cost=3.0),
    ]
    rows = group_records(recs, "object")
    keys = {row["key"]: row["cost"] for row in rows}
    assert keys == {"job-a": 15.0, "job-b": 3.0}


def test_object_in_supported_group_bys():
    from app.services.billing_analytics.aggregation import SUPPORTED_GROUP_BYS

    assert "object" in SUPPORTED_GROUP_BYS
