"""Synthetic award fixtures validate grouping, never populate production histories."""
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st

from components.awards import normalize_awards, fetch_awards, category_counts, season_awards
from components.profile_ui import profile_fields
import tests.test_smart as test_smart
from tests.test_support import seeded_app, fix_seasons


def award(code='ALMVP', season='2024', date='2024-11-20', name='AL MVP', position='DH'):
    return {'id': code, 'name': name, 'season': season, 'date': date,
            'player': {'id': 660271, 'primaryPosition': {'abbreviation': position}},
            'team': {'id': 1, 'teamName': 'Historic Award Team'}}


class AwardsTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def test_exact_and_annual_duplicates_are_not_double_counted(self):
        row = award()
        extra = dict(row, date='2024-11-21', team={'teamName': 'Later metadata'})
        result = normalize_awards({'awards': [row, row, extra]}, 660271)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(category_counts(result['records']), {'MVP': 1})

    def test_weekly_awards_distinct_dates_preserved(self):
        a = award('ALPOW', date='2024-05-01', name='AL Player of the Week')
        b = award('ALPOW', date='2024-06-01', name='AL Player of the Week')
        rows = normalize_awards({'awards': [a, a, b]}, 660271)['records']
        self.assertEqual(len(rows), 2)
        self.assertEqual(category_counts(rows), {})

    def test_postseason_mvp_and_minor_awards_never_count_as_regular_mvp(self):
        rows = normalize_awards({'awards': [award(), award('NLCSMVP', name='NLCS MVP'),
            award('BAMLROY', name='Baseball America Rookie of the Year'),
            award('MIDAS', name='Minor League All-Star')]}, 660271)['records']
        self.assertEqual(category_counts(rows), {'MVP': 1})
        self.assertEqual(len(rows), 4)

    def test_all_star_is_unique_seasons_not_positions_or_games(self):
        rows = normalize_awards({'awards': [award('ALAS', date='2024-07-01', name='AL All-Star'),
            award('ALAS', date='2024-07-16', name='AL All-Star', position='P'),
            award('NLAS', name='NL All-Star')]}, 660271)['records']
        self.assertEqual(category_counts(rows)['올스타 선정 시즌'], 1)

    def test_all_mlb_position_honors_preserved(self):
        a = award('MLBAFIRST', name='All-MLB First Team')
        b = award('MLBAFIRST', name='All-MLB First Team', position='SP')
        c = award('MLBAFIRST', name='All-MLB First Team', position='P')
        rows = normalize_awards({'awards': [a, b, c]}, 660271)['records']
        self.assertEqual(category_counts(rows)['All-MLB 선정 항목'], 2)

    def test_season_filter_uses_season_not_announcement_year(self):
        rows = normalize_awards({'awards': [award(date='2025-01-10'), award(season='2023')]}, 660271)['records']
        self.assertEqual(len(season_awards(rows, 2024)), 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(category_counts(rows)['MVP'], 2)

    def test_unknown_awards_names_and_ids_preserved(self):
        rows = normalize_awards({'awards': [award('NEW_AWARD', name='Official New Award')]}, 660271)['records']
        self.assertEqual(rows[0]['id'], 'NEW_AWARD')
        self.assertEqual(rows[0]['name'], 'Official New Award')
        self.assertEqual(category_counts(rows), {})

    def test_missing_season_not_guessed_from_date(self):
        row = award();row.pop('season')
        rows = normalize_awards({'awards': [row]}, 660271)['records']
        self.assertIsNone(rows[0]['season'])
        self.assertEqual(season_awards(rows, 2024), [])

    def test_championship_not_treated_as_individual_award(self):
        result = normalize_awards({'awards': [award('WSCHAMP', name='World Series Championship')]}, 660271)
        self.assertEqual(result['excluded'], 1)
        self.assertEqual(result['records'], [])
        self.assertEqual(category_counts(result['records']), {})

    def test_missing_team_never_filled_from_current_profile(self):
        row = award();row.pop('team')
        result = normalize_awards({'awards': [row]}, 660271)
        self.assertIsNone(result['records'][0]['team'])
        self.assertEqual(result['records'][0]['league'], 'AL')

    def test_conflicting_duplicate_teams_are_not_asserted_as_fact(self):
        a = award()
        b = dict(a, team={"teamName": "Conflicting Team"})
        records = normalize_awards({"awards": [a, b, a]}, 660271)["records"]
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["team"])

    def test_headshot_success_is_validated_and_cached(self):
        from io import BytesIO
        from PIL import Image
        from components.profile_ui import fetch_headshot
        data = BytesIO()
        Image.new("RGB", (1, 1)).save(data, format="PNG")
        response = Mock();response.content = data.getvalue()
        with patch('requests.get', return_value=response) as request:
            self.assertEqual(fetch_headshot(1), data.getvalue())
            fetch_headshot(1)
        self.assertEqual(request.call_count, 1)

    def test_missing_or_invalid_headshot_returns_placeholder_signal(self):
        from components.profile_ui import fetch_headshot
        with patch('requests.get', side_effect=requests.HTTPError()):
            self.assertIsNone(fetch_headshot(1))
        response = Mock();response.content = b'<html>No photo</html>'
        with patch('requests.get', return_value=response):
            self.assertIsNone(fetch_headshot(2))

    def test_empty_partial_and_invalid_responses(self):
        self.assertEqual(normalize_awards({'awards': []}, 660271)['records'], [])
        row = award();row['player'] = {'id': 1}
        result = normalize_awards({'awards': [award(), None, row]}, 660271)
        self.assertEqual(result['invalid'], 2)
        self.assertEqual(len(result['records']), 1)
        for payload in ({}, {'awards': None}, None):
            with self.assertRaises(ValueError):
                normalize_awards(payload, 660271)

    def test_fetch_actual_path_cache_and_failure_not_zero(self):
        response = Mock();response.json.return_value = {'awards': [award()]}
        with patch('requests.get', return_value=response) as request:
            self.assertEqual(len(fetch_awards(660271)['records']), 1)
            fetch_awards(660271)
        self.assertEqual(request.call_count, 1)
        self.assertTrue(request.call_args.args[0].endswith('/people/660271/awards'))
        st.cache_data.clear()
        with patch('requests.get', side_effect=requests.Timeout()), self.assertRaises(requests.Timeout):
            fetch_awards(660271)

    def test_profile_verified_fields_and_incomplete_metadata(self):
        person = {'id': 660271, 'fullName': 'Example'}
        fields = profile_fields(person, {'currentTeam': {'name': 'Current Club'},
            'mlbDebutDate': '2018-03-29', 'batSide': {'code': 'L'}, 'pitchHand': {'code': 'R'}})
        self.assertEqual(fields['현재 소속팀 (프로필 조회 기준)'], 'Current Club')
        self.assertEqual(fields['타격 손'], '좌')
        self.assertEqual(profile_fields(person, {'currentTeam': 'broken'})['현재 소속팀 (프로필 조회 기준)'], '미확인')


