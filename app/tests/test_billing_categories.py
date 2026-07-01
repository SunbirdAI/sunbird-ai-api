import pytest

from app.integrations.billing.categories import (
    CATEGORIES,
    PROVIDER_CATEGORY,
    providers_in_category,
)


def test_provider_category_map():
    assert PROVIDER_CATEGORY["runpod"] == "inference"
    assert PROVIDER_CATEGORY["modal"] == "inference"
    assert PROVIDER_CATEGORY["vastai"] == "training"


def test_categories_tuple():
    assert CATEGORIES == ("inference", "training")


def test_providers_in_category():
    assert set(providers_in_category("inference")) == {"runpod", "modal"}
    assert providers_in_category("training") == ["vastai"]


def test_providers_in_category_unknown_raises():
    with pytest.raises(ValueError):
        providers_in_category("nope")
