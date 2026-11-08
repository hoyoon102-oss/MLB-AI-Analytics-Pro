"""Deterministic arithmetic fixtures; published constants, no live API."""
import unittest
import json
from pathlib import Path
from analytics.advanced_hitting import hitting_metrics
from analytics.advanced_pitching import pitching_metrics
from analytics.advanced_stats import metrics, baselines
from analytics.pitching import innings_to_outs
from utils.i18n import t


class AdvancedTests(unittest.TestCase):
    def test_verified_mlb_examples(self):
        # Snapshot retrieved from season=2024, gameType=R, MLB IDs 660271/543037.
        examples = json.loads(Path(__file__).with_name('advanced-verified-examples.json').read_text(encoding='utf-8'))
        hitter, pitcher = examples
        h = hitting_metrics(hitter['stats'], 2024)
        p = pitching_metrics(pitcher['stats'], 2024)
        self.assertAlmostEqual(h['ISO'], 214/636)
        self.assertAlmostEqual(h['BABIP'], 143/425)
        self.assertAlmostEqual(h['wOBA'], .43058077994428967)
        self.assertAlmostEqual(p['FIP'], 3.692315789473684)
        self.assertAlmostEqual(p['K-BB%'], 17.94871794871795)

    def test_hitting_arithmetic(self):
        s = dict(hits=100, homeRuns=20, atBats=400, strikeOuts=80, sacFlies=5,
                 baseOnBalls=50, plateAppearances=460, totalBases=180,
                 intentionalWalks=5, hitByPitch=5, doubles=20, triples=0)
        values = hitting_metrics(s, 2024)
        self.assertAlmostEqual(values['ISO'], .2)
        self.assertAlmostEqual(values['BABIP'], 80/305)
        self.assertAlmostEqual(values['BB%'], 50/460*100)
        self.assertAlmostEqual(values['K%'], 80/460*100)
        self.assertEqual(values['BB/K'], .625)
        self.assertAlmostEqual(values['wOBA'], (.689*45+.720*5+.882*60+1.254*20+2.050*20)/455)

    def test_fip_and_outs(self):
        # 2024 cFIP 3.166, verified against FanGraphs Guts snapshot.
        s = dict(inningsPitched='6.1', homeRuns=1, baseOnBalls=2,
                 hitBatsmen=1, strikeOuts=8, battersFaced=27)
        v = pitching_metrics(s, 2024)
        self.assertEqual(innings_to_outs('6.1'), 19)
        self.assertAlmostEqual(v['FIP'], (13+9-16)*3/19+3.166)
        self.assertAlmostEqual(v['K/9'], 216/19)
        self.assertAlmostEqual(v['K-BB%'], 600/27)
        self.assertIsNone(pitching_metrics(s, 1900)['FIP'])
        for ip in ('6.3', '6.33', None, True):
            self.assertIsNone(innings_to_outs(ip))

    def test_missing_zero_negative(self):
        self.assertTrue(all(v is None for v in hitting_metrics({}, 2024).values()))
        self.assertTrue(all(v is None for v in pitching_metrics({}, 2024).values()))
        self.assertIsNone(hitting_metrics(dict(baseOnBalls=0, plateAppearances=0), 2024)['BB%'])
        self.assertEqual(hitting_metrics(dict(baseOnBalls=0, plateAppearances=100), 2024)['BB%'], 0)
        self.assertIsNone(pitching_metrics(dict(inningsPitched='0.0', strikeOuts=2), 2024)['K/9'])
        self.assertIsNone(pitching_metrics(dict(inningsPitched='6.1', outs=20, strikeOuts=2), 2024)['K/9'])
        # FIP can legitimately be negative.
        self.assertLess(pitching_metrics(dict(inningsPitched='1.0', homeRuns=0, baseOnBalls=0, hitBatsmen=0, strikeOuts=3), 2024)['FIP'], 0)

    def test_baselines_matching(self):
        self.assertEqual(baselines(None, 2024, 'hitting')['OPS+']['value'], 100)
        league = dict(season=2024, category='hitting', game_type='R', totals=dict(baseOnBalls=20,plateAppearances=100), league_id=103)
        self.assertEqual(baselines(league, 2024, 'hitting')['BB%']['value'], 20)
        self.assertNotIn('BB%', baselines(league, 2023, 'hitting'))
        self.assertNotIn('BB%', baselines(league, 2024, 'pitching'))

    def test_metadata_and_language(self):
        data = metrics(dict(baseOnBalls=1,plateAppearances=10), 2024, 'hitting', 123, 'test-time')
        self.assertEqual(data['BB%']['player_id'], 123)
        self.assertEqual(data['BB%']['retrieved_at'], 'test-time')
        self.assertEqual(data['OPS+']['availability'], 'unavailable')
        self.assertNotEqual(t('advanced_hitting', locale='ko'), t('advanced_hitting', locale='en'))
        for key in data:
            self.assertNotEqual(t('metric_'+key, locale='en'), 'metric_'+key)
        with self.assertRaises(ValueError):
            metrics({'_group':'pitching'}, 2024, 'hitting')

    def test_identity_and_trades(self):
        from services.player_stats import extract_stats, DataError
        team = dict(season='2024', player={'id':123}, stat={'hits':4}, team={'id':1})
        total = dict(season='2024', player={'id':123}, stat={'hits':9})
        payload = {'stats':[{'group':{'displayName':'hitting'}, 'splits':[team, total]}]}
        self.assertEqual(extract_stats(payload, 2024, player_id=123)['hits'], 9)
        with self.assertRaises(DataError):
            extract_stats(payload, 2024, player_id=999)
        payload['stats'][0]['splits'] = [team, dict(team, team={'id':2})]
        with self.assertRaises(DataError):
            extract_stats(payload, 2024, player_id=123)

    def test_ai_context(self):
        from services.ai_analyst import player_context
        from components.league_ui import ai_league_context
        context = player_context({'id':123,'fullName':'Test'}, 2024,'hitting',
                                 {'baseOnBalls':5,'plateAppearances':20},'test')
        self.assertEqual(context['advanced_statistics']['BB%']['value'],25)
        league = dict(season=2024, category='hitting', totals={'baseOnBalls':10,'plateAppearances':100},
                      rates={},source='test',retrieved_at='test',team_count=30,population='test',limitations='test',league_id=0)
        self.assertEqual(ai_league_context(context,league)['advanced_differences']['BB%'],15)


if __name__ == '__main__':
    unittest.main()
