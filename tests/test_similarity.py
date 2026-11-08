import json
import unittest
import numpy as np
from tests.test_percentiles import bundle
from analytics.percentiles import profile
from analytics.player_similarity import similar_players,ai_context,FEATURES


class SimilarityTests(unittest.TestCase):
    def test_standardization_and_score(self):
        b=bundle()
        b['raw']['players'][2].update(exit_velocity_avg='86',bb_percent='6',k_percent='16')
        result=similar_players(b,1)
        self.assertEqual(result['status'],'available')
        self.assertEqual(result['results'][0]['player']['id'],2)
        self.assertEqual(result['results'][0]['score'],1)
        self.assertEqual(result['results'][0]['distance'],0)
        self.assertNotIn(1,[r['player']['id'] for r in result['results']])
        self.assertAlmostEqual(result['means']['avg_ev'],np.mean([86,86,88,89,90,91]))
        self.assertAlmostEqual(result['std']['avg_ev'],np.std([86,86,88,89,90,91],ddof=0))
        last=result['results'][-1]
        expected=np.sqrt(np.mean([(last['z'][k]-result['target_z'][k])**2 for k in FEATURES]))
        self.assertAlmostEqual(last['score'],1/(1+expected))

    def test_missing_features_not_imputed_and_thresholds(self):
        b=bundle()
        b['raw']['players'][2]['bb_percent']=''
        result=similar_players(b,1)
        self.assertEqual(result['eligible_n'],5)
        self.assertNotIn(2,[r['player']['id'] for r in result['results']])
        b['raw']['players'][1]['pa']='299'
        self.assertEqual(similar_players(b,1)['status'],'unqualified_missing_or_insufficient')

    def test_fixed_features_and_zero_variance(self):
        b=bundle()
        for row in b['raw']['players'].values():
            row['exit_velocity_avg']='90'
        self.assertEqual(similar_players(b,1)['status'],'constant_feature')

    def test_tied_distances_resolve_by_id(self):
        b=bundle()
        b['raw']['players'][2].update(exit_velocity_avg='87',bb_percent='7',k_percent='17')
        b['raw']['players'][3].update(exit_velocity_avg='87',bb_percent='7',k_percent='17')
        result=similar_players(b,1)
        self.assertEqual([r['player']['id'] for r in result['results'][:2]],[2,3])

    def test_same_season_category_only(self):
        b=bundle('pitching')
        self.assertEqual(similar_players(b,1)['category'],'pitching')
        b['raw']['season']=2023
        with self.assertRaises(ValueError):
            similar_players(b,1)

    def test_ai_context_only_contains_verified_results(self):
        b=bundle()
        p=profile(b,1)
        s=similar_players(b,1)
        context=ai_context({'id':1,'fullName':'Test'},p,s)
        self.assertEqual(context['similarity']['results'],s['results'])
        self.assertLess(len(json.dumps(context)),25000)
        with self.assertRaises(ValueError):
            ai_context({'id':2,'fullName':'Wrong'},p,s)
