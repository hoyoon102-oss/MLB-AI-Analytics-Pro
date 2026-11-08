"""Loaded career UI, short histories, category switching, locale and explicit AI."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_career_trends import career,hitter,pitcher

SOURCE='''
from utils.i18n import st
from components.career_ui import panel
st.selectbox('Language',['ko','en'],key='ui_language')
panel({'id':1,'fullName':'Test'},{'mlbDebutDate':'2021-04-01'})
'''


class CareerUITests(unittest.TestCase):
    def setUp(self):
        for target,value in [('components.career_ui.fetch_awards',{'records':[{'id':'MVP','name':'Verified Award','category':'MVP','season':2022,'date':'2023-01-01'}]}),
                             ('components.career_ui.fetch_profile',{'mlbDebutDate':'2021-04-01'})]:
            p=patch(target,return_value=value)
            p.start()
            self.addCleanup(p.stop)

    @patch('components.career_ui.fetch_career')
    def test_explicit_load_bilingual_and_no_download_on_rerun(self,fetch):
        fetch.return_value=career({2021:hitter(),2022:hitter(ops=.9),2023:None,2024:hitter()})
        ui=AppTest.from_string(SOURCE).run()
        fetch.assert_not_called()
        ui.button(key='career_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get('plotly_chart')),2)
        ui.selectbox(key='ui_language').set_value('en').run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(any(s.value=='Career Development' for s in ui.subheader))

    @patch('components.career_ui.fetch_career')
    def test_one_season_and_two_way_selection(self,fetch):
        def load(pid,category,today):
            return career({2024:hitter() if category=='hitting' else pitcher()},category)
        fetch.side_effect=load
        ui=AppTest.from_string(SOURCE).run()
        ui.button(key='career_load').click().run()
        self.assertFalse(ui.exception)
        ui.radio(key='career_category_1').set_value('pitching').run()
        self.assertFalse(ui.exception)
        ui.button(key='career_load').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(fetch.call_args.args[1],'pitching')

    @patch('components.ai_ui.generate',return_value='Verified career explanation')
    @patch('components.career_ui.fetch_career')
    def test_ai_career_context_and_no_automatic_generation(self,fetch,generate):
        fetch.return_value=career({2021:hitter(),2022:hitter(ops=.9)})
        setup="from utils.i18n import st\nst.session_state.update(ai_enabled=True,ai_models=['small'],ai_model='small')\n"
        ui=AppTest.from_string(setup+SOURCE).run()
        ui.selectbox(key='ui_language').set_value('en').run()
        ui.button(key='career_load').click().run()
        generate.assert_not_called()
        ui.button(key='career_ai_generate').click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(generate.call_args.args[1]['mode'],'Career Development')
        self.assertEqual(generate.call_args.kwargs['language'],'en')

    @patch('components.career_ui.fetch_career',side_effect=ValueError('invalid source'))
    def test_fetch_failure_is_not_no_records(self,fetch):
        ui=AppTest.from_string(SOURCE).run()
        ui.button(key='career_load').click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.warning)
