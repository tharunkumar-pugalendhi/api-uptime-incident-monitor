from main import EndpointCreate
import pytest
from pydantic import ValidationError


def test_endpoint_creation_with_valid_data():
    endpoint = EndpointCreate(
        name="GitHub API",
        url="https://api.github.com"
    )

    assert endpoint.name == "GitHub API"
    assert str(endpoint.url) == "https://api.github.com/"
    assert endpoint.sla_ms == 800


def test_endpoint_rejects_short_name():
    with pytest.raises(ValidationError):
        EndpointCreate(
            name="A",
            url="https://api.github.com"
        )

@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com",
        "not-a-url",
        "file:///etc/passwd",
    ],
)
def test_endpoint_rejects_invalid_urls(url):
    with pytest.raises(ValidationError):
        EndpointCreate(
            name="Test API",
            url=url,
        )

@pytest.mark.parametrize("sla_ms", [50, 800, 10000])
def test_endpoint_accepts_valid_sla(sla_ms):
    endpoint = EndpointCreate(
        name="Test API",
        url="https://example.com",
        sla_ms=sla_ms,
    )

    assert endpoint.sla_ms == sla_ms


@pytest.mark.parametrize("sla_ms", [49, 10001])
def test_endpoint_rejects_invalid_sla(sla_ms):
    with pytest.raises(ValidationError):
        EndpointCreate(
            name="Test API",
            url="https://example.com",
            sla_ms=sla_ms,
        )