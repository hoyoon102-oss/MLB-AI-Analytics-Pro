"""Small real player queries; stores compact evidence, never all-MLB events."""
import json
from utils.paths import PROJECT_ROOT
from services.statcast_service import fetch_period, published_player
from analytics.statcast_context import summary


def main():
    examples = []
    empty = fetch_period(660271,2024,'hitting','2024-01-01','2024-01-31')
    if empty['rows']:
        raise RuntimeError('Unexpected regular-season events in known offseason window')
    print('PASS: known offseason window yields no observations')
    for player_id,category,day in [(660271,'hitting','2024-09-19'), (694973,'pitching','2024-05-11')]:
        data = fetch_period(player_id,2024,category,day,day)
        published = published_player(2024,category,player_id)
        if not data['rows']:
            raise RuntimeError('Expected real tracking observations were not returned')
        compact = summary(data,published)
        examples.append(compact)
        print(f'PASS: {category} MLBAM {player_id}, {day}, {len(data["rows"])} pitches')
        print('Published:',{k:v['value'] for k,v in compact['published_full_season'].items()})
        if published['errors']:
            print('Published-source limitations:',published['errors'])
    (PROJECT_ROOT/'docs/statcast-live-evidence.json').write_text(json.dumps(examples,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
