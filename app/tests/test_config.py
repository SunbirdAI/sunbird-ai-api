from app.core.config import Settings


def test_ga_properties_parses_env_string():
    s = Settings(
        ga_properties_raw="506611499:Sunflower,448469065:Sunbird Speech",
        ga_impersonation_target="ga-reader@test.iam.gserviceaccount.com",
    )
    assert s.ga_properties == {
        "506611499": "Sunflower",
        "448469065": "Sunbird Speech",
    }
    assert s.ga_enabled is True


def test_ga_enabled_false_when_no_target():
    s = Settings(ga_properties_raw="506611499:Sunflower")
    assert s.ga_enabled is False


def test_ga_enabled_false_when_no_properties():
    s = Settings(ga_impersonation_target="ga-reader@test.iam.gserviceaccount.com")
    assert s.ga_enabled is False


def test_ga_properties_ignores_malformed_entries():
    s = Settings(
        ga_properties_raw="506611499:Sunflower,malformed,448469065:Sunbird Speech"
    )
    assert s.ga_properties == {
        "506611499": "Sunflower",
        "448469065": "Sunbird Speech",
    }


def test_ga_properties_env_alias_works(monkeypatch):
    """End-to-end check: the GA_PROPERTIES alias populates ga_properties_raw."""
    monkeypatch.setenv("GA_PROPERTIES", "506611499:Sunflower")
    monkeypatch.setenv(
        "GA_IMPERSONATION_TARGET", "ga-reader@test.iam.gserviceaccount.com"
    )
    s = Settings()
    assert s.ga_properties == {"506611499": "Sunflower"}
    assert s.ga_enabled is True
