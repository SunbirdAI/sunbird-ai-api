"""Canned GoogleAnalyticsClient.run_report outputs for service tests."""

TRAFFIC_RESPONSE = {
    "dimension_headers": ["date"],
    "metric_headers": [
        "activeUsers",
        "newUsers",
        "sessions",
        "engagedSessions",
        "engagementRate",
        "averageSessionDuration",
        "bounceRate",
    ],
    "rows": [
        {
            "dimensions": ["20260413"],
            "metrics": ["100", "30", "120", "80", "0.67", "95.5", "0.33"],
        },
        {
            "dimensions": ["20260414"],
            "metrics": ["110", "35", "130", "85", "0.65", "102.1", "0.35"],
        },
    ],
}

TOP_PAGES_RESPONSE = {
    "dimension_headers": ["pagePath", "pageTitle"],
    "metric_headers": ["screenPageViews", "activeUsers", "averageSessionDuration"],
    "rows": [
        {"dimensions": ["/dashboard", "Dashboard"], "metrics": ["200", "150", "120.5"]},
        {"dimensions": ["/login", "Login"], "metrics": ["180", "170", "45.2"]},
    ],
}

PLATFORM_RESPONSE = {
    "dimension_headers": ["deviceCategory", "operatingSystem", "browser"],
    "metric_headers": ["activeUsers", "sessions"],
    "rows": [
        {"dimensions": ["desktop", "Windows", "Chrome"], "metrics": ["500", "600"]},
        {"dimensions": ["mobile", "Android", "Chrome"], "metrics": ["300", "350"]},
        {"dimensions": ["mobile", "iOS", "Safari"], "metrics": ["100", "120"]},
    ],
}

GEO_RESPONSE = {
    "dimension_headers": ["country", "city"],
    "metric_headers": ["activeUsers", "sessions"],
    "rows": [
        {"dimensions": ["Uganda", "Kampala"], "metrics": ["800", "900"]},
        {"dimensions": ["Kenya", "Nairobi"], "metrics": ["100", "120"]},
    ],
}

EVENTS_RESPONSE = {
    "dimension_headers": ["eventName"],
    "metric_headers": ["eventCount", "totalUsers"],
    "rows": [
        {"dimensions": ["page_view"], "metrics": ["1200", "400"]},
        {"dimensions": ["session_start"], "metrics": ["450", "400"]},
    ],
}
