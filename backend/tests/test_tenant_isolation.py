import uuid


def _make_project(client, prefix: str):
    name = f"{prefix}-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["api_key"], name


def test_cannot_read_other_projects_data(client):
    key_a, name_a = _make_project(client, "tenant-a")
    key_b, _      = _make_project(client, "tenant-b")
    hdr_a = {"Authorization": f"Bearer {key_a}"}
    hdr_b = {"Authorization": f"Bearer {key_b}"}

    ds = client.post("/api/datasets", headers=hdr_a, json={
        "name": "leak-test", "project": name_a,
        "examples": [{"input": "secret input"}],
    })
    assert ds.status_code == 201, ds.text
    dataset_id = ds.json()["dataset_id"]

    # tenant B must NOT be able to read tenant A's dataset
    r = client.get(f"/api/datasets/{dataset_id}", headers=hdr_b)
    assert r.status_code == 404

    # tenant A still can
    r = client.get(f"/api/datasets/{dataset_id}", headers=hdr_a)
    assert r.status_code == 200


def test_dataset_name_collision_does_not_cross_tenants(client):
    key_a, name_a = _make_project(client, "tenant-c")
    key_b, name_b = _make_project(client, "tenant-d")
    hdr_a = {"Authorization": f"Bearer {key_a}"}
    hdr_b = {"Authorization": f"Bearer {key_b}"}

    # tenant A creates "shared-name" first, with 1 example
    client.post("/api/datasets", headers=hdr_a, json={
        "name": "shared-name", "project": name_a,
        "examples": [{"input": "tenant-c-only-input"}],
    })
    # tenant B creates a dataset with the SAME name, more examples, created later
    client.post("/api/datasets", headers=hdr_b, json={
        "name": "shared-name", "project": name_b,
        "examples": [{"input": "x"}, {"input": "y"}],
    })

    run = client.post("/api/evals/run", headers=hdr_a,
        json={"project": name_a, "dataset_name": "shared-name"})
    assert run.status_code == 200

    # before the fix: unscoped lookup grabs tenant B's most-recently-created
    # dataset → total_cases == 2. after the fix: must resolve to tenant A's
    # own dataset → total_cases == 1.
    assert run.json()["total_cases"] == 1