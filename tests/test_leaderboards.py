"""Deterministic full-population ranking, filtering, pagination and local storage."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
from analytics.leaderboard_rankings import (build_frame,filter_and_rank,historical_age,paginate,export_csv,
                                            subset_percentile,ai_context)
from services.leaderboard_service import _season_population
from utils.leaderboard_presets import save_preset,load_presets,rename_preset,delete_preset
from tests.test_career_trends import hitter,pitcher


def fixture(category='hitting'):
    rows=[]
    for i in range(1,5):
        stat=hitter(ops=.9 if i<3 else .8) if category=='hitting' else pitcher(er=30 if i<3 else 50)
        stat.update(runs=50,stolenBases=10,wins=10,losses=3,saves=0,gamesStarted=10)
        if i==4:
            stat.update(ops=None,plateAppearances=0,atBats=0)
        rows.append({'season':'2024','stat':stat,'player':{'id':i,'fullName':f'Player {i}','birthDate':'1990-07-02','currentAge':99},
                     'team':{'id':1},'league':{'id':103},'sport':{'id':1},'gameType':'R',
                     'numTeams':2 if i==3 else 1,'position':{'abbreviation':'CF' if category=='hitting' else 'P'}})
    return {'season':2024,'category':category,'game_type':'R','rows':rows,'qualified_ids':[1,2,3],
            'population_n':4,'teams':{1:{'name':'Team A','league_id':103},2:{'name':'Team B','league_id':104}},
            'memberships':{3:[{'team_id':1,'league_id':103},{'team_id':2,'league_id':104}]},
            'sources':['https://statsapi.mlb.com/api/v1/stats'],'retrieved_at':'test-time',
            'cache_policy':'historical_24h','errors':[],'supplemental':None}


class LeaderboardTests(unittest.TestCase):
    def test_historical_age_not_current_age(self):
        self.assertEqual(historical_age('1990-07-02',2024),33)
        self.assertEqual(historical_age('1990-07-01',2024),34)
        self.assertIsNone(historical_age(None,2024))
        self.assertEqual(build_frame(fixture()).iloc[0]['age'],33)

    def test_qualification_sort_ties_and_missing(self):
        frame=build_frame(fixture())
        ranked=filter_and_rank(frame,'hitting',{},'OPS')
        self.assertEqual(ranked['id'].tolist(),[1,2,3])
        self.assertEqual(ranked['rank'].tolist(),[1,1,3])
        self.assertEqual(filter_and_rank(frame,'hitting',{'qualified':False},'OPS')['id'].tolist(),[1,2,3])
        self.assertEqual(filter_and_rank(frame,'hitting',{},'OPS',True)['id'].tolist(),[3,1,2])

    def test_team_league_position_age_and_threshold_filters(self):
        frame=build_frame(fixture())
        self.assertEqual(filter_and_rank(frame,'hitting',{'league':104},'OPS')['id'].tolist(),[3])
        self.assertEqual(filter_and_rank(frame,'hitting',{'team':2},'OPS')['id'].tolist(),[3])
        self.assertEqual(len(filter_and_rank(frame,'hitting',{'position':'OF','ages':[30,35],'min_pa':300},'OPS')),3)
        self.assertTrue(filter_and_rank(frame,'hitting',{'ages':[0,25]},'OPS').empty)
        self.assertEqual(filter_and_rank(frame,'hitting',{'thresholds':[{'metric':'OPS','min':.85,'max':None}]},'OPS')['id'].tolist(),[1,2])

    def test_incomplete_trades_cannot_form_false_filtered_population(self):
        data=fixture()
        data['memberships']={}
        frame=build_frame(data)
        self.assertEqual(len(filter_and_rank(frame,'hitting',{},'OPS')),3)
        with self.assertRaises(ValueError):filter_and_rank(frame,'hitting',{'team':1},'OPS')

    def test_pitcher_direction_and_baseball_innings(self):
        data=fixture('pitching')
        data['rows'][0]['stat'].update(inningsPitched='6.1',earnedRuns=2,era=2.84)
        frame=build_frame(data)
        self.assertAlmostEqual(frame.iloc[0]['IP'],19/3)
        self.assertEqual(frame.iloc[0]['IP_display'],'6.1')
        self.assertTrue(filter_and_rank(frame,'pitching',{'min_ip':100},'ERA')['IP'].ge(100).all())
        self.assertEqual(filter_and_rank(frame,'pitching',{},'ERA').iloc[0]['id'],2)

    def test_population_and_category_validation(self):
        data=fixture()
        data['rows'].append(data['rows'][0])
        with self.assertRaises(ValueError):build_frame(data)
        frame=build_frame(fixture())
        with self.assertRaises(ValueError):filter_and_rank(frame,'pitching',{},'ERA')
        data=fixture()
        data['rows'][0]['season']='2023'
        with self.assertRaises(ValueError):build_frame(data)

    def test_pagination_and_full_reference_percentiles(self):
        frame=filter_and_rank(build_frame(fixture()),'hitting',{},'OPS')
        repeated=__import__('pandas').concat([frame]*10,ignore_index=True)
        repeated['rank']=range(1,31)
        self.assertEqual(paginate(repeated,10,2)['rank'].tolist(),list(range(11,21)))
        self.assertEqual(subset_percentile(frame,3,'OPS',False),0)
        self.assertEqual(subset_percentile(frame,1,'OPS',False),75)

    def test_csv_is_full_filtered_bom_missing_and_metadata(self):
        data=fixture()
        ranked=filter_and_rank(build_frame(data),'hitting',{},'OPS')
        ranked.loc[0,'name']='=NotAFormula'
        ranked.loc[0,'age']=None
        content=export_csv(ranked,['OPS'],data,{},'OPS')
        self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
        rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]['name'],"'=NotAFormula")
        self.assertEqual(rows[0]['age'],'')
        self.assertEqual(rows[0]['retrieved_at'],'test-time')

    def test_ai_scope_is_complete_ranked_population_not_visible_slice(self):
        data=fixture()
        ranked=filter_and_rank(build_frame(data),'hitting',{},'OPS')
        context=ai_context(ranked,data,{'qualified':True},'OPS',False,3)
        self.assertEqual(context['eligible_n'],3)
        self.assertEqual(context['selected_player'][0]['rank'],3)
        json.dumps(context,allow_nan=False)

    @patch('services.leaderboard_service.requests.get')
    def test_all_api_pages_are_loaded(self,get):
        rows=fixture()['rows'][:3]
        responses=[]
        for part in (rows[:2],rows[2:]):
            response=Mock()
            response.url='source'
            response.json.return_value={'stats':[{'group':{'displayName':'hitting'},'type':{'displayName':'season'},'totalSplits':3,'splits':part}]}
            responses.append(response)
        get.side_effect=responses
        result=_season_population(2024,'hitting','ALL')
        self.assertEqual(len(result['rows']),3)
        self.assertEqual(get.call_args.kwargs['params']['offset'],2)

    @patch('services.leaderboard_service.requests.get')
    def test_partial_or_repeated_pages_are_rejected(self,get):
        response=Mock()
        response.url='test'
        response.json.return_value={'stats':[{'group':{'displayName':'hitting'},'type':{'displayName':'season'},'totalSplits':3,'splits':fixture()['rows'][:2]}]}
        get.return_value=response
        with self.assertRaises(ValueError):_season_population(2024,'hitting','ALL')

    def test_presets_persist_rename_and_confirmed_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'presets.json'
            config={'lb_season':2024,'lb_category':'hitting','lb_league':103}
            save_preset('한글 프리셋',config,path)
            self.assertEqual(load_presets(path)['한글 프리셋'],config)
            with self.assertRaises(ValueError):save_preset('한글 프리셋',{},path)
            rename_preset('한글 프리셋','New',path)
            with self.assertRaises(ValueError):delete_preset('New',path=path)
            self.assertIn('New',load_presets(path))
            delete_preset('New',confirmed=True,path=path)
            self.assertEqual(load_presets(path),{})

    def test_corrupt_preset_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'presets.json'
            path.write_text('broken',encoding='utf-8')
            with self.assertRaises(ValueError):save_preset('New',{},path)
            self.assertEqual(path.read_text(),'broken')
