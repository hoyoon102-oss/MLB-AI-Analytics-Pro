"""Read-only live checks. Never generate AI text or edit local user data."""
from services.player_stats import fetch_stats
from services.ai_analyst import AIError, list_models


def main():
    for player_id, category in ((660271, 'hitting'), (543037, 'pitching')):
        stats, _ = fetch_stats(player_id, 2024, category)
        if not stats or stats.get('_group') != category:
            raise RuntimeError('MLB season/category check failed')
        print(f'PASS: MLB regular-season {category}, player ID {player_id}, season 2024')
    try:
        models = list_models()
    except AIError as error:
        print('INFO: Ollama unavailable; handled AIError:', str(error))
    else:
        print(f'PASS: Ollama local connection and model listing ({len(models)} models); no generation requested')


if __name__ == '__main__':
    main()
