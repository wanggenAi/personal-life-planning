"""Separate public evidence, unresolved risks and on-site verification."""

import re


UNKNOWN = ('', '暂无', '暂无数据', '暂无信息', '未知')
CHINESE_NUMBERS = dict(zip('一二三四五六七八九', range(1, 10)))


def floor_integer(value):
    if value.isdigit():
        return int(value)
    if value == '十':
        return 10
    if '十' in value:
        left, right = value.split('十', 1)
        return CHINESE_NUMBERS.get(left, 1) * 10 + CHINESE_NUMBERS.get(right, 0)
    return CHINESE_NUMBERS.get(value)


def floor_and_elevator(row):
    base = row.get('public_base', {})
    sources = [('结构化楼层', base.get('所在楼层', '')),
               ('标题', row.get('title', ''))]
    sources += [(f'房源描述/{key}', text) for key, text in row.get('features', {}).items()]
    sources += [('公开带看反馈', text) for text in row.get('feedback', [])]
    floor_claims, elevator_claims = [], []
    for label, text in sources:
        for match in re.finditer(r'(?<![\d共总])([1-9]\d?|[一二三四五六七八九十]{1,3})\s*[楼层]', text):
            before, after = text[max(0, match.start() - 8):match.start()], text[match.end():match.end() + 8]
            if re.search(r'共|总高|总层|楼高|地上|一共', before) or re.search(r'同户型|都有|可选|以上|以下|到|至', after):
                continue
            # Ranges and hypothetical/nearby floors are not this apartment's floor.
            if re.search(r'楼上|楼下|隔壁|对面|楼栋|加装|计划', before) or re.search(r'[-~～至到]', before[-1:]):
                continue
            number = floor_integer(match.group(1))
            if number:
                floor_claims.append({'value': number, 'text': text[:180], 'kind': label, 'source_url': row['url']})
        negative = re.search(r'无电梯|没有电梯|不带电梯|未配备电梯|步梯', text)
        positive = re.search(r'有电梯|配有电梯|带电梯|电梯入户|电梯房', text)
        # A mixed estate description does not identify this building's elevator.
        mixed_estate = '小区' in text and '步梯房' in text and '电梯房' in text
        if (negative or positive) and not mixed_estate:
            elevator_claims.append({'value': False if negative else True, 'text': text[:180],
                                    'kind': label, 'source_url': row['url']})
    explicit_elevator = base.get('配备电梯') or base.get('电梯')
    if explicit_elevator in ('有', '无'):
        elevator_claims.append({'value': explicit_elevator == '有', 'text': explicit_elevator,
                                'kind': '结构化电梯字段', 'source_url': row['url']})
    floor_values, elevator_values = ({x['value'] for x in floor_claims}, {x['value'] for x in elevator_claims})
    floor = next(iter(floor_values)) if len(floor_values) == 1 else None
    elevator = next(iter(elevator_values)) if len(elevator_values) == 1 else None
    total = re.search(r'共\s*(\d+)\s*层', base.get('所在楼层', '') or row.get('floor', ''))
    total = int(total.group(1)) if total else None
    conflicts = []
    if len(floor_values) > 1 or floor is not None and total is not None and floor > total:
        conflicts.append('floor_claim_conflict')
        floor = None
    if len(elevator_values) > 1:
        conflicts.append('elevator_claim_conflict')
    if conflicts:
        status = 'pending_conflict'
    elif elevator is False and floor is not None and floor >= 4:
        status = 'excluded_walkup_above_3'
    elif elevator is True:
        status = 'eligible_next_round' if floor is not None else 'elevator_yes_floor_pending'
    elif floor in (1, 2, 3):
        status = 'eligible_next_round'
    else:
        status = 'pending_floor_or_elevator'
    return {'floor_number': floor, 'total_floors': total, 'elevator': elevator,
            'floor_evidence': floor_claims, 'elevator_evidence': elevator_claims,
            'floor_status': status, 'floor_conflicts': conflicts,
            'evidence_level': 'public_platform_claims_not_on_site'}


def community_key(row):
    url = row.get('community_url')
    if url:
        match = re.search(r'/xiaoqu/(\d+)', url)
        if match:
            return 'ke:' + match.group(1)
    # Do not merge identically named estates in different districts.
    return 'name:' + re.sub(r'\s+', '', row.get('community') or '') + ':' + (row.get('region') or row.get('search_region') or '')


