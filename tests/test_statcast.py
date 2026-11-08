"""Synthetic edge cases; no external network in automated Statcast tests."""
from datetime import date
import json
import unittest
import requests
from unittest.mock import patch, MagicMock

from services import statcast_service as service
from analytics.statcast_hitting import hitting_summary, published_metrics
from analytics.statcast_pitching import pitching_summary, arsenal, location_summary
from analytics.statcast_context import ai_context
from components import statcast_charts as charts
from utils.i18n import t, catalog


def row(**overrides):
    result = dict(game_pk='1',at_bat_number='1',pitch_number='1',batter='660271',pitcher='694973',
                  game_date='2024-05-11',game_type='R',type='X',events='single',pitch_type='FF',pitch_name='4-Seam Fastball',
                  launch_speed='95',launch_angle='8',launch_speed_angle='6',bb_type='line_drive',
                  release_speed='100',release_spin_rate='2400',release_extension='6',
                  pfx_x='-1',pfx_z='1.5',plate_x='0',plate_z='2.5',sz_bot='1.5',sz_top='3.5',
                  hc_x='125',hc_y='99',description='hit_into_play')
    result.update(overrides)
    return result


def dataset(rows=None):
    return {'player_id':660271,'season':2024,'category':'hitting','game_type':'R',
            'start':'2024-05-01','end':'2024-05-31','rows':rows if rows is not None else [row()],
            'quality':{},'sources':['https://baseballsavant.mlb.com/statcast_search/csv'], 'retrieved_at':'test'}


def published(category='hitting', player_id=660271):
    return {'season':2024,'category':category,'player_id':player_id,'tables':{},'errors':[]}


