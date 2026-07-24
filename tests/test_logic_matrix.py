from mlbmodel.genesis.logic_matrix import (
    ALLOWED_METRIC_WEIGHTS,
    CONVERGENCE_THRESHOLD,
    OSI_WEIGHTS,
    PITCHING_WEIGHTS,
    composite_metric_weight,
)


def test_osi_weights_match_pipeline_lineage():
    assert sum(OSI_WEIGHTS.values()) == 1.0
    assert OSI_WEIGHTS["obr"] >= OSI_WEIGHTS["rcv"] >= OSI_WEIGHTS["abq"]


def test_pitching_weights_match_pipeline_lineage():
    assert sum(PITCHING_WEIGHTS.values()) == 1.0
    assert PITCHING_WEIGHTS["k_pct"] == PITCHING_WEIGHTS["inv_whip"]


def test_composite_metric_weights_derive_from_osi():
    assert composite_metric_weight("abq") == OSI_WEIGHTS["abq"] * 0.45
    assert composite_metric_weight("obr") == OSI_WEIGHTS["obr"] * 0.45


def test_allowed_metric_weights_use_osi_abq_lineage():
    assert ALLOWED_METRIC_WEIGHTS["ABQ_allowed"] == OSI_WEIGHTS["abq"]


def test_convergence_threshold_matches_pipeline():
    assert CONVERGENCE_THRESHOLD == 4
