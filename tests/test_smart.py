"""Deterministic synthetic fixtures for seasons and automatic role selection."""
from datetime import date
import unittest
from unittest.mock import Mock, patch

import requests
import streamlit as st

from services.season_selection import choose_season, resolve_seasons, has_regular_data
from services.player_detection import detect_role, has_record
from tests.test_support import fix_seasons, seeded_app, choose_restored
from tests.test_pitching import response_payload


def metadata(year):
    return {"seasonId": str(year), "regularSeasonStartDate": f"{year}-03-25",
            "regularSeasonEndDate": f"{year}-09-28"}


class SeasonSelectionTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def test_active_regular_season(self):
        self.assertEqual(choose_season([metadata(2025), metadata(2026)], date(2026, 6, 1), lambda *args: True), 2026)

    def test_january_and_spring_default_previous_completed(self):
        for today in (date(2026, 1, 5), date(2026, 3, 1)):
            self.assertEqual(choose_season([metadata(2025), metadata(2026)], today, lambda *args: True), 2025)

    def test_autumn_offseason_is_current_completed_season(self):
        self.assertEqual(choose_season([metadata(2025), metadata(2026), metadata(2027)], date(2026, 11, 3), lambda *args: True), 2026)

    def test_opening_day_without_started_game_and_cancelled_season(self):
        self.assertEqual(choose_season([metadata(2025), metadata(2026)], date(2026, 3, 25), lambda year, _: year == 2025), 2025)
        self.assertEqual(choose_season([metadata(2025), metadata(2026)], date(2026, 11, 3), lambda year, _: year == 2025), 2025)

    def test_future_year_is_not_default_and_not_hardcoded(self):
        self.assertEqual(choose_season([metadata(2030), metadata(2031)], date(2030, 7, 1), lambda *args: True), 2030)

    def test_schedule_must_include_actual_started_game(self):
        for state, expected in (("Preview", False), ("Live", True), ("Final", True)):
            with patch('services.season_selection.get_json', return_value={"dates": [{"games": [{"status": {"abstractGameState": state}}]}]}):
                self.assertEqual(has_regular_data(2026, date(2026, 7, 1)), expected)

    def test_api_failure_explicit_unverified_fallback(self):
        with patch('services.season_selection.get_json', side_effect=requests.Timeout()):
            info = resolve_seasons('2030-05-01')
        self.assertEqual(info['latest'], 2029)
        self.assertTrue(info['warning'])

    def test_success_catalog_excludes_upcoming_and_is_cached(self):
        with patch('services.season_selection.get_json', return_value={"seasons": [metadata(2025), metadata(2026), metadata(2027)]}) as request, patch('services.season_selection.has_regular_data', return_value=True):
            info = resolve_seasons('2026-11-03')
            resolve_seasons('2026-11-03')
        self.assertEqual(info['years'], [2025, 2026])
        self.assertEqual(request.call_count, 1)


class RoleDetectionTests(unittest.TestCase):
    def test_hitter_despite_current_pitcher_position(self):
        role = detect_role({'hitting': {'plateAppearances': 500}, 'pitching': None}, {'primaryPosition': {'abbreviation': 'P'}})
        self.assertEqual(role['options'], ['hitting'])

    def test_pitcher_with_historical_batting_is_not_automatically_two_way(self):
        role = detect_role({'hitting': {'plateAppearances': 70}, 'pitching': {'inningsPitched': '200.1'}})
        self.assertEqual(set(role['available']), {'hitting', 'pitching'})
        self.assertEqual(role['options'], ['pitching'])

    def test_position_player_with_occasional_pitching(self):
        role = detect_role({'hitting': {'plateAppearances': 600}, 'pitching': {'inningsPitched': '1.1'}})
        self.assertEqual(role['options'], ['hitting'])

    def test_official_two_way_without_pitching_records(self):
        role = detect_role({'hitting': {'plateAppearances': 600}, 'pitching': None}, {'primaryPosition': {'code': 'Y'}})
        self.assertEqual(role['options'], ['hitting', 'pitching'])
        self.assertEqual(role['preferred'], 'hitting')
        self.assertEqual(role['available'], ['hitting'])

    def test_meaningful_two_way_records_and_pitching_only_default(self):
        role = detect_role({'hitting': {'plateAppearances': 150}, 'pitching': {'inningsPitched': '20.0'}})
        self.assertTrue(role['two_way'])
        role = detect_role({'hitting': None, 'pitching': {'inningsPitched': '20.0'}}, {'isTwoWayPlayer': True})
        self.assertEqual(role['preferred'], 'pitching')

    def test_role_changes_by_season_and_zero_appearances(self):
        self.assertFalse(has_record({'plateAppearances': 0, 'atBats': 0, 'gamesPlayed': 0, 'avg': '.000'}, 'hitting'))
        self.assertTrue(has_record({'gamesPitched': 1, 'inningsPitched': '0.0', 'baseOnBalls': 2}, 'pitching'))
        self.assertEqual(detect_role({'hitting': None, 'pitching': {'outs': 300}})['options'], ['pitching'])
        self.assertEqual(detect_role({'hitting': {'plateAppearances': 200}, 'pitching': None})['options'], ['hitting'])

    def test_one_failed_category_never_certifies_role(self):
        role = detect_role({'hitting': {'plateAppearances': 50}, 'pitching': None}, errors={'pitching': 'timeout'})
        self.assertTrue(role['uncertain'])
        self.assertIn('역할 확정 아님', role['reason'])

    def test_missing_and_failed_categories_are_distinct(self):
        missing = detect_role({'hitting': None, 'pitching': None})
        failed = detect_role({'hitting': None, 'pitching': None}, errors={'pitching': 'timeout'})
        self.assertIn('없음', missing['reason'])
        self.assertIn('실패', failed['reason'])


