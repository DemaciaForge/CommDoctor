import main
from fastapi.testclient import TestClient


client = TestClient(main.app)
URL = "/api/stage13/experiments"


def test_stage13_api_default_shape_reproducible_and_truthful_metrics():
    body = {"seed": 19, "eb_n0_db": 8, "n_training_symbols": 32,
            "n_payload_symbols": 128, "mu": 0.01}
    one = client.post(URL, json=body)
    two = client.post(URL, json=body)
    assert one.status_code == two.status_code == 200
    result = one.json()
    assert result == two.json()
    assert result["contract"]["training_samples"] == 32
    assert len(result["training"]["errors"]) == 32
    assert result["results"]["raw"]["compared"] == result["results"]["lms"]["compared"] == 128
    for measure in result["results"].values():
        assert measure["ber"] == measure["errors"] / measure["compared"]
    assert len(result["series"]["raw_samples"]) == len(result["series"]["equalized_samples"]) == 128
    assert result["contract"]["same_channel_and_noise"]


def test_stage13_api_rejects_invalid_and_extra_inputs():
    for payload in ({"mu": float("nan")}, {"mu": 0}, {"mu": 0.51}, {"seed": True},
                    {"n_training_symbols": 61}, {"n_payload_symbols": 127}, {"unexpected": 1}):
        assert client.post(URL, json=payload).status_code == 422
