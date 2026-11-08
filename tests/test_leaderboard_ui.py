"""Loaded interactive leaderboard UI and discovery actions without external APIs."""
import os
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from components.leaderboard_ui import open_player,_table_selection,_plot_selection
from utils.favorites import load_favorites
from tests.test_leaderboards import fixture

SOURCE='''
from utils.i18n import st
from components.leaderboard_ui import page
from components.dashboard import change_favorite
from utils.favorites import load_favorites
st.session_state['_favorites']=load_favorites()[0]
st.selectbox('Language',['ko','en'],key='ui_language')
def seasons(*args):
    return {'years':[2023,2024,2025],'latest':2024,'warning':None}
page(change_favorite,seasons)
'''


class LeaderboardUITests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        env=patch.dict(os.environ,{'MLB_ANALYTICS_DATA_DIR':d.name})
        env.start()
        self.addCleanup(env.stop)

    @patch('components.leaderboard_ui.discovery_dataset')
    def test_default_category_metric_direction_language_and_no_repeat_download(self,fetch):
        fetch.side_effect=lambda year,category,include:fixture(category)
        ui=AppTest.from_string(SOURCE).run()
        fetch.assert_not_called()
        self.assertEqual(ui.selectbox(key='lb_season').value,2024)
        ui.button(key='lb_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key='lb_metric').value,'OPS')
        self.assertFalse(ui.checkbox(key='lb_ascending').value)
        ui.selectbox(key='ui_language').set_value('en').run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_count,1)
        ui.radio(key='lb_category').set_value('pitching').run()
        ui.button(key='lb_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key='lb_metric').value,'ERA')
        self.assertTrue(ui.checkbox(key='lb_ascending').value)

    @patch('components.leaderboard_ui.discovery_dataset',return_value=fixture())
    def test_filters_presets_reset_and_confirmation(self,fetch):
        ui=AppTest.from_string(SOURCE).run()
        ui.button(key='lb_load').click().run()
        ui.number_input(key='lb_min_pa').set_value(300).run()
        ui.text_input(key='lb_preset_name').set_value('My filters').run()
        ui.button(key='lb_preset_save').click().run()
        self.assertFalse(ui.exception)
        self.assertIn('My filters',ui.selectbox(key='lb_preset_choice').options)
        ui.button(key='lb_reset').click().run()
        self.assertEqual(ui.number_input(key='lb_min_pa').value,0)
        ui.selectbox(key='lb_preset_choice').set_value('My filters').run()
        ui.button(key='lb_preset_apply').click().run()
        self.assertEqual(ui.number_input(key='lb_min_pa').value,300)
        self.assertTrue(ui.button(key='lb_preset_delete').disabled)
        ui.checkbox(key='lb_delete_confirm').set_value(True).run()
        ui.button(key='lb_preset_delete').click().run()
        self.assertFalse(ui.exception)
        self.assertNotIn('My filters',ui.selectbox(key='lb_preset_choice').options)

    @patch('components.leaderboard_ui.discovery_dataset',return_value=fixture())
    def test_favorites_comparison_and_navigation(self,fetch):
        ui=AppTest.from_string(SOURCE).run()
        ui.button(key='lb_load').click().run()
        ui.button(key='lb_favorite').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(load_favorites()[0][0]['id'],1)
        ui.multiselect(key='lb_compare_ids').set_value([1,2]).run()
        ui.button(key='lb_compare').click().run()
        self.assertEqual(ui.session_state['compare_1_chosen']['id'],2)
        self.assertEqual(ui.session_state['compare_0_stats_category'],'hitting')
        ui.button(key='lb_nav_선수 기록').click().run()
        self.assertEqual(ui.session_state['dashboard_chosen']['id'],1)
        self.assertEqual(ui.session_state['selected_season'],2024)

    def test_stable_table_plot_identifiers_and_two_way_category(self):
        state={'lb_table':{'selection':{'rows':[1,0]}},'_lb_visible_ids':[42,77],
               '_lb_result_ids':[42,77],'lb_plot':{'selection':{'points':[{'customdata':[42,'Name']}]}},
               'dashboard_result':999}
        with patch('components.leaderboard_ui.st.session_state',state):
            _table_selection()
            self.assertEqual(state['lb_compare_ids'],[77,42])
            _plot_selection()
            self.assertEqual(state['lb_selected_id'],42)
            open_player({'id':42,'fullName':'Two Way'},2024,'Statcast 분석','pitching')
            self.assertEqual(state['dashboard_stats_category'],'pitching')
            self.assertEqual(state['career_category_42'],'pitching')
            self.assertNotIn('dashboard_result',state)

    @patch('components.ai_ui.generate',return_value='Verified ranking insight')
    @patch('components.leaderboard_ui.discovery_dataset',return_value=fixture())
    def test_ai_current_language_and_filtered_context(self,fetch,generate):
        setup="from utils.i18n import st\nst.session_state.update(ai_enabled=True,ai_models=['small'],ai_model='small')\n"
        ui=AppTest.from_string(setup+SOURCE).run()
        ui.selectbox(key='ui_language').set_value('en').run()
        ui.button(key='lb_load').click().run()
        generate.assert_not_called()
        ui.button(key='lb_ai_generate').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(generate.call_args.args[1]['mode'],'MLB Leaderboard')
        self.assertEqual(generate.call_args.args[1]['eligible_n'],3)
        self.assertEqual(generate.call_args.kwargs['language'],'en')
