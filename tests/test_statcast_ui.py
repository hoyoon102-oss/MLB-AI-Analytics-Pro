"""Exercise new loaded dashboards, failures and locale switching without network."""
from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_statcast import dataset, published, row
from services.statcast_service import StatcastError

PANEL = '''
from utils.i18n import st
from components.statcast_ui import panel
st.selectbox('Language',['ko','en'],key='ui_language')
panel({'id':PLAYER_ID,'fullName':'Test Player'},2024,'CATEGORY')
'''


class StatcastUITests(unittest.TestCase):
    def setUp(self):
        patcher=patch('components.statcast_ui.current_date',return_value=date(2024,12,31))
        patcher.start()
        self.addCleanup(patcher.stop)

    def source(self,category='hitting'):
        return PANEL.replace('PLAYER_ID','660271' if category == 'hitting' else '694973').replace('CATEGORY',category)

    @patch('components.statcast_ui.published_player')
    @patch('components.statcast_ui.fetch_period')
    def test_hitting_load_is_explicit_and_reruns_do_not_download(self,fetch,publish):
        fetch.return_value=dataset()
        publish.return_value=published()
        ui=AppTest.from_string(self.source()).run()
        self.assertFalse(ui.exception)
        fetch.assert_not_called()
        ui.button(key='statcast_660271_2024_hitting_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get('plotly_chart')),5)
        self.assertEqual(fetch.call_count,1)
        ui.selectbox(key='ui_language').set_value('en').run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(any(m.value == 'Statcast Hitting' for m in ui.subheader))

    @patch('components.statcast_ui.published_player')
    @patch('components.statcast_ui.fetch_period')
    def test_pitcher_arsenal_locations_and_density_controls(self,fetch,publish):
        d=dataset()
        d.update(category='pitching',player_id=694973)
        fetch.return_value=d
        publish.return_value=published('pitching',694973)
        ui=AppTest.from_string(self.source('pitching')).run()
        ui.button(key='statcast_694973_2024_pitching_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get('plotly_chart')),2)
        self.assertTrue(ui.dataframe)
        ui.toggle(key='statcast_density').set_value(True).run()
        ui.toggle(key='statcast_normalized').set_value(False).run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_count,1)

    @patch('components.statcast_ui.published_player')
    @patch('components.statcast_ui.fetch_period',side_effect=StatcastError('sc_network_error'))
    def test_tracking_failure_keeps_published_values_and_retry(self,fetch,publish):
        p=published()
        p['tables']['expected']={'row':{'est_ba':'.300','pa':'100'},'source':'test','retrieved_at':'test'}
        publish.return_value=p
        ui=AppTest.from_string(self.source()).run()
        ui.button(key='statcast_660271_2024_hitting_load').click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.warning)
        self.assertTrue(any(m.value == '### 0.300' for m in ui.markdown))
        ui.button(key='statcast_660271_2024_hitting_load').click().run()
        self.assertEqual(fetch.call_count,2)

    @patch('components.ai_ui.generate',return_value='Verified Statcast analysis')
    @patch('components.statcast_ui.published_player')
    @patch('components.statcast_ui.fetch_period')
    def test_statcast_ai_is_explicit_compact_and_current_language(self,fetch,publish,generate):
        fetch.return_value=dataset()
        publish.return_value=published()
        setup="from utils.i18n import st\nst.session_state.update(ai_enabled=True,ai_models=['small'],ai_model='small')\n"
        ui=AppTest.from_string(setup+self.source()).run()
        ui.selectbox(key='ui_language').set_value('en').run()
        ui.button(key='statcast_660271_2024_hitting_load').click().run()
        self.assertFalse(ui.exception)
        generate.assert_not_called()
        ui.button(key='statcast_ai_generate').click().run()
        self.assertFalse(ui.exception)
        generate.assert_called_once()
        context=generate.call_args.args[1]
        self.assertEqual(context['mode'],'Statcast')
        self.assertNotIn('rows',context['statcast'])
        self.assertEqual(generate.call_args.kwargs['language'],'en')

    @patch('components.statcast_ui.published_player')
    @patch('components.statcast_ui.fetch_period')
    def test_comparison_loads_players_independently(self,fetch,publish):
        def load(pid,season,category,start,end,progress=None):
            d=dataset([row(batter=str(pid))])
            d.update(player_id=pid,start=start,end=end)
            return d
        fetch.side_effect=load
        publish.side_effect=lambda season,category,pid:published(category,pid)
        source="from components.statcast_ui import comparison\ncomparison([{'id':660271,'fullName':'A'},{'id':592450,'fullName':'B'}],2024,'hitting')"
        ui=AppTest.from_string(source).run()
        fetch.assert_not_called()
        ui.button(key='sc_compare_0_660271_2024_hitting_load').click().run()
        self.assertFalse(ui.exception)
        ui.button(key='sc_compare_1_592450_2024_hitting_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(len(ui.get('plotly_chart')),1)
