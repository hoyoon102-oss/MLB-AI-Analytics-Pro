"""Opt-in validation using real MLB records; no invented production statistics."""
import argparse

from services.ai_analyst import AIError, comparison_context, generate, list_models, player_context
from components.ai_ui import SCOUT
from services.player_stats import fetch_history, fetch_stats, search_players
from components.awards import fetch_awards


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="설치된 로컬 모델로 실제 생성도 수행 (기본: 데이터 검증만)")
    args = parser.parse_args()
    contexts = []
    for name, category in (("Shohei Ohtani", "hitting"), ("Aaron Judge", "hitting"),
                           ("Tarik Skubal", "pitching"), ("Paul Skenes", "pitching")):
        matches = [player for player in search_players(name) if player["fullName"] == name]
        assert len(matches) == 1, (name, "선수 식별 실패")
        player = matches[0]
        stats, at = fetch_stats(player["id"], 2024, category)
        assert stats, (name, "2024 기록 없음")
        records, problems, history_at = fetch_history(player["id"], 2020, 2024, category)
        context = player_context(player, 2024, category, stats, at, records, history_at,
                                 problems, fetch_awards(player["id"]))
        assert context["statistics"] and not problems, (name, "기록 검증 실패")
        contexts.append(context)
        print("PASS:", name, player["id"], category, "MLB context", flush=True)
        if name == "Shohei Ohtani":
            pitching, _ = fetch_stats(player["id"], 2024, "pitching")
            assert pitching is None, "2024 투구 기록 없음을 유지해야 함"
        if args.model:
            answer = generate(args.model, context, SCOUT)
            assert answer
            print(answer, flush=True)
    comparison_context(contexts[:2])
    comparison_context(contexts[2:])
    print("PASS: hitting and pitching comparison contexts", flush=True)
    try:
        print("Available local models:", list_models(), flush=True)
    except AIError as error:
        print("Ollama unavailable:", error, flush=True)


if __name__ == "__main__":
    main()