class StatcastTests(unittest.TestCase):
    def setUp(self):
        service.fetch_chunk.clear()
        service.published_table.clear()

    def test_date_chunks_have_no_overlap_or_gap(self):
        start,end=service.date_range(2024,'2024-02-01','2024-03-31')
        self.assertEqual(list(service.chunks(start,end)),[(date(2024,2,1),date(2024,3,2)),(date(2024,3,3),date(2024,3,31))])
        for args in [(2024,'2023-12-31','2024-01-02'),(2024,'2024-02-02','2024-02-01'),(2014,'2014-01-01','2014-01-02')]:
            with self.assertRaises(service.StatcastError):
                service.date_range(*args)

    def test_csv_bom_and_nulls(self):
        fields,rows=service.parse_csv('\ufeff"pitch_type","release_speed"\n"FF",""\n')
        self.assertEqual(fields,['pitch_type','release_speed'])
        self.assertEqual(rows[0]['release_speed'],'')
        with self.assertRaises(service.StatcastError):
            service.parse_csv('<html>error</html>')

    def test_player_identity_and_scope_filtering(self):
        records=[row(),row(pitch_number='2',game_type='W'),row(pitch_number='3',game_date='2023-05-11')]
        rows,quality=service.validate_rows(records,660271,2024,'hitting',date(2024,1,1),date(2024,12,31))
        self.assertEqual(len(rows),1)
        self.assertEqual(quality['excluded_scope'],2)
        with self.assertRaises(service.StatcastError):
            service.validate_rows([row(batter='999')],660271,2024,'hitting',date(2024,1,1),date(2024,12,31))
        self.assertEqual(len(service.validate_rows([row()],694973,2024,'pitching',date(2024,1,1),date(2024,12,31))[0]),1)

    def test_duplicates_are_stable_identifiers_not_equal_measurements(self):
        rows,q=service.validate_rows([row(),row(),row(pitch_number='2')],660271,2024,'hitting',date(2024,1,1),date(2024,12,31))
        self.assertEqual(len(rows),2)
        self.assertEqual(q['duplicates_removed'],1)
        for invalid in [row(launch_speed='96'),row(pitch_number='')]:
            with self.assertRaises(service.StatcastError):
                service.validate_rows([row(),invalid],660271,2024,'hitting',date(2024,1,1),date(2024,12,31))

    @patch('services.statcast_service.csv_request')
    def test_player_query_parameters_and_cache(self,request):
        request.return_value=(list(row()),[row()],'source')
        for _ in range(2):
            result=service.fetch_chunk(660271,2024,'hitting','2024-05-11','2024-05-11')
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(request.call_count,1)
        params=request.call_args.args[1]
        self.assertEqual(params['batters_lookup[]'],660271)
        self.assertEqual(params['hfGT'],'R|')
        self.assertEqual(params['game_date_gt'],'2024-05-11')

    @patch('services.statcast_service.fetch_chunk')
    @patch('services.statcast_service.time.sleep')
    def test_period_failure_never_returns_partial_totals(self,sleep,fetch):
        fetch.side_effect=[{'rows':[row()],'quality':{'excluded_scope':0,'duplicates_removed':0},'source':'test','retrieved_at':'now'},service.StatcastError('sc_network_error')]
        with self.assertRaises(service.StatcastError):
            service.fetch_period(660271,2024,'hitting','2024-05-01','2024-06-15')

    def test_exit_velocity_and_official_barrel_classification(self):
        result=hitting_summary([row(),row(launch_speed='94.9',launch_angle='32',launch_speed_angle='1'),
                                row(launch_speed='',launch_angle='',launch_speed_angle='')])
        self.assertEqual(result['bbe'],3)
        self.assertAlmostEqual(result['metrics']['avg_ev']['value'],94.95)
        self.assertEqual(result['metrics']['hard_hit']['value'],50)
        self.assertEqual(result['metrics']['sweet_spot']['value'],100)
        self.assertEqual(result['metrics']['barrel']['value'],50)
        self.assertEqual(result['metrics']['barrel']['n'],2)
        # Arbitrary high EV/angle must never create a barrel without the source code.
        self.assertIsNone(hitting_summary([row(launch_speed='115',launch_angle='25',launch_speed_angle='')])['metrics']['barrel']['value'])

    def test_pitch_metrics_and_whiff_denominator(self):
        rows=[row(description='swinging_strike'),row(description='foul'),row(description='called_strike'),
              row(description='ball',release_speed='',release_spin_rate='')]
        result=pitching_summary(rows)['metrics']
        self.assertEqual(result['whiff']['n'],2)
        self.assertEqual(result['whiff']['value'],50)
        self.assertEqual(result['spin']['n'],3)
        self.assertEqual(result['horizontal']['value'],-12)
        self.assertEqual(result['vertical']['value'],18)
        self.assertIsNone(pitching_summary([row(description='called_strike')])['metrics']['whiff']['value'])

    def test_arsenal_usage_unknowns_and_missing_values(self):
        result=arsenal([row(),row(pitch_type='ST',pitch_name='Sweeper'),row(pitch_type='',pitch_name='')])
        self.assertEqual({r['pitch_type'] for r in result},{'FF','ST','UN'})
        self.assertAlmostEqual(sum(r['usage']['value'] for r in result),100)
        self.assertEqual(result[0]['usage']['n'],3)
        self.assertTrue(all(m['value'] is None for m in pitching_summary([])['metrics'].values()))
        self.assertIsNone(hitting_summary([row(launch_speed='nan')])['metrics']['avg_ev']['value'])

    def test_published_values_never_locally_reconstructed(self):
        p=published()
        p['tables']['expected']={'row':{'est_ba':'.300','est_slg':'.550','est_woba':'.400','pa':'600'},'source':'source','retrieved_at':'test'}
        metrics=published_metrics(p)
        self.assertEqual(metrics['xba']['value'],.3)
        self.assertEqual(metrics['xba']['classification'],'source_published')
        self.assertEqual(metrics['xba']['n'],600)
        self.assertIsNone(metrics['barrel']['value'])
        self.assertIsNone(published_metrics(published('pitching',694973))['xera']['value'])

    @patch('services.statcast_service.published_table')
    def test_published_player_id_season_and_failure(self,fetch):
        fetch.return_value={'rows':[{'player_id':'999','year':'2024'},{'player_id':'660271','year':'2024','est_ba':'.310'}], 'source':'test','retrieved_at':'now'}
        result=service.published_player(2024,'hitting',660271)
        self.assertEqual(published_metrics(result)['xba']['value'],.31)
        fetch.return_value={'rows':[{'player_id':'660271','year':'2023'}]}
        self.assertTrue(service.published_player(2024,'hitting',660271)['errors'])

    def test_real_coordinate_transform_and_missing(self):
        self.assertEqual(charts.spray_point(row()),(0,100))
        self.assertIsNone(charts.spray_point(row(hc_x='')))
        self.assertEqual(charts.location_point(row(),True),(0,.5))
        self.assertIsNone(charts.location_point(row(sz_top='1.5'),True))
        self.assertIsNone(charts.location_point(row(plate_x=''),False))
        self.assertEqual(location_summary([row()])['center_in_measured_rectangle_pct'],100)
        self.assertIsNone(location_summary([row(sz_top='')])['center_in_measured_rectangle_pct'])

    def test_charts_preserve_gaps_and_zone_sample(self):
        fig=charts.monthly_chart([row()],'avg_ev','2024-04-01','2024-06-30')
        self.assertEqual(list(fig.data[0].y),[None,95,None])
        self.assertFalse(fig.data[0].connectgaps)
        self.assertEqual(charts.locations([row()],['FF'],True,True).data[0].type,'scatter')
        self.assertEqual(charts.movement([row()],['FF']).data[0].x[0],-12)
        self.assertIsNone(charts.spray([row(hc_x='')]))

    def test_ai_context_is_compact_and_language_complete(self):
        context=ai_context({'id':660271,'fullName':'Test'},dataset([row()]*1000),published())
        self.assertNotIn('rows',context['statcast'])
        self.assertLess(len(json.dumps(context)),15000)
        self.assertEqual(context['statcast']['observed']['metrics']['hard_hit']['value'],100)
        self.assertNotEqual(t('sc_hitting',locale='ko'),t('sc_hitting',locale='en'))
        self.assertEqual(set(catalog('ko')),set(catalog('en')))
        with self.assertRaises(ValueError):
            ai_context({'id':999,'fullName':'Wrong Player'},dataset(),published())

    @patch('services.statcast_service.requests.get')
    def test_access_limits_do_not_retry_or_bypass(self,get):
        response=MagicMock()
        response.status_code=429
        get.return_value.__enter__.return_value=response
        with self.assertRaises(service.StatcastError):
            service.csv_request('/statcast_search/csv',{})
        self.assertEqual(get.call_count,1)

    @patch('services.statcast_service.time.sleep')
    @patch('services.statcast_service.requests.get')
    def test_transient_retry_and_bounded_response(self,get,sleep):
        response=MagicMock()
        response.status_code=200
        response.url='verified-source'
        response.iter_content.return_value=[b'col\nvalue\n']
        manager=MagicMock()
        manager.__enter__.return_value=response
        get.side_effect=[requests.Timeout(),manager]
        fields,rows,source=service.csv_request('/statcast_search/csv',{})
        self.assertEqual(fields,['col'])
        self.assertEqual(rows,[{'col':'value'}])
        self.assertEqual(get.call_count,2)
        self.assertEqual(source,'verified-source')
        get.side_effect=None
        get.return_value=manager
        with patch('services.statcast_service.MAX_BYTES',3),self.assertRaises(service.StatcastError):
            service.csv_request('/statcast_search/csv',{})


if __name__ == '__main__':
    unittest.main()