class SmartUITests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        fix_seasons(self)
        request = patch('requests.get', side_effect=self.request)
        request.start()
        self.addCleanup(request.stop)

    def request(self, url, params, **kwargs):
        response = Mock()
        player_id = int(url.split('/people/')[1].split('/')[0])
        if not url.endswith('/stats'):
            response.json.return_value = {'people': [{'id': player_id, 'primaryPosition': {'abbreviation': 'TWP' if player_id == 660271 else 'P'}}]}
        else:
            category = params['group']
            # All fixtures are 2024. Ohtani has hitting only but retains official two-way status.
            available = category == ('pitching' if player_id == 543037 else 'hitting')
            response.json.return_value = response_payload(category) if available else {'stats': []}
        return response

    def test_hitter_automatic_no_type_selector(self):
        ui = seeded_app()
        choose_restored(ui, 'dashboard', 'Aaron Judge')
        self.assertEqual(len(ui.metric), 6)
        self.assertFalse(any(r.key in ('dashboard_category', 'dashboard_stats_category') for r in ui.radio))

    def test_pitcher_automatic(self):
        ui = seeded_app()
        choose_restored(ui, 'dashboard', 'Gerrit Cole')
        self.assertEqual(len(ui.metric), 14)
        self.assertFalse(any(r.key == 'dashboard_stats_category' for r in ui.radio))

    def test_two_way_missing_pitching_and_preserved_choice(self):
        ui = seeded_app()
        self.assertEqual(len(ui.metric), 6)
        ui.radio(key='dashboard_stats_category').set_value('pitching').run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.metric)
        self.assertTrue(any('해당 시즌 기록 없음' in info.value for info in ui.info))
        ui.run()
        self.assertEqual(ui.radio(key='dashboard_stats_category').value, 'pitching')

    def test_shared_manual_season_survives_navigation(self):
        ui = seeded_app()
        ui.selectbox(key='selected_season').set_value(2020).run()
        ui.sidebar.radio[0].set_value('선수 비교').run()
        self.assertEqual(ui.selectbox(key='selected_season').value, 2020)
        ui.sidebar.radio[0].set_value('선수 기록').run()
        self.assertEqual(ui.selectbox(key='selected_season').value, 2020)

    def test_incompatible_players_no_misleading_chart(self):
        ui = seeded_app()
        ui.sidebar.radio[0].set_value('선수 비교').run()
        ui.session_state['compare_0_chosen'] = {'id': 543037, 'fullName': 'Gerrit Cole'}
        ui.run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.table)
        self.assertFalse(ui.get('plotly_chart'))
        self.assertTrue(any('같은 종류' in info.value for info in ui.info))

    def test_two_way_and_pitcher_align_then_missing_stats_is_explicit(self):
        ui = seeded_app()
        ui.sidebar.radio[0].set_value('선수 비교').run()
        ui.session_state['compare_1_chosen'] = {'id': 543037, 'fullName': 'Gerrit Cole'}
        # Player 0 previously had a user-chosen hitting category; preserve it and explain mismatch.
        ui.run()
        ui.radio(key='compare_0_stats_category').set_value('pitching').run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.table[0].value), 14)
        self.assertTrue(any('해당 시즌 기록 없음' in info.value for info in ui.info))


if __name__ == '__main__':
    unittest.main()
