"""Deterministic qualification, direction, ties, missing values and source joins."""
import unittest
from unittest.mock import patch
from services.leaderboard_service import validate_table,fetch_table
from analytics.percentiles import local_percentile,profile,raw_values


def bundle(category='hitting'):
    rows={i:{'player_id':str(i),'year':'2024','last_name, first_name':f'Player {i}',
              'pa':'400','exit_velocity_avg':str(85+i),'bb_percent':str(5+i),'k_percent':str(15+i)} for i in range(1,7)}
    official={i:{'player_id':str(i),'year':'2024','player_name':f'Player {i}',
                  'k_percent':str(100-i),'exit_velocity':str(i*10)} for i in rows}
    common={'season':2024,'category':category,'game_type':'R','source':'test-source','retrieved_at':'test-time'}
    return dict(common,official=dict(common,players=official),raw=dict(common,players=rows),contact=None,metadata={},errors=[])


class PercentileTests(unittest.TestCase):
    def test_local_direction_and_ties(self):
        self.assertEqual(local_percentile(10,[10,10,20],'higher'),25)
        self.assertEqual(local_percentile(10,[10,10,20],'lower'),75)
        self.assertEqual(local_percentile(20,[10,10,20],'higher'),100)
        self.assertEqual(local_percentile(5,[5,5,5],'higher'),50)
        self.assertIsNone(local_percentile(1,[1],'higher'))
        self.assertIsNone(local_percentile(None,[1,2],'higher'))

    def test_official_lower_metric_is_never_inverted_twice(self):
        result=profile(bundle(),1)
        self.assertEqual(result['metrics']['k']['percentile'],99)
        self.assertEqual(result['metrics']['k']['direction'],'lower')
        self.assertEqual(result['metrics']['k']['population_n'],6)
        self.assertEqual(result['metrics']['k']['actual'],16)

    def test_local_qualification_and_missing_values(self):
        b=bundle()
        b['raw']['players'][1]['pa']='299'
        self.assertIsNone(profile(b,1,'local')['metrics']['k']['percentile'])
        b['raw']['players'][1]['pa']='300'
        b['raw']['players'][2]['k_percent']=''
        result=profile(b,1,'local')
        self.assertEqual(result['metrics']['k']['population_n'],5)
        self.assertIsNotNone(result['metrics']['k']['percentile'])

    def test_pitcher_population_and_direction(self):
        b=bundle('pitching')
        b['raw']['players'][1]['pa']='200'
        result=profile(b,1,'local')
        self.assertEqual(result['metrics']['k']['direction'],'higher')
        self.assertEqual(result['metrics']['bb']['direction'],'lower')
        self.assertIsNone(result['metrics']['fb_spin']['percentile'])
        b['raw']['category']='hitting'
        with self.assertRaises(ValueError):
            profile(b,1)

    def test_season_id_and_duplicate_validation(self):
        self.assertEqual(validate_table([{'player_id':'1','year':'2024'}],2024)[1]['year'],'2024')
        self.assertEqual(validate_table([{'player_id':'999999'}],2024),{})
        for rows in ([{'player_id':'1','year':'2023'}],[{'player_id':'1','year':'2024'}]*2,[{'player_id':'bad','year':'2024'}]):
            with self.assertRaises(ValueError):
                validate_table(rows,2024)
        b=bundle()
        b['official']['season']=2023
        with self.assertRaises(ValueError):
            profile(b,1)

    def test_partial_official_qualification_is_metric_specific(self):
        b=bundle()
        b['official']['players'][1]['k_percent']=''
        b['official']['players'][1]['max_ev']='88'
        result=profile(b,1)
        self.assertIsNone(result['metrics']['k']['percentile'])
        self.assertEqual(result['metrics']['max_ev']['percentile'],88)
        b['contact']={'season':2024,'category':'hitting','rows':[{'player_id':'1','max_hit_speed':'119.2'}],'source':'contact'}
        self.assertEqual(raw_values(b)[1]['max_ev'],119.2)
        b['raw']=None
        self.assertEqual(raw_values(b)[1]['max_ev'],119.2)

    def test_invalid_raw_measurements_are_missing_not_zero(self):
        b=bundle()
        b['raw']['players'][1]['bb_percent']='101'
        b['raw']['players'][1]['exit_velocity_avg']='-1'
        self.assertIsNone(raw_values(b)[1]['bb'])
        self.assertIsNone(raw_values(b)[1]['avg_ev'])
        self.assertIsNone(profile(b,1,'local')['metrics']['bb']['percentile'])

    @patch('services.leaderboard_service.csv_request')
    def test_source_cache_is_season_category_specific(self,request):
        fetch_table.clear()
        request.return_value=(['player_id','year','player_name'],[{'player_id':'1','year':'2024','player_name':'Test'}],'source')
        fetch_table(2024,'hitting','percentiles')
        fetch_table(2024,'hitting','percentiles')
        self.assertEqual(request.call_count,1)
        fetch_table(2024,'pitching','percentiles')
        self.assertEqual(request.call_count,2)
