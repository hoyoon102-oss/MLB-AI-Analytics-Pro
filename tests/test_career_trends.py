"""Offline career fixtures: aggregation, ordering, gaps, qualifications and rules."""
import unittest
from unittest.mock import patch
from services.career_stats_service import extract_career,fetch_career
from analytics.career_trends import aggregate,metric_value,changes,rolling,peak,development,career_x,ai_context
from components.career_charts import timeline,awards_timeline


def hitter(pa=400,ab=350,hits=100,tb=180,**extra):
    row=dict(gamesPlayed=100,plateAppearances=pa,atBats=ab,hits=hits,totalBases=tb,baseOnBalls=40,strikeOuts=80,
             hitByPitch=5,sacFlies=5,homeRuns=10,rbi=50,doubles=20,triples=0,intentionalWalks=0,_group='hitting')
    row.update(extra)
    pooled=aggregate([row],'hitting')
    row.update({k:pooled[k] for k in ('avg','obp','slg','ops')})
    row.update(extra)
    return row


def pitcher(ip='100.0',er=40,**extra):
    row=dict(gamesPlayed=20,gamesPitched=20,gamesStarted=20,inningsPitched=ip,earnedRuns=er,baseOnBalls=30,
             hits=80,strikeOuts=110,battersFaced=400,homeRuns=10,hitBatsmen=3,atBats=350,sacFlies=5,_group='pitching')
    row.update(extra)
    pooled=aggregate([row],'pitching')
    row.update({k:pooled[k] for k in ('era','whip')})
    return row


def payload(rows,category='hitting'):
    return {'stats':[{'group':{'displayName':category},'type':{'displayName':'yearByYear'},'splits':rows}]}


def split(year,stat,team=1):
    r={'season':str(year),'stat':stat,'player':{'id':1},'gameType':'R','sport':{'id':1}}
    if team:
        r['team']={'id':team,'name':str(team)}
    return r


def career(records,category='hitting'):
    return {'player_id':1,'category':category,'game_type':'R','records':records,
            'career_totals':aggregate([r for r in records.values() if r],category),'problems':{},'incomplete':[],
            'first_season':min(records),'last_season':max(records),'played_seasons':sum(bool(r) for r in records.values()),
            'source':'test','retrieved_at':'test','total_method':'pooled','season_methods':{},'teams':{},
            'season_status':{},'calendar_error':None}


