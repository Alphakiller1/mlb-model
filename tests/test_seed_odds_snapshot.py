import json

from scripts.seed_odds_snapshot import freshest_snapshot, promote_snapshot


def _write(path, fetched_at, *, events=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": fetched_at, "events": [{"id": "game"}] if events else []}),
        encoding="utf-8",
    )


def test_freshest_snapshot_rejects_empty_and_selects_newest(tmp_path):
    stale = tmp_path / "stale.json"
    fresh = tmp_path / "fresh.json"
    empty = tmp_path / "empty.json"
    _write(stale, "2026-08-20T21:12:37+00:00")
    _write(fresh, "2026-08-25T16:49:21+00:00")
    _write(empty, "2026-08-26T16:49:21+00:00", events=False)

    assert freshest_snapshot([stale, empty, fresh]) == fresh


def test_promote_snapshot_replaces_stale_deploy_seed(tmp_path):
    destination = tmp_path / "deploy" / "odds_latest.json"
    candidate = tmp_path / "data" / "odds_latest.json"
    _write(destination, "2026-08-20T21:12:37+00:00")
    _write(candidate, "2026-08-25T16:49:21+00:00")

    assert promote_snapshot(destination, [candidate]) == candidate
    assert json.loads(destination.read_text(encoding="utf-8"))["fetched_at"].startswith("2026-08-25")


def test_promote_snapshot_keeps_newer_deploy_seed(tmp_path):
    destination = tmp_path / "deploy" / "odds_latest.json"
    candidate = tmp_path / "data" / "odds_latest.json"
    _write(destination, "2026-08-26T16:49:21+00:00")
    _write(candidate, "2026-08-25T16:49:21+00:00")

    assert promote_snapshot(destination, [candidate]) == destination