class AwardsUITests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear();fix_seasons(self)
        patcher = patch('requests.get', side_effect=self.request)
        patcher.start();self.addCleanup(patcher.stop)

    def request(self, url, params, **kwargs):
        if url.endswith('/awards'):
            response = Mock()
            player_id = int(url.split('/people/')[1].split('/')[0])
            row = award();row['player']['id'] = player_id
            response.json.return_value = {'awards': [row, award(season='2023')] if player_id == 660271 else [row]}
            return response
        return test_smart.SmartUITests.request(self, url, params, **kwargs)

    def test_awards_default_career_independent_of_selected_season(self):
        ui = seeded_app()
        ui.toggle(key='awards_open').set_value(True).run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.radio(key='awards_view_660271').value, '통산 수상')
        self.assertTrue(any(metric.label == 'MVP' and metric.value == '2' for metric in ui.metric))
        ui.selectbox(key='selected_season').set_value(2020).run()
        self.assertFalse(ui.exception)
        self.assertTrue(any(metric.label == 'MVP' and metric.value == '2' for metric in ui.metric))
        ui.radio(key='awards_view_660271').set_value('선택 시즌 수상').run()
        self.assertTrue(any('2020 시즌에 연결된' in item.value for item in ui.info))

    def test_awards_api_failure_does_not_break_stats_or_show_zero(self):
        ui = seeded_app()
        with patch('components.awards.fetch_awards', side_effect=requests.Timeout()):
            ui.toggle(key='awards_open').set_value(True).run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.metric), 6)
        self.assertTrue(any('0회라는 뜻이 아닙니다' in item.value for item in ui.warning))

    def test_empty_history_explicit_message(self):
        ui = seeded_app()
        with patch('components.awards.fetch_awards', return_value={'records': [], 'excluded': 0, 'invalid': 0, 'fetched_at': 'test UTC'}):
            ui.toggle(key='awards_open').set_value(True).run()
        self.assertFalse(ui.exception)
        self.assertTrue(any('수상 경력이 없다는 뜻은 아닙니다' in item.value for item in ui.info))

    def test_optional_career_comparison_works_for_incompatible_season_roles(self):
        ui = seeded_app()
        ui.sidebar.radio[0].set_value('선수 비교').run()
        ui.session_state['compare_0_chosen'] = {'id': 543037, 'fullName': 'Pitcher Example'}
        ui.run()
        self.assertFalse(ui.table)
        ui.checkbox(key='compare_awards').set_value(True).run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.table), 1)
        self.assertEqual(len(ui.get('plotly_chart')), 1)
        self.assertTrue(any('같은 종류' in item.value for item in ui.info))


if __name__ == '__main__':
    unittest.main()