class CareerTests(unittest.TestCase):
    def test_historical_order_and_missing_seasons(self):
        c=extract_career(payload([split(2024,hitter()),split(2022,hitter())]),1,'hitting',2024)
        self.assertEqual(list(c['records']),[2022,2023,2024])
        self.assertIsNone(c['records'][2023])
        self.assertFalse(c['problems'])

    def test_multiteam_total_selected_once(self):
        p=payload([split(2024,hitter(hits=10),1),split(2024,hitter(hits=20),2),split(2024,hitter(hits=30),None)])
        c=extract_career(p,1,'hitting',2024)
        self.assertEqual(c['records'][2024]['hits'],30)
        self.assertEqual(c['career_totals']['hits'],30)
        self.assertEqual(c['teams'][2024],['1','2'])

    def test_distinct_team_counts_fallback_and_ambiguous_duplicates(self):
        rows=[split(2024,hitter(hits=10),1),split(2024,hitter(hits=20),2)]
        c=extract_career(payload(rows),1,'hitting',2024)
        self.assertEqual(c['records'][2024]['hits'],30)
        self.assertIsNone(c['records'][2024]['gamesPlayed'])
        c=extract_career(payload([rows[0],rows[0]]),1,'hitting',2024)
        self.assertIn(2024,c['problems'])
        self.assertIsNone(c['records'][2024])

    def test_source_identity_category_and_regular_season(self):
        bad=split(2024,hitter())
        bad['player']['id']=2
        with self.assertRaises(ValueError):extract_career(payload([bad]),1,'hitting',2024)
        with self.assertRaises(ValueError):extract_career(payload([]),1,'pitching',2024)
        postseason=split(2024,hitter())
        postseason['gameType']='W'
        self.assertEqual(extract_career(payload([postseason]),1,'hitting',2024)['records'],{})
        with self.assertRaises(ValueError):aggregate([pitcher()],'hitting')

    def test_pooled_career_rates_not_season_averages(self):
        a=hitter(pa=120,ab=100,hits=10,tb=20)
        b=hitter(pa=1000,ab=900,hits=300,tb=500)
        result=aggregate([a,b],'hitting')
        self.assertAlmostEqual(result['avg'],.31)
        self.assertAlmostEqual(result['slg'],.52)
        self.assertAlmostEqual(metric_value(result,2024,'hitting','ISO'),.21)
        self.assertNotAlmostEqual(result['avg'],(a['avg']+b['avg'])/2)
        self.assertAlmostEqual(result['obp'],(310+80+10)/(1000+80+10+10))

    def test_pitching_outs_and_zero_denominators(self):
        c=aggregate([pitcher('6.1',2),pitcher('3.2',1)],'pitching')
        self.assertEqual(c['inningsPitched'],'10.0')
        self.assertAlmostEqual(c['era'],2.7)
        self.assertIsNone(aggregate([pitcher('0.0',0)],'pitching')['era'])
        with self.assertRaises(ValueError):aggregate([pitcher('6.3')],'pitching')
        poor=aggregate([pitcher(strikeOuts=10,baseOnBalls=30)],'pitching')
        self.assertEqual(metric_value(poor,2024,'pitching','K-BB%'),-5)

    def test_year_over_year_direction_and_percentage_rules(self):
        records={2021:pitcher(er=30),2022:None,2023:pitcher(er=50)}
        c=changes(records,'pitching','ERA')[0]
        self.assertEqual(c['gap_years'],2)
        self.assertEqual(c['direction'],'decline')
        self.assertAlmostEqual(c['difference'],1.8)
        self.assertAlmostEqual(c['percentage_change'],200/3)
        self.assertIsNone(changes({2021:hitter(),2022:hitter(baseOnBalls=0)},'hitting','BB%')[0]['percentage_change'])

    def test_peak_sample_qualification_ties_and_incomplete(self):
        records={2020:hitter(pa=299,ops=2),2021:hitter(ops=1),2022:hitter(ops=1),2023:hitter(ops=2)}
        self.assertEqual([r['season'] for r in peak(records,'hitting','OPS',[2023])],[2021,2022])
        self.assertEqual(peak(records,'hitting','OPS+'),[])

    def test_rolling_uses_consecutive_count_totals(self):
        records={2020:hitter(ab=100,hits=10),2021:hitter(ab=900,hits=300),2022:hitter(ab=100,hits=10)}
        self.assertAlmostEqual(rolling(records,'hitting','AVG')[2022],320/1100)
        records[2021]=None
        self.assertIsNone(rolling(records,'hitting','AVG')[2022])

    def test_breakout_requires_context_sample_baseline_and_direction(self):
        records={2020:hitter(ops=.7),2021:hitter(ops=.7),2022:hitter(ops=.9)}
        leagues={y:{'season':y,'category':'hitting','rates':{'ops':.7},'source':'test'} for y in records}
        d=development(records,'hitting',leagues)
        self.assertEqual(d['breakouts'][0]['season'],2022)
        self.assertEqual(len(d['changes']),1)
        self.assertFalse(development(records,'hitting',{})['breakouts'])
        records[2022]['plateAppearances']=299
        self.assertFalse(development(records,'hitting',leagues)['breakouts'])
        records[2022]['plateAppearances']=400
        self.assertFalse(development(records,'hitting',leagues,unknown=[2021])['breakouts'])

    def test_career_year_alignment_and_awards(self):
        self.assertEqual(career_x(2024,2018,'experience'),7)
        self.assertEqual(career_x(2024,2018,'calendar'),2024)
        a={'season':2023,'date':'2024-01-01','name':'Verified Award','category':'MVP'}
        self.assertEqual(list(awards_timeline([a]).data[0].x),[2023])
        c=career({2022:hitter(),2023:None,2024:hitter()})
        self.assertIsNone(timeline(c,'OPS',2022,2024).data[0].y[1])
        self.assertFalse(timeline(c,'OPS',2022,2024).data[0].connectgaps)

    def test_compact_ai_context_uses_python_deltas(self):
        c=career({2021:hitter(ops=.7),2022:hitter(ops=.9)})
        ctx=ai_context({'id':1,'fullName':'Test'},c,'OPS')
        self.assertAlmostEqual(ctx['year_over_year'][0]['difference'],.2)
        self.assertNotIn('records',ctx['career_summary'])
        with self.assertRaises(ValueError):ai_context({'id':2,'fullName':'Wrong'},c,'OPS')

    @patch('services.career_stats_service.season_calendar',return_value={2024:{'regularSeasonEndDate':'2024-09-30'}})
    @patch('services.career_stats_service.api_json')
    def test_fetch_caches_category_and_marks_incomplete(self,api,calendar):
        fetch_career.clear()
        api.return_value=payload([split(2024,hitter())])
        c=fetch_career(1,'hitting','2024-07-01')
        self.assertEqual(c['incomplete'],[2024])
        fetch_career(1,'hitting','2024-07-01')
        self.assertEqual(api.call_count,1)
