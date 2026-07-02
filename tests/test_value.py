from mlbmodel.market.value import assess_value


def test_unpromoted_positive_edge_is_monitor_only():
    result = assess_value(
        0.57,
        -110,
        0.52,
        promotion_status="HOLD/ABSTAIN",
    )
    assert result.raw_state == "PLAY"
    assert result.action == "MONITOR"


def test_promoted_positive_edge_can_be_bet():
    result = assess_value(0.57, -110, 0.52, promotion_status="PROMOTE")
    assert result.action == "BET"


def test_no_price_is_no_edge():
    result = assess_value(0.57, None, None, promotion_status="PROMOTE")
    assert result.action == "NO EDGE"
