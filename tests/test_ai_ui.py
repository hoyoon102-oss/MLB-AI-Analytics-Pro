"""UI tests with synthetic records and mocked local generation; no network."""
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services.ai_analyst import AIError


PANEL_APP = '''
import streamlit as st
import components.ai_ui as ai_ui
st.session_state.setdefault("ai_enabled", True)
st.session_state.setdefault("ai_models", ["small"])
st.session_state.setdefault("ai_model", "small")
player_id = st.selectbox("테스트 선수", [1, 2], key="test_player")
def history(*args):
    return {2023: {"ops": ".800"}, 2024: {"ops": ".900"}}, [], "history time"
def awards(*args):
    return {"records": [], "fetched_at": "award time"}
ai_ui.player_panel({"id": player_id, "fullName": f"Test {player_id}"}, 2024,
                   "hitting", {"ops": ".900"}, "time", history, awards)
'''


class AIUITests(unittest.TestCase):
    @patch("components.ai_ui.generate")
    def test_mlb_history_and_award_failures_remain_explicit(self, generate):
        source = PANEL_APP.replace('return {2023: {"ops": ".800"}, 2024: {"ops": ".900"}}, [], "history time"',
                                   'raise ValueError("invalid history response")')
        source = source.replace('return {"records": [], "fetched_at": "award time"}',
                                'raise ValueError("invalid awards response")')
        ui = AppTest.from_string(source).run()
        ui.button(key="ai_prepare").click().run()
        self.assertEqual(len(ui.exception), 0)
        context = ui.session_state["ai_player_context"]
        self.assertTrue(context["history_error"])
        self.assertTrue(context["awards_error"])
        self.assertEqual(context["official_awards"], [])
        self.assertGreaterEqual(len(ui.warning), 2)
        generate.assert_not_called()

    @patch("components.ai_ui.generate", return_value="두 선수 비교")
    def test_comparison_generates_only_on_click(self, generate):
        source = '''
import streamlit as st
import components.ai_ui as ai_ui
st.session_state["ai_enabled"] = True
st.session_state["ai_models"] = ["small"]
st.session_state["ai_model"] = "small"
ai_ui.comparison_panel([{"id": 1, "fullName": "Test 1"}, {"id": 2, "fullName": "Test 2"}],
                       2024, "pitching", [{"inningsPitched": "6.1", "era": 2},
                       {"inningsPitched": "60.2", "era": 3}], ["time", "time"])
'''
        ui = AppTest.from_string(source).run()
        self.assertEqual(len(ui.exception), 0)
        generate.assert_not_called()
        ui.button(key="ai_comparison_generate").click().run()
        self.assertEqual(len(ui.exception), 0)
        generate.assert_called_once()
        self.assertEqual(generate.call_args.args[1]["players"][0]["category"], "pitching")

    @patch("components.ai_ui.generate", return_value="테스트 분석")
    def test_explicit_generation_only_and_result_survives_rerun(self, generate):
        ui = AppTest.from_string(PANEL_APP).run()
        self.assertEqual(len(ui.exception), 0)
        generate.assert_not_called()
        ui.button(key="ai_prepare").click().run()
        self.assertEqual(len(ui.exception), 0)
        generate.assert_not_called()
        ui.button(key="ai_scout_generate").click().run()
        self.assertEqual(len(ui.exception), 0)
        generate.assert_called_once()
        ui.run()
        generate.assert_called_once()
        self.assertTrue(any(item.value == "테스트 분석" for item in ui.markdown))

    @patch("components.ai_ui.generate", return_value="선택 선수 답변")
    def test_chat_switch_clears_history_and_prepared_data(self, generate):
        ui = AppTest.from_string(PANEL_APP).run()
        ui.button(key="ai_prepare").click().run()
        ui.chat_input[0].set_value("강점은 무엇인가요?").run()
        self.assertEqual(len(ui.exception), 0)
        self.assertEqual(len(ui.session_state["ai_chat_messages"]), 2)
        self.assertEqual(generate.call_args.args[1]["player"]["id"], 1)
        ui.selectbox(key="test_player").set_value(2).run()
        self.assertEqual(len(ui.exception), 0)
        self.assertEqual(ui.session_state["ai_chat_messages"], [])
        self.assertNotIn("ai_player_context", ui.session_state)
        ui.button(key="ai_prepare").click().run()
        self.assertEqual(ui.session_state["ai_player_context"]["player"]["id"], 2)

    @patch("components.ai_ui.generate", side_effect=AIError("연결 실패: 다시 시도하세요"))
    def test_generation_failure_keeps_ui_and_retry(self, generate):
        ui = AppTest.from_string(PANEL_APP).run()
        ui.button(key="ai_prepare").click().run()
        ui.button(key="ai_scout_generate").click().run()
        self.assertEqual(len(ui.exception), 0)
        self.assertTrue(ui.error)
        ui.chat_input[0].set_value("질문").run()
        self.assertEqual(ui.session_state["ai_chat_pending"], "질문")
        self.assertEqual(ui.session_state["ai_chat_messages"], [])
        self.assertIsNotNone(ui.button(key="ai_chat_retry"))

    @patch("components.ai_ui.list_models", side_effect=AIError("Ollama 연결 실패"))
    def test_ollama_unavailable_is_optional(self, models):
        ui = AppTest.from_string("import components.ai_ui as ai_ui\nai_ui.settings()\n").run()
        models.assert_not_called()
        ui.toggle(key="ai_enabled").set_value(True).run()
        models.assert_not_called()
        ui.button(key="ai_refresh_models").click().run()
        self.assertEqual(len(ui.exception), 0)
        self.assertTrue(ui.warning)


if __name__ == "__main__":
    unittest.main()
