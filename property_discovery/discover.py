"""Bounded public DOM collection via browser-harness; never solve access gates."""

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .browser import read_page, validate_url


DEFAULT_URLS = ["https://xz.ke.com/ershoufang/",
                "https://xz.ke.com/ershoufang/p2/"]
AUXILIARY_URLS = ["https://xz.esf.fang.com/house/c20,30,40-d230,40,50/"]
NONRESIDENTIAL = re.compile(r"商办公寓|商业办公|酒店式公寓|商办房")


def numeric(text):
    match = re.search(r"\d+(?:\.\d+)?", str(text or '').replace(',', ''))
    return float(match.group()) if match else None


def normalize(row):
    result = dict(row)
    info = row.get('info', '')
    area = re.search(r"(\d+(?:\.\d+)?)\s*(?:平米|㎡)", info)
    layout = re.search(r"\d+室\d+厅", info)
    floor = re.search(r"(?:低楼层|中楼层|高楼层|低层|中层|高层|顶层)\s*[（(]共\d+层[）)]", info)
    result.update(area_sqm=float(area.group(1)) if area else None,
                  price_wan=numeric(row.get('price_text')),
                  unit_price_yuan=numeric(row.get('unit_text')),
                  layout=layout.group() if layout else None,
                  floor=floor.group() if floor else None)
    result['elevator'] = None
    result['floor_number'] = None
    result['inside_third_ring'] = None
    return result


def preliminary_filter(row, minimum=0, maximum=50):
    area, price = row.get('area_sqm'), row.get('price_wan')
    if area is None or price is None:
        return 'missing_area_or_price'
    if not 40 <= area <= 60:
        return 'outside_area_40_60'
    if not minimum <= price <= maximum:
        return 'outside_price_range'
    if price == 0:
        return 'zero_price_requires_verification'
    # Only explicit commercial claims are held back. Generic community names such
    # as "公寓" or "商铺旁" do not establish the legal use of a residential unit.
    if NONRESIDENTIAL.search(row.get('title', '')):
        return 'possible_nonresidential_title'
    return None


def apply_detail(row, detail):
    result = dict(row)
    result['detail_status'] = detail.get('status')
    if detail.get('status') != 'ok':
        result['qualification'] = 'pending_detail'
        result['qualification_reason'] = detail.get('reason', 'detail_unavailable')
        return result
    base, transaction = detail.get('base', {}), detail.get('transaction', {})
    result['public_base'] = base
    result['public_transaction'] = transaction
    result['community_url'] = detail.get('community_url')
    result['region'] = detail.get('region')
    result['listed_date'] = transaction.get('挂牌时间')
    result['floor'] = base.get('所在楼层') or result.get('floor')
    result['layout'] = base.get('房屋户型') or result.get('layout')
    purpose = transaction.get('房屋用途', '')
    rights = transaction.get('交易权属', '')
    ownership = transaction.get('产权所属', '')
    certificate = transaction.get('房本备件', '')
    elevator = base.get('配备电梯', '')
    if elevator in ('有', '无'):
        result['elevator'] = elevator == '有'
    match = re.search(r"^(\d+)层", result.get('floor') or '')
    if match:
        result['floor_number'] = int(match.group(1))
    # Prefer detail fields. Any list/detail conflict must be retained and held back.
    conflicts = []
    area = numeric(base.get('建筑面积'))
    price = numeric(detail.get('price_text'))
    for field, value in (('area_sqm', area), ('price_wan', price)):
        if value is not None and result.get(field) is not None and abs(value - result[field]) > 0.01:
            conflicts.append(field)
        if value is not None:
            result[field] = value
    unit = numeric(detail.get('unit_text'))
    if unit is not None:
        result['unit_price_yuan'] = unit
    result['conflicts'] = conflicts
    if purpose and purpose != '普通住宅':
        result['qualification'], result['qualification_reason'] = 'excluded', 'nonresidential_or_other_purpose'
    elif (purpose != '普通住宅' or rights != '商品房'
          or ownership not in ('非共有', '共有') or '已上传' not in certificate):
        result['qualification'], result['qualification_reason'] = 'pending_title', 'incomplete_public_title_fields'
    elif conflicts:
        result['qualification'], result['qualification_reason'] = 'pending_conflict', 'list_detail_conflict'
    else:
        result['qualification'], result['qualification_reason'] = 'public_fields_match', None
    # Public claims are not registration verification, including mortgage claims.
    result['title_registry_verified'] = False
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def priority(row):
    floor = row.get('floor') or ''
    floor_band = 0 if '低' in floor else 1 if '中' in floor else 2
    return (not (row.get('elevator') is True or row.get('floor_number') in (1, 2, 3)),
            floor_band, row.get('price_wan', 999), row['url'])


