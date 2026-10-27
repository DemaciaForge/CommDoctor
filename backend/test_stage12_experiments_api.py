"""Stage12 paired hard/soft API contracts and bounded sweep behavior."""

import main
from fastapi.testclient import TestClient
from stage12_experiments import run_compare, run_sweep
from stage12_soft_viterbi import paired_decode


client = TestClient(main.app)
COMPARE = "/api/stage12/compare"
SWEEP = "/api/stage12/ber-sweep"


def test_compare_uses_same_samples_reports_truthful_information_ber_and_excludes_tails(monkeypatch):
    observed = []
    original = main.run_stage12_compare

    def capture(**kwargs):
        result = original(**kwargs)
        observed.append(result)
        return result

    monkeypatch.setattr(main, "run_stage12_compare", capture)
    response = client.post(COMPARE, json={"n_information_bits": 73, "eb_n0_db": 2.5, "seed": 9, "include_details": True})
    assert response.status_code == 200
    body = response.json()
    details = body["details"]
    expected = paired_decode(details["information_bits"], details["received_samples"])
    assert details["hard_information_bits"] == list(expected.hard_information_bits)
    assert details["soft_information_bits"] == list(expected.soft_information_bits)
    assert len(details["information_bits"]) == 73
    assert len(details["encoded_bits"]) == len(details["received_samples"]) == 150
    assert body["lengths"] == {"information_bits": 73, "tail_bits": 2, "encoded_bits": 150, "decoded_information_bits": 73}
    assert body["fairness"]["same_received_samples"] is True
    assert body["fairness"]["noise_draws"] == 1
    assert body["fairness"]["hard_input_sha256"] == body["fairness"]["soft_input_sha256"]
    for key, decisions in (("hard_decision", details["hard_information_bits"]), ("soft_decision", details["soft_information_bits"])):
        measure = body["results"][key]
        errors = sum(a != b for a, b in zip(details["information_bits"], decisions))
        assert measure["errors"] == errors
        assert measure["compared"] == 73
        assert measure["ber"] == errors / 73
        assert measure["tail_counted"] is False
    assert body["results"]["decoded_tail_bits"] == [0, 0]


def test_compare_reproducibility_default_bounds_and_safe_internal_error(monkeypatch):
    request = {"n_information_bits": 61, "eb_n0_db": 5, "seed": 311, "include_details": True}
    assert client.post(COMPARE, json=request).json() == client.post(COMPARE, json=request).json()
    assert client.post(COMPARE, json={"seed": 4}).status_code == 200
    for payload in (
        {"n_information_bits": True}, {"n_information_bits": 4097}, {"seed": True},
        {"seed": -1}, {"eb_n0_db": 31}, {"eb_n0_db": float("nan")},
        {"include_details": True, "n_information_bits": 257}, {"extra": 1},
    ):
        assert client.post(COMPARE, json=payload).status_code == 422

    def fail(**kwargs):
        raise RuntimeError("private implementation detail")

    monkeypatch.setattr(main, "run_stage12_compare", fail)
    failure = client.post(COMPARE, json={"n_information_bits": 4})
    assert failure.status_code == 500
    assert failure.json()["detail"] == "Stage12 comparison could not be completed. Please retry."
    assert "private implementation" not in failure.text


def test_paired_core_receives_one_immutable_received_tuple(monkeypatch):
    import stage12_experiments as experiments
    original = experiments.paired_decode
    inputs = []

    def capture(information, received, **kwargs):
        inputs.append((information, received))
        return original(information, received, **kwargs)

    monkeypatch.setattr(experiments, "paired_decode", capture)
    experiments.run_compare(12, 4, 88)
    assert len(inputs) == 1
    assert type(inputs[0][1]) is tuple
    assert len(inputs[0][1]) == 28


def test_sweep_reuses_one_payload_and_calls_paired_decoder_once_per_point(monkeypatch):
    import stage12_experiments as experiments
    original = experiments.paired_decode
    payloads = []
    received = []

    def capture(information, samples, **kwargs):
        payloads.append(information)
        received.append(samples)
        return original(information, samples, **kwargs)

    monkeypatch.setattr(experiments, "paired_decode", capture)
    result = experiments.run_sweep(0, 4, 2, 31, 2026)
    assert len(result["points"]) == len(payloads) == len(received) == 3
    assert len(set(payloads)) == 1
    assert len(set(received)) == 3


def test_sweep_pairs_each_point_replays_and_reports_actual_denominators():
    params = {"start_db": 0, "stop_db": 4, "step_db": 2, "n_information_bits": 79, "seed": 412}
    first = run_sweep(**params)
    assert first == run_sweep(**params)
    response = client.post(SWEEP, json=params)
    assert response.status_code == 200
    body = response.json()
    assert body == first
    assert body["parameters"]["total_information_bits"] == 237
    assert body["fairness"] == {"same_payload_across_points": True, "same_received_samples_per_point": True, "noise_draws_per_point": 1}
    assert [point["eb_n0_db"] for point in body["points"]] == [0, 2, 4]
    assert len({point["seed"] for point in body["points"]}) == 3
    for point in body["points"]:
        assert point["hard_input_sha256"] == point["soft_input_sha256"] == point["received_samples_sha256"]
        for key in ("hard_decision", "soft_decision"):
            measure = point[key]
            assert measure["compared"] == 79
            assert measure["ber"] == measure["errors"] / 79
            assert measure["tail_counted"] is False


def test_sweep_rejects_bad_grid_nonfinite_over_budget_and_reports_zero_as_measurement():
    invalid = [
        {"start_db": 0, "stop_db": 0}, {"start_db": 2, "stop_db": 1},
        {"start_db": 0, "stop_db": 1, "step_db": 0},
        {"start_db": 0, "stop_db": 1, "step_db": 0.3},
        {"start_db": float("inf")}, {"start_db": 0, "stop_db": 16, "step_db": 1},
        {"n_information_bits": 4097}, {"n_information_bits": True},
        {"start_db": 0, "stop_db": 8, "step_db": 1, "n_information_bits": 4096},
        {"unknown": 2},
    ]
    for payload in invalid:
        response = client.post(SWEEP, json=payload)
        assert response.status_code == 422, (payload, response.text)
        assert "Traceback" not in response.text
    zero = client.post(SWEEP, json={"start_db": 30, "stop_db": 30, "step_db": 1, "n_information_bits": 4, "seed": 7})
    # A one-point interval is deliberately rejected by the shared ordered-range contract.
    assert zero.status_code == 422
    sweep = client.post(SWEEP, json={"start_db": 28, "stop_db": 30, "step_db": 2, "n_information_bits": 4, "seed": 7}).json()
    assert any(point[metric]["errors"] == 0 and point[metric]["ber"] == 0 for point in sweep["points"] for metric in ("hard_decision", "soft_decision"))
    assert sweep["sampling"]["zero_error_note"]
