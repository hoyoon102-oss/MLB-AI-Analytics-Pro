"""New UI controls, locale, persistent favorites, navigation and compact AI context."""
import os
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_percentiles import bundle
from components.rankings_ui import open_comparison,open_statistics
from utils.favorites import load_favorites
from utils.i18n import t

SOURCE='''
from utils.i18n import st
from components.rankings_ui import panel
from components.dashboard import change_favorite
from utils.favorites import load_favorites
st.session_state['_favorites']=load_favorites()[0]
st.selectbox('Language',['ko','en'],key='ui_language')
panel({'id':1,'fullName':'Selected'},2024,'hitting',change_favorite)
'''


class RankingsUITests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher=patch.dict(os.environ,{'MLB_ANALYTICS_DATA_DIR':directory.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch('components.rankings_ui.load_boards',return_value=bundle())
    def test_load_language_and_rerun_cache(self,load):
        ui=AppTest.from_string(SOURCE).run()
        self.assertFalse(ui.exception)
        load.assert_not_called()
        ui.button(key='rank_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get('plotly_chart')),2)
        ui.selectbox(key='rank_top').set_value(10).run()
        ui.radio(key='rank_method').set_value('local').run()
        ui.selectbox(key='ui_language').set_value('en').run()
        self.assertFalse(ui.exception)
        self.assertEqual(load.call_count,1)
        self.assertTrue(any(h.value=='Percentile Rankings' for h in ui.subheader))
        self.assertNotEqual(t('rank_title',locale='ko'),t('rank_title',locale='en'))

    @patch('components.rankings_ui.load_boards',return_value=bundle())
    def test_favorites_and_comparison_identity(self,load):
        ui=AppTest.from_string(SOURCE).run()
        ui.button(key='rank_load').click().run()
        ui.button(key='rank_save_2').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(load_favorites()[0][0]['id'],2)
        ui.button(key='rank_compare_2').click().run()
        self.assertEqual(ui.session_state['pro_page'],'선수 비교')
        self.assertEqual(ui.session_state['compare_0_chosen']['id'],1)
        self.assertEqual(ui.session_state['compare_1_chosen']['id'],2)
        self.assertEqual(ui.session_state['compare_1_stats_category'],'hitting')

    def test_navigation_clears_stale_picker_identity(self):
        state={'compare_0_result':999,'compare_1_favorite_choice':998,'dashboard_result':888}
        with patch('components.rankings_ui.st.session_state',state):
            open_comparison({'id':1,'fullName':'A'},{'id':2,'fullName':'B'},2024,'pitching')
            self.assertNotIn('compare_0_result',state)
            self.assertNotIn('compare_1_favorite_choice',state)
            open_statistics({'id':2,'fullName':'B'},2024)
            self.assertNotIn('dashboard_result',state)
            self.assertEqual(state['pro_page'],'선수 기록')
            self.assertEqual(state['dashboard_chosen']['id'],2)

    @patch('components.ai_ui.generate',return_value='Verified explanation')
    @patch('components.rankings_ui.load_boards',return_value=bundle())
    def test_ai_uses_python_results_and_selected_language(self,load,generate):
        setup="from utils.i18n import st\nst.session_state.update(ai_enabled=True,ai_models=['small'],ai_model='small')\n"
        ui=AppTest.from_string(setup+SOURCE).run()
        ui.selectbox(key='ui_language').set_value('en').run()
        ui.button(key='rank_load').click().run()
        generate.assert_not_called()
        ui.button(key='rank_ai_generate').click().run()
        self.assertFalse(ui.exception)
        context=generate.call_args.args[1]
        self.assertEqual(context['similarity']['player_id'],1)
        self.assertEqual(context['percentiles']['mode'],'official')
        self.assertEqual(generate.call_args.kwargs['language'],'en')
