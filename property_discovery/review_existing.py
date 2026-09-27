"""V4: bounded review of already collected homes; never add search results."""

import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .acoustics import enrich
from .browser import read_page
from .discover import apply_detail, write_json, write_reports
from .geography import classify, road_ring
from .investigate import investigate


FOCUS = ('煤建四处', '合群小区', '民和园', '湖滨西村')
DATA = Path(__file__).with_name('data')


def review(refresh_focus=False):
    run = json.loads((DATA / 'latest.json').read_text(encoding='utf-8'))
    now = dt.datetime.now(ZoneInfo('Asia/Shanghai'))
    run.update(parent_run_id=run['run_id'], run_id=now.strftime('%Y%m%dT%H%M%S%f%z'),
               collected_at=now.isoformat(timespec='seconds'), schema_version=4)
    ring = road_ring(json.loads((DATA / 'third_ring_osm.json').read_text(encoding='utf-8')))
    sources = json.loads((DATA / 'v4_reviews.json').read_text(encoding='utf-8'))
    run['geography'] = dict(ring, sources=sources['boundary_sources'],
                            classification_scope='community_reference_only', near_boundary_buffer_m=750)
    raw = []
    stopped = False
    script = Path(__file__).with_name('extract.js').read_text(encoding='utf-8')
    for index, old in enumerate(run['properties']):
        row = dict(old)
        if refresh_focus and row['community'] in FOCUS:
            if stopped:
                row['live_check'] = {'status': 'not_attempted', 'reason': 'prior_access_gate_stop'}
            else:
                payload = read_page(row['url'], script)
                stamp = dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')
                record = {'url': row['url'], 'status': payload.get('status'), 'reason': payload.get('reason'),
                          'read_at': stamp, 'phase': 'v4_existing_listing'}
                run['access_log'].append(record)
                raw.append(dict(record, payload=payload))
                row['live_check'] = record
                if payload.get('status') == 'ok':
                    row = dict(apply_detail(row, payload), detail_read_at=stamp)
                stopped = payload.get('status') == 'blocked'
        row = investigate(row)
        row['geography'] = classify(row, ring)
        row['inside_third_ring'] = row['geography']['inside_third_ring']
        focused = sources['properties'].get(row['url'], {})
        row['focused_investigation'] = focused
        row['geographic_environment'] = focused.get('map_facts', [])
        if focused.get('location_conflict'):
            row['geography']['status'] = 'location_conflict'
            row['inside_third_ring'] = None
        row['location_allowed_verified'] = row['inside_third_ring'] is True
        row = enrich(row)
        row['scope_label'] = row['geography']['status'] + '（小区参考点初核；非楼栋测绘）'
        row['visit_blockers'] = []
        if row['qualification'] != 'public_fields_match':
            row['visit_blockers'].append('公开住宅/面积/价格条件未通过')
        if not 40 <= row.get('area_sqm', 0) <= 60 or not 0 < row.get('price_wan', 999) <= 50:
            row['visit_blockers'].append('面积/价格超范围或零价不能确认有效报价')
        if row['floor_status'] != 'eligible_next_round':
            row['visit_blockers'].append('楼层/电梯条件尚未通过')
        if row['inside_third_ring'] is not True:
            row['visit_blockers'].append('三环内位置尚未通过：' + row['geography']['status'])
        if row.get('living_conflicts'):
            row['visit_blockers'].extend(row['living_conflicts'])
        if not focused.get('visit_evidence'):
            row['visit_blockers'].append('尚缺具体环境/布局复核，不用泛化周边POI凑看房名单')
        if row.get('live_check', {}).get('status') != 'ok':
            row['visit_blockers'].append('本轮挂牌有效性未刷新')
        row['visit_ready'] = not row['visit_blockers']
        run['properties'][index] = row
    run['v4_scope'] = '不扩大搜索；三环外独立保存；实地调查资格不是购买或隔音合格结论'
    if raw:
        write_json(DATA / 'runs' / f"{run['run_id']}_public_refresh.json", raw)
    write_json(DATA / 'runs' / f"{run['run_id']}.json", run)
    write_json(DATA / 'latest.json', run)
    write_json(DATA / 'outside_properties.json', {'run_id': run['run_id'], 'properties': [r for r in run['properties']
                if r['geography']['status'] == 'outside_reference'],
                'boundary_pending': [r for r in run['properties'] if r['geography']['status'] == 'near_boundary']})
    write_json(DATA / 'third_ring_derived.json', run['geography'])
    write_boundary_report(run)
    write_reports(run, Path('candidate_properties.md'))
    print(json.dumps({'run_id': run['run_id'], 'visit_ready': [r['community'] for r in run['properties'] if r['visit_ready']],
                      'gate_stop': stopped}, ensure_ascii=False))


