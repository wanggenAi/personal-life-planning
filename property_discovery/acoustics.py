"""Traceable acoustic investigations, not inferred decibel performance."""

import re
import json
from pathlib import Path

from tools.score_property import score


DIMENSIONS = ('structure', 'materials', 'layout', 'external', 'equipment', 'field')


def assess(row):
    url, community_url = row['url'], row.get('community_url') or row['url']
    evidence, risks, favorable = [], [], []

    def add(dimension, grade, fact, source, scope='apartment_claim'):
        evidence.append({'dimension': dimension, 'grade': grade, 'fact': fact,
                         'source_url': source, 'scope': scope,
                         'retrieved_at': row.get('community_read_at') if source == community_url else row.get('detail_read_at')})

    base = row.get('public_base', {})
    for key in ('建筑结构', '建筑类型'):
        if base.get(key):
            add('structure', 'D', f'{key}：{base[key]}；未取得构造或竣工资料', url)
    if row.get('built_year'):
        add('structure', 'D', f"建成年份：{row['built_year']}；不代表楼板/墙体性能", url)
    for room in row.get('rooms', []):
        if room and '卧室' in room[0]:
            add('layout', 'D', '分间字段：' + ' / '.join(room), url)
    ratio = base.get('梯户比例', '')
    if ratio and '暂无' not in ratio:
        add('layout', 'D', '梯户比例：' + ratio, url)
        # It is a shared-circulation investigation trigger, never a noise verdict.
        match = re.search(r'(\d+|[一二三四五六七八九十]{1,4})户', ratio)
        if match and match.group(1) in ('十四', '二十八', '14', '28'):
            risks.append('每层多户共用交通空间：核查走廊门声、共墙数量及电梯运行；不是已确认噪声超标')
        if ratio in ('一梯两户', '一梯二户', '1梯2户'):
            favorable.append('公开梯户比例较少，可优先核查共墙和走廊；隔音仍未经验证')
    for key in ('房屋总数', '楼栋总数', '容积率'):
        value = row.get('density', {}).get(key)
        if value:
            add('layout', 'D', f'贝壳小区字段{key}：{value}；非竣工数据', community_url, 'community_not_building')
    for item in row.get('environment_evidence', []):
        add('external', 'C', f"{item['name']}约{item['distance']}；地图参考点距离，不是卧室距离",
            item['source_url'], 'community_reference_not_apartment')
        if item['category'] in ('medical', 'education', 'shopping'):
            label = {'medical': '医疗车辆/急诊', 'education': '广播/上下学', 'shopping': '营业/装卸/人流'}[item['category']]
            risks.append(f"{item['name']}：需定位{label}声源、营业时段与卧室关系；实际声压未知")
    review = row.get('environment_review', {})
    for item in review.get('facts', []):
        add('external', 'C', item['text'], item['source_url'], 'community_map_visual_review_not_apartment')
        evidence[-1]['retrieved_at'] = review.get('reviewed_at')
    if review.get('favorable_lead'):
        favorable.append(review['favorable_lead'])
    risks.extend(review.get('risks', []))
    for key, claim in row.get('features', {}).items():
        if re.search(r'不临街|不靠路|内部|内街|边户|电梯井|高架|管道|底商|阁楼|步梯|电梯', claim):
            add('equipment' if '设备' in claim or '管道' in claim else 'layout', 'D', f'{key}：{claim[:220]}', url)
        if re.search(r'不临街|不靠路|内街', claim):
            favorable.append('描述称不临街：可优先定位卧室窗户复核；仅D级线索，不是环境事实')
        if '边户' in claim:
            favorable.append('描述称边户：可核查是否减少邻户共墙；未取得完整户型/连接资料')
        if re.search(r'高架|底商|阁楼', claim):
            risks.append(f'描述需核查：{claim[:120]}；核对外部/结构噪声、用途与居住条件')
    if row.get('floor_number') == row.get('total_floors') and row.get('floor_number'):
        favorable.append('公开楼层称顶楼：上方住宅脚步路径可能减少，屋面设备/雨噪/漏水仍须核查')
    elif row.get('floor_number') == 1:
        risks.append('公开描述1楼：核查入口、停车及楼道开关门，楼上撞击声路径仍存在')
    gaps = {
        'structure': ['楼板厚度及连接', '分户墙构造', '侧向传声路径', '竣工/改造图纸'],
        'materials': ['具体材料厚度与层序', '浮筑层及声桥', '门窗构件检测报告', '密封及安装质量'],
        'layout': ['楼栋定位及卧室朝向与道路关系', '共墙数量', '上下层厨卫/卧室对应', '电梯井邻接'],
        'external': ['主干道/铁路/夜市/工地楼栋级调查', '昼夜声源工况', '实际室内噪声'],
        'equipment': ['电梯/水泵/变压器位置', '隔振基础与管道支架', '排水立管与卧室共墙', '设备运行频谱'],
        'field': ['规范化空气声与撞击声测量', '校准与背景修正', '混响及频带数据', '夜间卧室和设备测量'],
    }
    return {'evidence': evidence, 'favorable_leads': list(dict.fromkeys(favorable)),
            'risk_questions': list(dict.fromkeys(risks)), 'gaps': gaps,
            'evidence_counts': {grade: sum(e['grade'] == grade for e in evidence) for grade in 'ABCD'},
            'actual_performance_verified': False, 'structure_materials_verified': False,
            'quiet_rating': None, 'sound_rating': None,
            'conclusion': '有可追溯调查线索；没有A级实测或B级构造证据，不证明安静/隔音合格'}


def scored_investigation(row):
    """Use existing six weights once; public clues cannot supply quiet/sound ratings."""
    gates = {'inside_third_ring': row.get('inside_third_ring'),
             'residential_clear_title': True if row.get('title_registry_verified') else None}
    result = score({'community': row.get('community'), 'area_sqm': row.get('area_sqm'),
                    'price_wan': row.get('price_wan'), 'floor': row.get('floor_number'),
                    'total_floors': row.get('total_floors'), 'elevator': row.get('elevator'),
                    'gates': gates, 'ratings': {}, 'evidence': {},
                    'price_evidence_confidence': 'unknown'})
    result['interpretation'] = 'C表示证据不完整，不表示隔音中等；区间不是价格或品质排序'
    return result


def enrich(row):
    result = dict(row)
    reviews = json.loads(Path(__file__).with_name('data').joinpath('map_reviews.json').read_text(encoding='utf-8'))
    review = reviews['communities'].get(row.get('community_url'))
    if review:
        result['environment_review'] = dict(review, reviewed_at=reviews['reviewed_at'])
        if review.get('scope_label'):
            result['scope_label'] = review['scope_label']
    result['acoustics'] = assess(result)
    result['score_assessment'] = scored_investigation(result)
    conflicts = []
    descriptions = ' '.join(row.get('features', {}).values())
    if re.search(r'两梯二十八户|两梯十四户', row.get('public_base', {}).get('梯户比例', '')):
        conflicts.append('平台梯户比例涉及14/28户，共用空间密度、走廊布局及服务范围待核')
    if re.search(r'做民宿|办公室|工作室|阁楼', descriptions):
        conflicts.append('描述涉及民宿/办公或阁楼，正常居住用途、邻户使用及产权范围须额外核查')
    result['living_conflicts'] = conflicts
    return result
