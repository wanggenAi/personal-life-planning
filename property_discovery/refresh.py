"""Refresh failed community evidence legally; preserve the previous run."""

import argparse
import datetime as dt
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from .acoustics import enrich
from .browser import read_page
from .discover import apply_detail, write_reports, write_json
from .investigate import investigate


def refresh(input_path, output, report, listing_urls=(), refresh_existing=True):
    run = json.loads(input_path.read_text(encoding='utf-8'))
    now = dt.datetime.now(ZoneInfo('Asia/Shanghai'))
    run['parent_run_id'] = run['run_id']
    run['run_id'] = now.strftime('%Y%m%dT%H%M%S%f%z')
    run['collected_at'] = now.isoformat(timespec='seconds')
    run['schema_version'] = 3
    cache, stopped = {}, False
    script = Path(__file__).with_name('extract.js').read_text(encoding='utf-8')
    available = {r['url']: r for r in run.get('unvisited_matches', [])}
    if len(listing_urls) > 12 or any(url not in available for url in listing_urls):
        raise ValueError('At most 12 URLs already observed in this snapshot are allowed')
    for url in dict.fromkeys(listing_urls):
        time.sleep(2)
        payload = read_page(url, script)
        timestamp = dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
        run['access_log'].append({'url': url, 'status': payload.get('status'),
                                  'reason': payload.get('reason'), 'read_at': timestamp,
                                  'phase': 'targeted_existing_lead'})
        if payload.get('status') == 'blocked':
            stopped = True
            break
        row = apply_detail(available[url], payload)
        row['detail_read_at'] = timestamp
        run['properties'].append(row)
    for row in run['properties']:
        url = row.get('community_url')
        if url and not stopped and (refresh_existing or not row.get('community_read_at')):
            if url not in cache:
                time.sleep(2)
                payload = read_page(url, script)
                timestamp = dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
                cache[url] = (payload, timestamp)
                run['access_log'].append({'url': url, 'status': payload.get('status'),
                                          'reason': payload.get('reason'), 'read_at': timestamp,
                                          'phase': 'community_refresh'})
                stopped = payload.get('status') == 'blocked'
            payload, timestamp = cache[url]
            if payload.get('status') == 'ok':
                row['community_read_at'] = timestamp
                row['address'] = payload.get('address')
                row['community_attributes'] = payload.get('attributes', {})
                for key in ('surroundings', 'history', 'coordinates', 'map_access'):
                    row[key] = payload.get(key)
                if row.get('surroundings') is None:
                    row['surroundings'] = {}
        # Recompute prior decisions too (e.g. estate-level mixed elevator claims).
        if row.get('qualification_reason') == 'confirmed_public_walkup_above_3':
            row['qualification'], row['qualification_reason'] = 'public_fields_match', None
        row.update(enrich(investigate(row)))
        write_json(output / 'runs' / f"{run['run_id']}.json", run)
    run['refresh_stop_reason'] = 'access_gate_stop' if stopped else 'bounded_existing_communities_complete'
    run['stats']['targeted_detail_attempts'] = sum(item.get('phase') == 'targeted_existing_lead'
                                                 for item in run['access_log'])
    visited = {r['url'] for r in run['properties']}
    run['unvisited_matches'] = [r for r in run.get('unvisited_matches', []) if r['url'] not in visited]
    write_json(output / 'runs' / f"{run['run_id']}.json", run)
    write_json(output / 'latest.json', run)
    write_reports(run, report)
    print(json.dumps({'run_id': run['run_id'], 'properties': len(run['properties']),
                      'environment_evidence': sum(bool(r.get('environment_evidence')) for r in run['properties']),
                      'stop': run['refresh_stop_reason']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('property_discovery/data/latest.json'))
    parser.add_argument('--output', type=Path, default=Path('property_discovery/data'))
    parser.add_argument('--report', type=Path, default=Path('candidate_properties.md'))
    parser.add_argument('--listing-url', action='append', default=[])
    parser.add_argument('--skip-existing-communities', action='store_true')
    args = parser.parse_args()
    refresh(args.input, args.output, args.report, args.listing_url, not args.skip_existing_communities)


if __name__ == '__main__':
    main()