def write_boundary_report(run):
    ring = run['geography']
    xs, ys = zip(*ring['coordinates'])
    lines = ['# 徐州三环道路范围核验 V4', '',
             '本轮严格三环内；V3南区环外放宽不沿用。行政区不参与范围判定。', '',
             '## 来源与空间口径', '',
             '- [徐州市政府2021-10-22道路连接说明](https://www.xz.gov.cn/001/001004/20211022/5525841c-8d6c-40dc-a68c-b4755cc4651a.html)：南三环西接徐萧路节点、东接古州飞虹节点；与西、北、东三环构成闭合道路。2026-09-27通过正常Chrome读取，政府页不含住宅法定边界坐标。',
             f"- [公开OSM道路几何](https://www.openstreetmap.org)经Overpass读取，采集2026-09-27，数据基准{ring['osm_base']}，ODbL；坐标WGS84/EPSG:4326。不是官方测绘，几何真实性仍受开放地图质量限制。",
             f"- 从四条具名快速路主线逐一连接相同OSM端点，取得{len(ring['way_ids'])}段/{len(ring['coordinates'])}个坐标的闭合有向车道环。没有手画连接线；主辅路与双向车道有位置差异。范围约经度{min(xs):.5f}—{max(xs):.5f}，纬度{min(ys):.5f}—{max(ys):.5f}。",
             '- [原始道路数据](data/third_ring_osm.json)、[实际选用节点与道路ID](data/third_ring_derived.json)、[请求与失败日志](data/v4_reviews.json)均留存。对公开服务的读取失败不解释为没有道路。',
             '- 贝壳小区参考点标为BD-09，经近似BD-09→GCJ-02→WGS84转换，非测绘精度；距闭合环750米以内一律待核，未精确量测小区外边界。该缓冲是保守筛选政策，不是坐标误差上限。',
             '- 远离边界可支持小区参考点环内/环外初核；**尚无具体房源楼栋测绘确认**，不能用参考点替代楼号。地图地址矛盾单列，不能靠数值算法消除矛盾。', '',
             '## 全部既有小区逐项结果', '',
             '| 小区 | 地理结果 | 参考点距闭合道路约米 | 坐标来源 |', '| --- | --- | --- | --- |']
    for row in run['properties']:
        g = row['geography']
        lines.append(f"| {row['community']} | {g['status']} | {g.get('distance_to_ring_m_approx', '未知')} | [贝壳小区参考点]({row.get('community_url')})，{row.get('community_read_at')} |")
    lines += ['', 'inside_reference/outside_reference仅为参考点初核；near_boundary需要楼号及小区范围；location_conflict需要纠正定位；unknown需要准确坐标。', '',
              '下一步：民和园取得西三环东侧实际楼号，湖滨西村先核对西村/东村和湖北路/地图冲突；广山西路、南坝山、金苑北院、碧水湾按边界附近保留。环外单存，不混入看房名单。']
    Path(__file__).with_name('third_ring_review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh-focus', action='store_true')
    review(parser.parse_args().refresh_focus)
