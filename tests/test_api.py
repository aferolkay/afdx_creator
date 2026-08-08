"""API tests. No OMNeT++ toolchain required -- validation is exercised with a fake binary."""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AFDX_GENERATOR_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("AFDX_GENERATOR_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("AFDX_GENERATOR_ENV_FILE", str(tmp_path / "env.json"))

    from afdx_generator.app import create_app

    return TestClient(create_app())


SMALL_NETWORK = {
    "nodes": [
        {"id": "es0", "kind": "end_system", "label": "E0"},
        {"id": "es1", "kind": "end_system", "label": "E1"},
        {"id": "sw1", "kind": "switch", "label": "S1"},
    ],
    "edges": [
        {"id": "e1", "node_a_id": "es0", "node_b_id": "sw1", "length_m": 10.0},
        {"id": "e2", "node_a_id": "sw1", "node_b_id": "es1", "length_m": 10.0},
    ],
    "virtual_links": [
        {
            "id": "vl1", "hex_vl_id": "0x1", "label": "V1", "frame_bytes": 256,
            "source_node_id": "es0", "destination_node_ids": ["es1"],
            "bag_s": 0.002, "offset_s": 0.0,
        }
    ],
}


def _make_project(client, body=SMALL_NETWORK, name="test net"):
    project_id = client.post("/api/projects", json={"name": name}).json()["id"]
    response = client.put(f"/api/projects/{project_id}", json=body)
    assert response.status_code == 200
    return project_id


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_constants_are_served_for_the_frontend(client):
    """The browser duplicates the rho/sigma formula; it must read these rather than hardcode them."""
    data = client.get("/api/constants").json()
    assert data["phy_overhead_bits"] == 160
    assert data["default_sigma_margin_factor"] == 4.0


def test_project_lifecycle(client):
    created = client.post("/api/projects", json={"name": "my net"}).json()
    project_id = created["id"]

    assert any(p["id"] == project_id for p in client.get("/api/projects").json())
    assert client.get(f"/api/projects/{project_id}").json()["name"] == "my net"

    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope").status_code == 404


def test_problems_endpoint_reports_topology_faults(client):
    broken = dict(SMALL_NETWORK)
    broken = {
        **SMALL_NETWORK,
        "nodes": SMALL_NETWORK["nodes"] + [{"id": "sw9", "kind": "switch", "label": "S9"}],
    }
    project_id = _make_project(client, broken)
    problems = client.get(f"/api/projects/{project_id}/problems").json()["problems"]
    assert any("S9" in p for p in problems)


def test_generate_writes_files_and_reports_routes(client):
    project_id = _make_project(client)
    result = client.post(f"/api/projects/{project_id}/generate").json()

    names = set(result["files"])
    assert "test_net.ned" in names        # note the space in "test net" became an underscore
    assert "test_net.ini" in names
    assert "S1.txt" in names
    assert result["virtual_links"][0]["route"] == "es0->sw1->es1"


def test_generate_rejects_an_invalid_topology(client):
    broken = {**SMALL_NETWORK, "edges": []}
    project_id = _make_project(client, broken)
    response = client.post(f"/api/projects/{project_id}/generate")
    assert response.status_code == 400
    assert response.json()["detail"]["problems"]


def test_traffic_suggestion_matches_the_python_formula(client):
    response = client.post("/api/suggest-traffic", json={"payload_bytes": 1183, "bag_s": 0.001})
    data = response.json()
    assert data["lmax_bits"] == 10000
    assert data["rho_bps"] == pytest.approx(10e6)
    assert data["sigma_bits"] == pytest.approx(40000)


def test_validation_without_a_configured_binary_fails_clearly(client):
    project_id = _make_project(client)
    result = client.post(f"/api/projects/{project_id}/validate").json()
    assert result["passed"] is False
    assert result["issues"][0]["kind"] == "launch_failure"
    assert "binary" in result["issues"][0]["message"].lower()


def _write_fake_binary(path, output, exit_code=0):
    path.write_text(f"#!/bin/sh\ncat <<'EOF'\n{output}\nEOF\nexit {exit_code}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_validation_passes_against_a_clean_fake_run(client, tmp_path):
    binary = _write_fake_binary(
        tmp_path / "fake_sim.sh",
        "Running simulation...\n<!> Simulation time limit reached -- at t=1s\nEnd.",
    )
    client.put("/api/environment", json={"binary_path": str(binary)})

    project_id = _make_project(client)
    result = client.post(f"/api/projects/{project_id}/validate").json()
    assert result["passed"] is True
    assert result["issues"] == []


def test_validation_surfaces_policer_drops_from_a_failing_run(client, tmp_path):
    binary = _write_fake_binary(
        tmp_path / "fake_sim.sh",
        "Running simulation...\n"
        "TOKEN_INSUFFICIENT (VL:1) SW:0\n"
        "TOKEN_INSUFFICIENT (VL:1) SW:0\n"
        "End.",
    )
    client.put("/api/environment", json={"binary_path": str(binary)})

    project_id = _make_project(client)
    result = client.post(f"/api/projects/{project_id}/validate").json()

    assert result["passed"] is False
    drop = next(i for i in result["issues"] if i["kind"] == "policer_drop")
    assert drop["count"] == 2 and drop["virtual_link"] == "1"
    assert "sigma" in drop["hint"]


def test_environment_config_round_trips(client):
    payload = {"binary_path": "/tmp/x", "afdx_src_dir": "/tmp/afdx"}
    client.put("/api/environment", json=payload)
    stored = client.get("/api/environment").json()
    assert stored["binary_path"] == "/tmp/x"
    assert stored["afdx_src_dir"] == "/tmp/afdx"