def qualifies(row, filters):
    return (urlsplit(row.get('url', '')).hostname == 'xz.ke.com'
            and row.get('qualification') == 'public_fields_match'
            and not preliminary_filter(row, filters['min_price_wan'], filters['max_price_wan']))


def markdown(value):
    return str(value if value not in (None, '') else '未知').replace('|', '\\|').replace('\n', ' ')


def render_report(run):
    rows = [r for r in run['properties'] if qualifies(r, run['filters'])]
    # Prefer community diversity without pretending different apartments are identical.
    ordered, seen, later = [], set(), []
    for row in sorted(rows, key=priority):
        if row.get('community') in seen:
            later.append(row)
        else:
            seen.add(row.get('community'))
            ordered.append(row)
    selected = (ordered + later)[:run['target']]
    strict = [r for r in rows if r.get('inside_third_ring') is True and r.get('title_registry_verified')]
    lines = ['# 徐州小住宅：公开挂牌发现', '', f"采集时间：{run['collected_at']}。运行ID：`{run['run_id']}`。", '',
             '## 第一阶段结论', '',
             f"贝壳公开详情字段匹配的房源：**{len(rows)}套**；本报告列出**{len(selected)}套**。",
             f"三环内及登记产权均核验的房源：**{len(strict)}套**。",
             ('面积、报价和普通住宅挂牌的存在性可由下列贝壳公开页面复核；完整的“三环内、产权可正常交易、适合长期独居”命题仍未验证。'
              if rows else '本轮未取得可列出的贝壳公开字段匹配候选，不能据此断言市场不存在。'),
             '未找到或未读取不等于市场没有；这不是成交价分析，也不是购买推荐。', '',
             '## 筛选口径', '',
             f"- 城市徐州；面积40-60㎡；最低价不限（参数{run['filters']['min_price_wan']:g}万元），最高{run['filters']['max_price_wan']:g}万元；0元标价进入异常队列，不计有效候选。",
             '- 电梯或1-3楼优先；低/中/高楼层不等于精确楼层，未知电梯不能按有电梯处理。',
             '- 排除明确商办、公寓及非住宅；用途/权属/产权所属/房本备件字段缺失者仅存线索，不列正式发现候选。',
             '- 候选中的产权信息只是平台公开声明，未经登记核验；抵押、共有、转让资格仍需核实。',
             '- 三环边界未核验不称为环内。地址为公开小区地址，不保存房号、经纪人联系方式、聊天或账户信息。',
             '- 生活优先级沿用原项目：安静 > 隔音 > 生活便利 > 价格 > 升值。原100分权重保持安静30、隔音20、密度15、便利15、价格15、流动性5；升值不单独加分。',
             '- 表序是采集展示顺序，不是舒适度排名；未知条件不打分，低价不抵消噪音或隔音缺陷。正式候选仅计贝壳，辅助平台仅作线索。', '',
             '## 候选表', '',
             '| 编号 | 小区 | 地址 | 面积㎡ | 户型 | 楼层 | 电梯 | 总价万 | 单价元/㎡ | 来源 | 挂牌日期 | 采集日期 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    date = run['collected_at'][:10]
    for index, row in enumerate(selected, 1):
        elevator = '有（页面声明）' if row.get('elevator') is True else '无（页面声明）' if row.get('elevator') is False else '未知'
        values = [index, row.get('community'), row.get('address'), row.get('area_sqm'), row.get('layout'),
                  row.get('floor'), elevator, row.get('price_wan'), row.get('unit_price_yuan'),
                  f"[{row.get('source', '来源')}]({row['url']})", row.get('listed_date'), date]
        lines.append('| ' + ' | '.join(markdown(v) for v in values) + ' |')
    lines += ['', '## 初步评分：证据缺失不打分', '',
              '| 编号 | 安静潜力 | 隔音风险 | 居住密度 | 价格 | 三环边界 | 产权公开声明 |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for index, row in enumerate(selected, 1):
        base = row.get('public_base', {})
        structure = base.get('建筑结构')
        sound = f"未知；页面建筑结构为{structure}，不能据此推断实测隔音" if structure else '未知'
        budget = f"在{run['filters']['max_price_wan']:g}万元挂牌上限内；合理成交价未知"
        lines.append(f"| {index} | 未知 | {markdown(sound)} | 未知 | {budget} | 未知 | 普通住宅/商品房；登记未核验 |")
    lines += ['', '## 逐套待核', '']
    for index, row in enumerate(selected, 1):
        transaction = row.get('public_transaction', {})
        community_attrs = row.get('community_attributes', {})
        note = f"产权所属：{markdown(transaction.get('产权所属'))}；抵押：{markdown(transaction.get('抵押信息'))}；房本：{markdown(transaction.get('房本备件'))}（均为平台声明）。"
        if row.get('community_url'):
            note += f" [小区地址来源]({row['community_url']})。"
        if community_attrs.get('物业公司'):
            note += f" 页面物业公司：{markdown(community_attrs['物业公司'])}，不直接推断物业好坏。"
        if '高' in (row.get('floor') or '') or '顶' in (row.get('floor') or ''):
            note += ' 高/顶楼层且电梯未知，与楼层偏好可能不符，仅作存在性线索。'
        lines.append(f"{index}. **{markdown(row.get('community'))}**：{note} 需核验卧室噪音、精确楼层、电梯及地图边界。")
    pending = [r for r in run['properties'] if r.get('qualification') != 'public_fields_match']
    lines += ['', '## 缺口与采集范围', '',
              f"- 本轮读取列表卡片{run['stats']['cards']}条，URL去重后{run['stats']['unique_listings']}条；数值与标题初筛后{run['stats']['numeric_matches']}条。",
              f"- 已尝试详情{run['stats']['detail_attempts']}套；不完整、冲突或排除的已访问线索{len(pending)}套。未访问的初筛线索不算候选。",
              '- 尚缺：三环边界证据、精确楼层/电梯、登记产权、当前真实可售确认及现场居住条件。',
              '- 首页/默认排序样本有平台排序偏差，不是全市普查；挂牌陈旧时仍可能下架或改价。不同平台相似卡片未核验同房时不合并为同一套。',
              f"- 低价发现采用0-{run['filters']['max_price_wan']:g}万元；原生活规划的30万元情景不再作为采集下限。", '',
              '## 访问记录', '', '| 页面 | 状态 | 原因 |', '| --- | --- | --- |']
    for event in run['access_log']:
        lines.append(f"| {markdown(event['url'])} | {markdown(event['status'])} | {markdown(event.get('reason') or '正常读取公开DOM字段')} |")
    if len(selected) < run['target']:
        lines += ['', f"本轮未取得{run['target']}套可列出的公开字段匹配候选，缺{run['target'] - len(selected)}套；不伪造补足。"]
    lines += ['', '## 数据与复现', '', f"本轮结构化证据：`property_discovery/data/runs/{run['run_id']}.json`。",
              '执行 `python3 -m property_discovery.discover --target 10` 可进行下一次有界采集；默认仅读取贝壳2个列表页，最多尝试30套详情。',
              '遇登录墙、验证码或反爬拦截立即停止该平台本轮请求，记录原因；不求解、不换身份、不调用私有API。',
              '这里没有设置后台计划任务；每次运行追加独立快照，候选报告反映最近一次运行，旧快照不覆盖。', '']
    return '\n'.join(lines)


def collect(args, reader=read_page, sleeper=time.sleep):
    now = dt.datetime.now(ZoneInfo('Asia/Shanghai'))
    run_id = now.strftime('%Y%m%dT%H%M%S%f%z')
    list_urls = args.url or (DEFAULT_URLS + (AUXILIARY_URLS if getattr(args, 'auxiliary', False) else []))
    run = {'run_id': run_id, 'collected_at': now.isoformat(timespec='seconds'), 'list_urls': list_urls,
           'filters': {'city': '徐州', 'area_sqm': [40, 60], 'min_price_wan': args.min_price,
                       'max_price_wan': args.max_price, 'third_ring': 'prefer_verified'},
           'target': args.target, 'properties': [], 'access_log': [], 'rejected': [],
           'stats': {'cards': 0, 'unique_listings': 0, 'numeric_matches': 0, 'detail_attempts': 0}}
    script = Path(__file__).with_name('extract.js').read_text(encoding='utf-8')
    blocked_hosts, unique, communities = set(), {}, {}
    run_path = args.output / 'runs' / f'{run_id}.json'

    def checkpoint():
        write_json(run_path, run)

    def visit(url):
        host = validate_url(url)
        if host in blocked_hosts:
            payload = {'status': 'skipped', 'reason': 'host_stopped_after_access_gate'}
        else:
            sleeper(args.delay)
            payload = reader(url, script)
            if payload.get('status') == 'blocked':
                blocked_hosts.add(host)
        run['access_log'].append({'url': url, 'status': payload.get('status', 'error'),
                                  'reason': payload.get('reason'),
                                  'final_url': payload.get('url'),
                                  'read_at': dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')})
        checkpoint()
        return payload

    for url in list_urls:
        payload = visit(url)
        if payload.get('status') != 'ok':
            continue
        for raw in payload.get('rows', []):
            run['stats']['cards'] += 1
            try:
                host = validate_url(raw['url'])
            except (ValueError, KeyError):
                continue
            raw['source'] = '贝壳' if host == 'xz.ke.com' else '房天下' if host == 'xz.esf.fang.com' else '安居客'
            row = normalize(raw)
            # Same URL repeated in price-filtered and unfiltered lists is one listing.
            if row['url'] not in unique:
                unique[row['url']] = row
        checkpoint()
    run['stats']['unique_listings'] = len(unique)
    matches = []
    for row in unique.values():
        reason = preliminary_filter(row, args.min_price, args.max_price)
        if reason:
            run['rejected'].append({'url': row['url'], 'reason': reason,
                                    'area_sqm': row['area_sqm'], 'price_wan': row['price_wan']})
        else:
            matches.append(row)
    run['stats']['numeric_matches'] = len(matches)
    # Auxiliary list cards are retained as leads until their detail adapter is verified.
    for row in matches:
        if urlsplit(row['url']).hostname != 'xz.ke.com':
            row['qualification'], row['qualification_reason'] = 'pending_detail', 'auxiliary_detail_adapter_not_verified'
            run['properties'].append(row)
    attempts = 0
    for row in sorted((r for r in matches if urlsplit(r['url']).hostname == 'xz.ke.com'), key=priority):
        if attempts >= args.max_details:
            break
        if urlsplit(row['url']).hostname in blocked_hosts:
            break
        attempts += 1
        run['stats']['detail_attempts'] = attempts
        item = apply_detail(row, visit(row['url']))
        community_url = item.get('community_url')
        if community_url:
            if community_url not in communities:
                communities[community_url] = visit(community_url)
            community = communities[community_url]
            if community.get('status') == 'ok':
                item['address'] = community.get('address')
                item['community_attributes'] = community.get('attributes', {})
        run['properties'].append(item)
        checkpoint()
        count = sum(qualifies(r, run['filters']) for r in run['properties'])
        if count >= args.target:
            break
    run['unvisited_matches'] = [r for r in matches if r['url'] not in {p['url'] for p in run['properties']}]
    checkpoint()
    write_json(args.output / 'latest.json', run)
    report = render_report(run)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding='utf-8')
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--min-price', type=float, default=0, help='万元；默认不设最低价')
    parser.add_argument('--max-price', type=float, default=50)
    parser.add_argument('--target', type=int, default=10)
    parser.add_argument('--max-details', type=int, default=30)
    parser.add_argument('--delay', type=float, default=2, help='读取间隔秒，最低2秒')
    parser.add_argument('--url', action='append', help='公开列表URL，可重复；不自动无限翻页')
    parser.add_argument('--auxiliary', action='store_true', help='额外读取辅助平台列表，但候选仍只计贝壳')
    parser.add_argument('--output', type=Path, default=Path('property_discovery/data'))
    parser.add_argument('--report', type=Path, default=Path('candidate_properties.md'))
    args = parser.parse_args()
    if (not all(math.isfinite(v) for v in (args.min_price, args.max_price, args.delay))
            or not 0 <= args.min_price < args.max_price <= 50 or args.delay < 2
            or not 1 <= args.target <= 30 or not 1 <= args.max_details <= 50
            or args.url and len(args.url) > 10):
        parser.error('Invalid bounds: price 0..50, delay >=2, target 1..30, details 1..50, <=10 list URLs')
    try:
        run = collect(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'run_id': run['run_id'], 'stats': run['stats'],
                      'public_field_matches': sum(qualifies(r, run['filters']) for r in run['properties']),
                      'report': str(args.report)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
