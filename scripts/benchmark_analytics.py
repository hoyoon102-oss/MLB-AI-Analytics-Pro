"""Bounded offline timings; no external requests or user storage."""
import json
from pathlib import Path
import statistics
import time
from analytics.percentiles import profile
from analytics.player_similarity import similar_players
from analytics.career_trends import aggregate
from analytics.leaderboard_rankings import filter_and_rank
from tests.test_percentiles import bundle
from tests.test_career_trends import hitter
import pandas as pd

def main():
    b = bundle()
    frame = pd.DataFrame([{'id': i, 'OPS': i / 1000, 'PA': 400, 'category': 'hitting', 'season': 2024, 'qualified': True} for i in range(1, 101)])
    jobs = {'percentiles': lambda: profile(b, 1, 'local'),
            'similarity': lambda: similar_players(b, 1),
            'career_aggregate': lambda: aggregate([hitter() for _ in range(20)], 'hitting'),
            'leaderboard_filter': lambda: filter_and_rank(frame, 'hitting', {}, 'OPS')}
    output = {}
    for name, job in jobs.items():
        observations = []
        for _ in range(5):
            start = time.perf_counter()
            for _ in range(20):
                job()
            observations.append((time.perf_counter() - start) / 20)
        output[name] = {'median_seconds': statistics.median(observations), 'calls': 100}
    Path('docs/v49-analytics-benchmark.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
