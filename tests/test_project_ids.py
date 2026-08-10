"""Project ids double as filenames, so they must be readable, unique, and path-safe."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("AFDX_GENERATOR_PROJECTS_DIR", str(tmp_path / "projects"))
    from afdx_generator.storage import project_store
    return project_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AFDX_GENERATOR_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("AFDX_GENERATOR_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("AFDX_GENERATOR_ENV_FILE", str(tmp_path / "env.json"))
    from afdx_generator.app import create_app
    return TestClient(create_app())


def test_id_is_derived_from_the_name(store):
    assert store.new_project_id("realisticNetwork") == "realisticNetwork"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("my network", "my_network"),
        ("simple-network", "simple_network"),   # anything but letters/digits becomes '_'
        ("Net 2024!", "Net_2024"),
    ],
)
def test_awkward_names_become_safe_filenames(store, name, expected):
    assert store.new_project_id(name) == expected


def test_a_name_with_nothing_usable_falls_back_to_a_random_id(store):
    generated = store.new_project_id("***")
    assert generated.isalnum() and len(generated) == 12


def test_second_project_with_the_same_name_gets_a_suffix(store):
    from afdx_generator.models.project import Project

    assert store.new_project_id("net") == "net"
    store.save_project(Project(id="net", name="net"))
    assert store.new_project_id("net") == "net-2"

    store.save_project(Project(id="net-2", name="net"))
    assert store.new_project_id("net") == "net-3"


def test_collisions_are_detected_regardless_of_case(store):
    """Linux would keep Net.json and net.json apart; a case-insensitive disk would not."""
    from afdx_generator.models.project import Project

    store.save_project(Project(id="Net", name="Net"))
    assert store.new_project_id("net") == "net-2"
    assert store.new_project_id("NET") == "NET-2"


def test_very_long_names_are_truncated(store):
    generated = store.new_project_id("x" * 500)
    assert len(generated) <= 60


def test_id_can_never_escape_the_projects_directory(store):
    for hostile in ("../../etc/passwd", "/absolute/path", "..", "./."):
        generated = store.new_project_id(hostile)
        assert "/" not in generated and generated not in ("", ".", "..")


def test_creating_through_the_api_writes_a_readable_file(client, tmp_path):
    created = client.post("/api/projects", json={"name": "realisticNetwork"}).json()
    assert created["id"] == "realisticNetwork"
    assert (tmp_path / "projects" / "realisticNetwork.json").exists()


def test_two_projects_named_alike_do_not_overwrite_each_other(client):
    first = client.post("/api/projects", json={"name": "twin"}).json()
    second = client.post("/api/projects", json={"name": "twin"}).json()

    assert first["id"] != second["id"]
    assert {p["id"] for p in client.get("/api/projects").json()} == {first["id"], second["id"]}
    # Both must still be individually loadable -- i.e. neither file clobbered the other.
    assert client.get(f"/api/projects/{first['id']}").status_code == 200
    assert client.get(f"/api/projects/{second['id']}").status_code == 200


def test_existing_projects_with_random_ids_still_load(client, tmp_path):
    """Projects created before this change keep their opaque ids; nothing migrates."""
    from afdx_generator.models.project import Project
    from afdx_generator.storage import project_store

    project_store.save_project(Project(id="f0a2eb5fa15d", name="realisticNetwork"))
    fetched = client.get("/api/projects/f0a2eb5fa15d").json()
    assert fetched["name"] == "realisticNetwork"
