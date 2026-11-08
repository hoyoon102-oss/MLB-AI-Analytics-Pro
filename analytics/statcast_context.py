"""Compact verified AI summaries; raw pitch rows never enter the language model."""
from analytics.statcast_hitting import hitting_summary, monthly_summary, published_metrics
from analytics.statcast_pitching import pitching_summary, arsenal, location_summary


def summary(dataset, published):
    category = dataset['category']
    if (dataset['player_id'] != published['player_id'] or dataset['season'] != published['season']
            or category != published['category'] or dataset.get('game_type') != 'R'):
        raise ValueError('Statcast identity, season or category mismatch')
    result = {'player_id':dataset['player_id'],'season':dataset['season'],'category':category,
              'game_type':'R','start':dataset['start'],'end':dataset['end'],
              'retrieved_at':dataset['retrieved_at'],'source':dataset['sources'],
              'quality':dataset['quality'],'published_full_season':published_metrics(published),
              'observed':(hitting_summary if category == 'hitting' else pitching_summary)(dataset['rows'])}
    if category == 'hitting':
        result['monthly'] = monthly_summary(dataset['rows'])
    else:
        result['arsenal'] = arsenal(dataset['rows'])
        result['locations'] = location_summary(dataset['rows'])
        result['monthly'] = {month:pitching_summary([r for r in dataset['rows'] if r['game_date'].startswith(month)])
                             for month in sorted({r['game_date'][:7] for r in dataset['rows']})}
    return result


def ai_context(player, dataset, published, previous=None):
    if player['id'] != dataset['player_id']:
        raise ValueError('Statcast player identity mismatch')
    observed = summary(dataset,published)
    context = {'player':{'id':player['id'],'name':player['fullName']},'season':dataset['season'],
               'category':dataset['category'],'mode':'Statcast','statistics':{
                   key:item['value'] for key,item in observed['observed']['metrics'].items()},
               'statcast':observed,
               'limitations':[
                   'Selected-date observations and source-published full-season expected metrics have different scopes and denominators.',
                   'League baselines unavailable. Missing values are unknown, never zero.',
                   '2015+ coverage only; tracking coverage and systems vary. CSV EV/LA can include source estimates.',
                   'Observed whiff rate uses the supplied description sets; not guaranteed identical to leaderboard rates.',
                   'pfx_x/pfx_z in inches, catcher perspective; not total drop or movement versus league average.',
                   '2026+ plate locations use middle of plate; through 2025 front of plate.',
                   'Do not infer causes or overall player quality from one metric. Explain sample sizes and provisional seasons.']}
    if previous and previous['player_id'] == player['id'] and previous['category'] == dataset['category']:
        context['previous_statcast'] = previous
        context['observed_changes'] = {key:item['value']-previous['observed']['metrics'][key]['value']
                                       for key,item in observed['observed']['metrics'].items()
                                       if item['value'] is not None and previous['observed']['metrics'].get(key,{}).get('value') is not None}
    return context
