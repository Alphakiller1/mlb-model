import json

from mlbmodel.market.lines_cache import write_lines_cache
from scripts.lines_nonempty import line_count


def test_wrapped_cache_with_lines_counts_lines(tmp_path):
    path = tmp_path / "pp.json"
    write_lines_cache([{"player": "a"}, {"player": "b"}], path)
    assert line_count(path) == 2


def test_wrapped_cache_with_no_lines_counts_zero(tmp_path):
    """The regression that emptied the PrizePicks board.

    A blocked fetch still writes {"snapshot_at": ..., "lines": []}; the deploy workflow used
    to call len() on the parsed payload, which counted the wrapper's 2 KEYS and reported the
    fetch as successful — overwriting a good committed snapshot with zero lines.
    """
    path = tmp_path / "pp.json"
    write_lines_cache([], path)
    assert json.loads(path.read_text(encoding="utf-8")).keys()  # wrapper is non-empty...
    assert line_count(path) == 0  # ...but it holds no lines


def test_legacy_bare_list_snapshot_counts_entries(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps([{"player": "a"}]), encoding="utf-8")
    assert line_count(path) == 1


def test_missing_or_corrupt_file_counts_zero(tmp_path):
    assert line_count(tmp_path / "nope.json") == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert line_count(bad) == 0