def environment(row):
    nearby = row.get('surroundings', {})
    evidence = []
    for category in ('medical', 'education', 'shopping', 'traffic'):
        for poi in nearby.get(category, [])[:3]:
            if not poi.get('name') or not poi.get('distance_text'):
                continue
            evidence.append({'category': category, 'name': poi['name'], 'distance': poi['distance_text'],
                             'source_url': poi.get('source_url', row.get('community_url')),
                             'level': 'platform_map_display', 'distance_origin': 'community_reference_not_apartment',
                             'actual_noise_verified': False})
    claims = []
    for key, text in row.get('features', {}).items():
        if re.search(r'铁路|火车|高架|主干道|临街|不临|内街|内部|医院|学校|商场|夜市|餐饮|工地|施工|设备|电梯井', text):
            claims.append({'section': key, 'text': text[:220], 'source_url': row['url'],
                           'level': 'public_description_not_independent_measurement'})
    attributes = row.get('community_attributes', {})
    density = {key: attributes.get(key) if attributes.get(key) not in UNKNOWN else None
               for key in ('房屋总数', '楼栋总数', '容积率', '绿化率')}
    density.update({'梯户比例': row.get('public_base', {}).get('梯户比例'),
                    '楼间距': None, '停车拥挤': None, '电梯服务户数': None,
                    '楼栋布局': '仅能通过公开照片/地图进一步核验，尚未量测'})
    return {'environment_evidence': evidence, 'noise_claims': claims, 'density': density,
            'actual_quiet_verified': False, 'sound_insulation_verified': False,
            'road_distance_from_building': None, 'rail_distance_from_building': None,
            'building_position_verified': False, 'window_street_relation_verified': False,
            'environment_evidence_level': 'public_nearby_sources' if evidence else 'description_only' if claims else 'insufficient'}


def investigate(row):
    result = dict(row)
    result.update(floor_and_elevator(row))
    result.update(environment(row))
    info = row.get('info', '')
    year = re.search(r'\b((?:19|20)\d{2})年', info)
    result['built_year'] = int(year.group(1)) if year else None
    result['sound_evidence'] = {'built_year': result['built_year'],
                              'structure': row.get('public_base', {}).get('建筑结构'),
                              'orientation': row.get('public_base', {}).get('房屋朝向'),
                              'rooms': row.get('rooms', []), 'floor_slab': None, 'walls': None,
                              'doors_windows_acoustic_spec': None, 'elevator_shaft_adjacency': None,
                              'equipment_room_adjacency': None, 'shared_walls_count': None,
                              'source_url': row['url'], 'actual_sound_insulation_verified': False}
    result['onsite_checks'] = [
        '工作日早间与周末晚间，在实际卧室分别开关窗观察道路、商业、学校和医院声音；核对楼栋是否临街及窗户面向。',
        '请楼上正常走路、挪椅并使用卫生间，在卧室辨认脚步、冲水和管道声；未经许可不安排干扰性测试。',
        '经相邻住户同意，以正常说话和楼道开关门测试墙体、入户门传声；核实共墙数量。',
        '电梯上下运行或水泵启动时检查卧室低频声和结构振动；定位电梯井、机房及老旧管道。',
        '查验楼板、墙体、门窗及改造资料，不能用房龄、混合结构或装修承诺替代隔音测试。',
        '夜间观察出入口、停车、垃圾点和公共空间，核对楼间距、每层户数与电梯实际服务户数。']
    if result['floor_status'] == 'excluded_walkup_above_3':
        result['qualification'], result['qualification_reason'] = 'excluded', 'confirmed_public_walkup_above_3'
    return result


def history_rows(row):
    results = []
    for item in row.get('history', []):
        def number(text):
            match = re.search(r'\d+(?:\.\d+)?', (text or '').replace(',', ''))
            return float(match.group()) if match else None
        area, total = number(item.get('area_text')), number(item.get('total_text'))
        date = item.get('deal_date', '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) or area is None or total is None:
            continue
        same_area = row['area_sqm'] * 0.8 <= area <= row['area_sqm'] * 1.2
        same_layout = re.match(r'\d+室\d+厅', item.get('layout', ''))
        target_layout = re.match(r'\d+室\d+厅', row.get('layout', ''))
        layout_match = bool(same_layout and target_layout and same_layout.group() == target_layout.group())
        result = dict(item, area_sqm=area, total_price_wan=total,
                      area_match=same_area, layout_match=layout_match,
                      exact_floor_match=None, elevator_match=None,
                      comparability='面积初步可比；楼层、电梯、朝向、装修与时间尚需匹配' if same_area else '面积不同，不直接可比')
        if same_area:
            result['comparability'] = ('面积及室厅数初步匹配' if layout_match else '仅面积初步匹配，室厅数不同或缺失') + '；精确楼层/电梯/装修未匹配，不用于合理买价'
        results.append(result)
    return sorted(results, key=lambda d: (not d['area_match'], not d['layout_match'],
                                         abs(d['area_sqm'] - row['area_sqm']), d['deal_date']))
