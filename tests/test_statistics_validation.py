"""Hand-verifiable examples exercise existing formulas, not new ones."""
import pytest
from services.league_stats import rates_from_totals
from analytics.career_trends import aggregate
from analytics.advanced_hitting import hitting_metrics
from analytics.advanced_pitching import pitching_metrics

pytestmark = pytest.mark.unit

def test_hitting_reference():
    s = dict(hits=100, atBats=400, baseOnBalls=50, hitByPitch=5, sacFlies=5,
             totalBases=180, plateAppearances=460, strikeOuts=80)
    r = rates_from_totals(s, 'hitting')
    assert r['avg'] == .25
    assert r['obp'] == pytest.approx(155 / 460)
    assert r['slg'] == .45
    assert r['ops'] == pytest.approx(155 / 460 + .45)
    assert r['bbPercent'] == pytest.approx(50 / 460 * 100)
    assert r['kPercent'] == pytest.approx(80 / 460 * 100)

def test_pitching_reference():
    r = rates_from_totals(dict(outs=19, earnedRuns=2, hits=5, baseOnBalls=2, strikeOuts=8), 'pitching')
    assert r['era'] == pytest.approx(54 / 19)
    assert r['whip'] == pytest.approx(21 / 19)
    assert r['strikeoutsPer9Inn'] == pytest.approx(216 / 19)
    assert r['walksPer9Inn'] == pytest.approx(54 / 19)

def test_weighted_short_season():
    r = aggregate([dict(hits=1, atBats=2), dict(hits=1, atBats=8)], 'hitting')
    assert r['avg'] == .2
    assert r['obp'] is None

@pytest.mark.parametrize('category', ['hitting', 'pitching'])
def test_zero_and_missing(category):
    assert all(v is None for v in rates_from_totals({}, category).values())
    assert all(v is None for v in rates_from_totals(dict(atBats=0, outs=0), category).values())

def test_unavailable_adjusted_metrics():
    assert hitting_metrics({}, 1900)['OPS+'] is None
    assert hitting_metrics({}, 1900)['wRC+'] is None
    assert hitting_metrics({}, 1900)['wOBA'] is None
    assert pitching_metrics({}, 1900)['ERA+'] is None
    assert pitching_metrics({}, 1900)['FIP'] is None
