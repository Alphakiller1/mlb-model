from mlbmodel.sources.sync_mlbma import (
    current_pipeline_rows,
    matchup_keys,
    merge_pipeline_slate,
    pipeline_metadata,
)


def test_exact_pipeline_slate_enriches_live_schedule_identity():
    schedule = [{
        "Game_PK": 101,
        "MLB_Game_PK": 7001,
        "Game_Number": 1,
        "Slate_Date": "2026-06-27",
        "Time": "1:00 PM ET",
        "Away": "NYY",
        "Home": "BOS",
        "Away_SP": "API Away",
        "Home_SP": "API Home",
        "Away_FIP": "",
    }]
    pipeline = [{
        "Slate_Date": "2026-06-27",
        "Time": "1:10 PM ET",
        "Away": "NYY",
        "Home": "BOS",
        "Away_SP": "Pipeline Away",
        "Home_SP": "Pipeline Home",
        "Away_FIP": "3.25",
    }]

    merged, exact = merge_pipeline_slate(schedule, pipeline)

    assert exact is True
    assert merged[0]["Game_PK"] == 101
    assert merged[0]["MLB_Game_PK"] == 7001
    assert merged[0]["Away_SP"] == "Pipeline Away"
    assert merged[0]["Away_FIP"] == "3.25"
    assert merged[0]["Time"] == "1:10 PM ET"


def test_authoritative_handedness_survives_pipeline_merge():
    # The MLB Stats API people record (resolved in build_rows) is the source of truth
    # for handedness; the pipeline's hand column is unreliable (lefties mislabeled R).
    # An exact slate match must NOT let the pipeline overwrite the schedule-sourced hand.
    schedule = [{
        "Game_PK": 101, "MLB_Game_PK": 7001, "Game_Number": 1,
        "Slate_Date": "2026-06-27", "Away": "HOU", "Home": "DET",
        "Away_SP": "Kai-Wei Teng", "Home_SP": "Framber Valdez",
        "Away_Hand": "R", "Home_Hand": "L",  # Valdez is a lefty
        "Away_FIP": "",
    }]
    pipeline = [{
        "Slate_Date": "2026-06-27", "Away": "HOU", "Home": "DET",
        "Home_Hand": "R",  # wrong upstream hand must be ignored
        "Away_FIP": "4.63",
    }]

    merged, exact = merge_pipeline_slate(schedule, pipeline)

    assert exact is True
    assert merged[0]["Home_Hand"] == "L"  # preserved, not clobbered to R
    assert merged[0]["Away_FIP"] == "4.63"  # other pipeline values still enrich


def test_mismatch_keeps_live_schedule_as_chase_fallback():
    schedule = [{"Away": "NYY", "Home": "BOS"}]
    pipeline = [{"Away": "TOR", "Home": "BAL"}]

    merged, exact = merge_pipeline_slate(schedule, pipeline)

    assert exact is False
    assert merged == schedule


def test_pipeline_date_filter_and_doubleheader_keys():
    rows = [
        {"Slate_Date": "2026-06-26", "Away": "NYY", "Home": "BOS"},
        {"Slate_Date": "2026-06-27", "Away": "NYY", "Home": "BOS"},
        {"Slate_Date": "2026-06-27", "Away": "NYY", "Home": "BOS"},
    ]

    current = current_pipeline_rows(rows, "2026-06-27")

    assert matchup_keys(current) == ["NYY@BOS", "NYY@BOS#2"]


def test_pipeline_metadata_reads_last_updated_matrix():
    metadata = pipeline_metadata([
        ["Last Updated", "2026-06-27 07:13:13"],
        ["Slate_Date_ET", "2026-06-27"],
    ])

    assert metadata["Slate_Date_ET"] == "2026-06-27"
