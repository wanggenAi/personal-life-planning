"""Residence-first V2 report with one representative per community."""

from .investigate import community_key, history_rows


def text(value):
    return str(value if value not in (None, '') else '未知').replace('|', '\\|').replace('\n', ' ')


def representative_priority(row):
    # Evidence completeness is not an acoustic-quality score.
    known_density = sum(value not in (None, '', '暂无数据', '暂无信息')
                        for value in row.get('density', {}).values())
    price = row.get('price_wan', 999)
    price_band = 0 if 20 <= price <= 35 else 1 if 35 < price <= 45 else 2 if 45 < price <= 50 else 3
    return (bool(row.get('living_conflicts')),
            not bool(row.get('acoustics', {}).get('favorable_leads')),
            row.get('floor_status') != 'eligible_next_round',
            not bool(row.get('environment_evidence')), -known_density,
            price_band, abs(row.get('area_sqm', 50) - 50), row.get('url', ''))


def representatives(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(community_key(row), []).append(row)
    result = []
    for group in grouped.values():
        ordered = sorted(group, key=representative_priority)
        result.append((ordered[0], ordered[1:]))
    return sorted(result, key=lambda pair: representative_priority(pair[0]))


def elevator_text(row):
    value = row.get('elevator')
    return '有（公开声明）' if value is True else '无（公开声明）' if value is False else '未知'


def floor_text(row):
    number = row.get('floor_number')
    return f"{number}楼（公开描述；非现场核验）" if number is not None else f"精确楼层未知；平台分段：{text(row.get('floor'))}"


def noise_summary(row):
    evidence = row.get('environment_evidence', [])
    items = []
    for category in ('medical', 'education', 'shopping'):
        item = next((x for x in evidence if x['category'] == category), None)
        if item:
            items.append(f"{text(item['name'])} {text(item['distance'])}")
    return '；'.join(items) if items else '周边距离未取得，只有描述或地址线索'


def render_card(row, alternatives, index, run):
    region = row.get('region') or row.get('search_region')
    base = row.get('public_base', {})
    source = f"[贝壳房源原页]({row['url']})"
    community_url = row.get('community_url')
    community_source = f"[贝壳小区/地图/成交页]({community_url})" if community_url else '小区页未取得'
    lines = [f"### {index}. {text(row.get('community'))} · {text(region)}", '',
             f"**{text(row.get('area_sqm'))}㎡ · {text(row.get('layout'))} · 挂牌{text(row.get('price_wan'))}万元**。{source}；{community_source}。",
             f"挂牌单价：{text(row.get('unit_price_yuan'))}元/㎡（平台字段，非成交价）。",
             f"地址：{text(row.get('address'))}。挂牌日期：{text(row.get('listed_date'))}；资料获取：{row.get('detail_read_at', run['collected_at'])}。",
             f"楼层：{floor_text(row)}；电梯：{elevator_text(row)}；楼层状态：`{row.get('floor_status', 'pending')}`。",
             f"范围：{text(row.get('scope_label', '三环边界未核验'))}；所属检索片区：{text(', '.join(x['name'] for x in row.get('search_scopes', [])))}。", '',
             '**安静与周边环境**', '']
    evidence = row.get('environment_evidence', [])
    if evidence:
        for category, label in (('medical', '医疗'), ('education', '教育'), ('shopping', '商业'), ('traffic', '交通')):
            items = [x for x in evidence if x['category'] == category][:2]
            if items:
                lines.append(f"- {label}：" + '；'.join(f"{text(x['name'])}约{text(x['distance'])}" for x in items)
                             + f"。来源：{community_source}（百度地图在贝壳页显示）。")
    else:
        lines.append('- 周边地图距离尚未取得，不以地址或小区名称推断安静。')
    for access in row.get('map_access', []):
        if access.get('status') == 'unavailable':
            lines.append(f"- 地图读取缺口：{text(access.get('category'))}，原因`{text(access.get('reason'))}`。未取得该类结果不能解释为周边没有设施。")
    for claim in row.get('noise_claims', [])[:2]:
        lines.append(f"- 描述线索（非独立核验）：{text(claim['section'])}“{text(claim['text'][:120])}”。来源：{source}。")
    review = row.get('environment_review', {})
    for fact in review.get('facts', []):
        lines.append(f"- 地图/资料复核：{text(fact['text'])}。来源：[{text(fact.get('source_name', '公开资料'))}]({fact['source_url']})。")
    if review.get('image'):
        lines += ['', f"![本小区公开地图复核，仅参考点定位]({review['image']})", '',
                  f"地图来源：{community_source}；复核{review.get('reviewed_at')}。地图参考点不是具体房源位置。"]
    lines += ['- 上述距离是平台小区参考点距离，计算口径未说明，不是楼栋或卧室距离；近医院/学校/商场表示需核验相关声源，不等于已经噪音超标。',
              '- 主干道/高架、铁路及货运、夜市娱乐、医院急诊入口、学校广播与施工：未完成楼栋级排查。楼栋是否内部、卧室是否背街仍需确认。', '',
              '**隔音证据与缺口**', '',
              f"- 房源建成年份：{text(row.get('built_year'))}；结构：{text(base.get('建筑结构'))}；整体朝向：{text(base.get('房屋朝向'))}。来源：{source}。"]
    rooms = [x for x in row.get('rooms', []) if x and '卧室' in x[0]]
    if rooms:
        lines.append('- 分间信息：' + '；'.join(' / '.join(text(v) for v in room) for room in rooms[:3]) + f"。来源：{source}。窗型/朝向不证明隔音或是否临街。")
    lines += ['- 楼板/共墙材料厚度、入户门及窗户隔声指标、电梯井/设备间邻接、管道振动资料未知。房龄与结构不能证明隔音好坏；实际脚步、说话、楼道及低频传声均未经现场验证。', '',
              '**居住密度证据**', '']
    density = row.get('density', {})
    lines.append(f"- 总户数：{text(density.get('房屋总数'))}；楼栋：{text(density.get('楼栋总数'))}；容积率：{text(density.get('容积率'))}；绿化率：{text(density.get('绿化率'))}。来源：{community_source}。")
    lines.append(f"- 梯户比例：{text(density.get('梯户比例'))}（房源页）；电梯服务户数、楼间距、停车及公共空间拥挤程度未知。高/低容积率不直接等于吵/安静。")
    property_company = row.get('community_attributes', {}).get('物业公司')
    if property_company:
        lines.append(f"- 平台物业公司字段：{text(property_company)}。需要现场核实管理状态，不能仅凭字段认定物业极差。")
    lines += ['', '**历史成交：与本套挂牌分开**', '']
    deals = history_rows(row)
    if deals:
        lines += ['| 贝壳显示成交日期 | 面积㎡/户型 | 历史成交万元 | 楼层 | 可比性 | 来源 |',
                  '| --- | --- | --- | --- | --- | --- |']
        for deal in deals[:3]:
            lines.append('| ' + ' | '.join([text(deal['deal_date']), f"{text(deal['area_sqm'])}/{text(deal.get('layout'))}",
                                           text(deal['total_price_wan']), text(deal.get('floor')),
                                           text(deal['comparability']), f"[小区页记录]({deal['source_url']})"]) + ' |')
        lines.append('仅保留贝壳可见历史记录；样本数量、楼层、电梯、装修及时间可比性不足，不给合理购买价，不预测继续降价。')
    else:
        lines.append(f"可靠历史成交未取得。{community_source}；不以小区参考均价代替成交，也不判断本套购买价是否合理。")
    lines += ['', '**符合与未确认**', '',
              '- 已有公开字段支持：40—60㎡、50万元以内、普通住宅/商品房用途与平台产权字段；不等于登记机关产权核验。',
              f"- 楼层/电梯：{floor_text(row)}，{elevator_text(row)}。"
              + ('按公开信息可进入下一轮，仍需现场及登记确认。' if row.get('floor_status') == 'eligible_next_round'
                 else '条件仍不完整，不能列为已满足全部要求。'),
              '- 未证明：长期安静、实际隔音、公共空间不拥挤、楼栋/窗户位置及地理范围。',
              '- 本套核验重点：' + ('楼层或电梯未知，先取得明确证据，避免无电梯4楼及以上。' if row.get('floor_status') != 'eligible_next_round' else '核对公开楼层/电梯声明，先测试睡眠卧室。')]
    if row.get('price_wan', 50) < 20:
        lines.append('- 低于20万元：额外核查楼层、产权/占用、维修、采光及低价原因，不因为便宜降低生活要求。')
    if row.get('floor_evidence') or row.get('elevator_evidence'):
        for item in (row.get('floor_evidence', [])[:2] + row.get('elevator_evidence', [])[:2]):
            lines.append(f"- 楼层/电梯证据：{text(item['kind'])}“{text(item['text'][:120])}”。来源：{source}；如相互矛盾保持未知。")
    lines += ['', '**现场隔音与生活核验清单**', '']
    engineering = row.get('acoustics', {})
    if engineering:
        counts = engineering['evidence_counts']
        lines += [f"- 工程证据：A={counts['A']}、B={counts['B']}、C={counts['C']}、D={counts['D']}。证据等级不是隔音等级。",
                  '- 有利条件：' + ('；'.join(engineering['favorable_leads']) or '未取得能够确认安静有利条件的构造/布局证据'),
                  '- 风险调查：' + ('；'.join(engineering['risk_questions'][:4]) or '声源与传声路径尚缺具体资料，不能当作已排除'),
                  '- 结构/材料真实可靠资料：未取得B级构造资料；实际隔音未取得A级测量。',
                  f"- 原评分体系：{row['score_assessment']['grade']}（证据不完整）；安静30分、隔音20分均暂不赋值，不增加第七项或用缺失填中分。",
                  f"- [本套六维工程证据与资料缺口](property_discovery/acoustic_investigations.md#{row['url'].split('/')[-1].split('.')[0]})；[规范与现场测量方法](property_discovery/acoustic_reference.md)。"]
    if row.get('living_conflicts'):
        lines.append('- 暂停优先调查的居住冲突：' + '；'.join(row['living_conflicts']) + '。先核查，不因便宜忽略。')
    lines.extend('- ' + item for item in row.get('onsite_checks', []))
    images = row.get('images', [])
    if images:
        lines += ['', f"[查看贝壳公开房源图片]({images[0]})（原页引用，可能含VR渲染；图片不能证明安静或隔音）。"]
    if alternatives:
        lines += ['', '同小区备选（不再占首页名额）：' + '；'.join(
            f"[{text(x.get('area_sqm'))}㎡/{text(x.get('price_wan'))}万]({x['url']})" for x in alternatives)]
    lines.append('')
    return lines


def render_v2(run):
    if run.get('schema_version', 1) >= 4:
        return render_v4(run)
    rows = [row for row in run['properties'] if row.get('qualification') == 'public_fields_match']
    pairs = representatives(rows)
    basics = [row for row in rows if row.get('floor_status') == 'eligible_next_round']
    confirmed = [row for row in basics if row.get('location_allowed_verified') is True]
    formal = [pair for pair in pairs if pair[0] in confirmed]
    deferred = [pair for pair in pairs if pair[0].get('living_conflicts')]
    pending = [pair for pair in pairs if pair not in formal and pair not in deferred]
    env = [row for row in rows if row.get('environment_evidence')]
    excluded = [row for row in run['properties'] if row.get('qualification') == 'excluded']
    coverage = run.get('coverage', [])
    lines = ['# 徐州自由居所 V3：真实住宅声学调查', '', '## 第一部分：搜索结果总览', '',
             f"截至{run['collected_at']}：取得**{len(rows)}套**贝壳普通住宅公开字段匹配线索，分布于**{len(pairs)}个不同小区**。每个小区只展示一套代表房源，同小区备选不重复占位。",
             f"- 面积、挂牌价、精确楼层及电梯限制均有公开证据支持：**{len(basics)}套**。",
             f"- 再加地理范围初核通过：**{len(confirmed)}套**。南区环外补充单列，不冒称三环内。",
             f"- 有周边设施距离证据：**{len(env)}套**；**实际安静、隔音与生活密度完全核验：0套**。周边地图证据不是睡眠质量证明。",
             f"- 因公开条件明确不符而排除：**{len(excluded)}套**；其他缺字段的记录保留在线索，不当作合格。",
             '- 本次优先级：安静 > 隔音 > 居住密度 > 价格；面积40—60㎡，优先约50㎡，无电梯仅1—3楼。20—35万元优先，35—45可接受，45—50补充，低于20另查低价原因。',
             ('- 是否值得继续：下列真实、不同小区的对象可补充调查；目前没有证据足以确认任何一套适合长期安静独居。下一步先补楼层/电梯与楼栋定位，再预约白天、夜间隔音测试。' if pairs else '- 本轮没有取得可展示的有效住宅线索，访问原因见覆盖表；不能声称有候选。'), '',
             '### 优先调查入口（不是购买推荐）', '',
             '| 小区 | 面积㎡/挂牌万元 | 精确楼层/电梯 | 已取得的环境线索 | 首要缺口 |',
             '| --- | --- | --- | --- | --- |']
    for row, _ in [pair for pair in pairs if pair not in deferred]:
        favorable = '；'.join(row.get('acoustics', {}).get('favorable_leads', [])[:1])
        lines.append(f"| [{text(row.get('community'))}]({row['url']}) | {text(row.get('area_sqm'))}/{text(row.get('price_wan'))} | {floor_text(row)}；{elevator_text(row)} | {(favorable + '；') if favorable else ''}{noise_summary(row)} | 楼栋/窗户与噪声实测，范围和未明楼层/电梯 |")
    lines += ['', '### 实际搜索覆盖', '', '| 区域/片区 | 状态 | 初筛线索/不同小区 | 范围说明 | 来源 |',
              '| --- | --- | --- | --- | --- |']
    for entry in coverage:
        count = f"{entry.get('numeric_matches', 0)}/{entry.get('communities', 0)}"
        status = entry['status']
        if entry.get('reason'):
            status += ': ' + entry['reason']
        if entry['status'] == 'ok' and not entry.get('numeric_matches'):
            status += '；本次已读页面无数值匹配，不代表整个片区没有'
        lines.append('| ' + ' | '.join([text(entry['name']), text(status), count,
                                       '南区允许补充，边界另核' if 'south' in entry.get('scope', '') else '行政区不是三环边界',
                                       f"[贝壳列表]({entry['url']})"]) + ' |')
    if len(pairs) < run['target']:
        lines += ['', f"**未达到{run['target']}个不同小区，缺{run['target'] - len(pairs)}个。**停止原因：{text(run.get('stop_reason'))}。不放宽面积、价格、用途或无电梯楼层限制补足数量。"]
    lines += ['', '## 第二部分：已初核基本条件的房源', '',
              '此区要求面积、价格、住宅用途、楼层/电梯和允许地理范围有证据支持；安静、隔音仍需现场核验。']
    if not formal:
        lines += ['', '**目前没有同时满足以上已确认门槛的房源。**下面的待调查对象不冒充正式合格候选。']
    for index, (row, alternatives) in enumerate(formal, 1):
        lines += render_card(row, alternatives, index, run)
    lines += ['', '## 第三部分：值得继续调查的真实房源', '',
              '这些是有真实贝壳来源的住宅线索，不是已完全合格房源。噪音源、结构与密度字段尽可能给证据；未知楼层/电梯、边界、楼栋及实测保持未知。']
    for index, (row, alternatives) in enumerate(pending, 1):
        lines += render_card(row, alternatives, index, run)
    if deferred:
        lines += ['', '## 暂停优先：密度或使用描述冲突', '',
                  '以下挂牌虽有普通住宅字段，但公共空间密度或民宿/办公/阁楼描述需特别核验；不以低价把它们放在首页主要候选中。']
        for index, (row, alternatives) in enumerate(deferred, 1):
            lines += render_card(row, alternatives, index, run)
    lines += ['', '## 明确排除与其他待补线索', '', '| 小区 | 面积㎡/挂牌万元 | 房源 | 原因 |', '| --- | --- | --- | --- |']
    for row in run['properties']:
        if row.get('qualification') != 'public_fields_match':
            reason = ('公开描述步梯' + str(row.get('floor_number')) + '楼，超出无电梯1—3楼限制'
                      if row.get('qualification_reason') == 'confirmed_public_walkup_above_3'
                      else text(row.get('qualification_reason')))
            lines.append(f"| {text(row.get('community'))} | {text(row.get('area_sqm'))}/{text(row.get('price_wan'))} | [贝壳]({row['url']}) | {reason} |")
    lines += ['', '## 方法、证据边界与复现', '',
              '- V1重复原因：仅读默认首页和价格页，达到房源套数就停止；报告阶段去重太晚。V2分区域片区、按小区ID去重、轮流调查不同区域，先读完有限覆盖计划，再以有效小区数或访问/数量上限停止。',
              '- 未确认楼层或电梯不算门槛通过；结构、房龄、容积率和周边距离不直接等于安静/吵或隔音好/差。',
              '- 所有挂牌与历史成交仅来自贝壳。公开描述是声明；地图距离是平台参考点数据；实际噪声、楼板传声和密度体验要到具体房间核验。',
              '- 遇登录墙、验证码及访问限制立即停止平台访问，不绕过；截图、坐标不用于猜具体房号。',
              f"- 本轮原始公开字段、来源及获取时间：`property_discovery/data/runs/{run['run_id']}.json`。旧快照保留。", 
              '- 执行：`python3 -m property_discovery.discover --target 20`。边界：有限搜索计划、最多60套详情，最多2套/小区；不无限扩区或翻页。', '']
    return '\n'.join(lines)


def render_v4(run):
    rows = [r for r in run['properties'] if r.get('qualification') == 'public_fields_match']
    visits = [r for r, _ in representatives(rows) if r.get('visit_ready')][:5]
    focuses = [r for r in rows if r.get('focused_investigation')]
    excluded = [r for r in run['properties'] if r.get('qualification') == 'excluded']
    labels = {'inside_reference': '环内参考点初核', 'outside_reference': '环外参考点初核',
              'near_boundary': '边界附近待楼栋核实', 'location_conflict': '定位资料冲突', 'unknown': '坐标未知'}
    lines = ['# 徐州自由居所 V4：实地调查名单', '',
             f"资料更新：{run['collected_at']}。本轮仅复核已有30套，未增加搜索或小区。挂牌、成交分别保留原采集日期。", '',
             f"- 有效住宅公开线索：**{len(rows)}套 / {len(representatives(rows))}个小区**；住宅登记与交易资格仍需查验。",
             f"- 三环内小区参考点初核：**{sum(r.get('inside_third_ring') is True for r in rows)}套**；具体楼栋测绘确认：**0套**。不能把这两个数字混用。",
             f"- 楼层偏好初筛通过：**{sum(r.get('floor_status') == 'eligible_next_round' for r in rows)}套**（平台公开证据；不是现场确认）。",
             f"- 本轮重点逐套环境/布局复核：**{len(focuses)}套**；原有地图周边信息{sum(bool(r.get('environment_evidence')) for r in rows)}套，不等同于已排除噪声。",
             f"- 可安排有明确核验任务的实地调查：**{len(visits)}套**；安静、隔音、低密度全部验证：**0套**；明确楼层不符排除：**{len(excluded)}套**。", '',
             '**这不是买房推荐。**名单表示值得去获取证据，不表示已满足安静要求；电梯未知仍如实保留。公开明确1—3楼即可通过楼层偏好，矛盾字段则不能通过。', '',
             '## 先看哪些房子', '', '| 房源 | 面积 / 挂牌价 | 楼层 / 电梯 | 为什么值得现场调查 |', '| --- | --- | --- | --- |']
    if not visits:
        lines.append('| 暂无 | — | — | 关键证据未通过；见下方具体阻碍 |')
    for r in visits:
        f = r['focused_investigation']
        lines.append(f"| [{r['community']}]({r['url']}) | {r['area_sqm']}㎡ / {r['price_wan']}万 | {floor_text(r)} / {elevator_text(r)} | {text('；'.join(f['facts'][:2]))} |")
    for r in sorted(focuses, key=lambda r: (not r.get('visit_ready'), r['price_wan'])):
        f = r['focused_investigation']
        status = '可安排实地调查，非购买推荐' if r.get('visit_ready') else '先补资料，暂不预约'
        lines += ['', f"### {r['community']} · {r['area_sqm']}㎡ · 挂牌{r['price_wan']}万元", '',
                  f"**{status}**。[贝壳挂牌]({r['url']}) · [小区/地图/历史成交]({r.get('community_url')})。",
                  f"{text(r.get('layout'))}；{floor_text(r)}；电梯：{elevator_text(r)}。本轮挂牌访问：{text(r.get('live_check', {}).get('status'))}，{text(r.get('live_check', {}).get('read_at'))}。",
                  f"三环：{labels.get(r.get('geography', {}).get('status'), '未知')}；参考点距三环道路约{r.get('geography', {}).get('distance_to_ring_m_approx', '未知')}米，**不是卧室声源距离**。", '',
                  '**A. 已取得事实与有利线索**（地图C级、平台描述D级；无A级实测/B级构造证明）']
        lines.extend('- ' + fact for fact in f['facts'])
        for item in r.get('geographic_environment', []):
            lines.append(f"- {item['fact']} [公开地图]({item['source_url']})；[留存图片]({item['image']})。")
        lines += ['', '**B. 潜在声学风险，尚未证明实际干扰**']
        lines.extend('- ' + risk for risk in f['risks'])
        lines += ['', '**历史成交，不能直接当买价**']
        deals = [d for d in history_rows(r) if d['area_match']][:2]
        for d in deals:
            link = d.get('url') or d['source_url']
            lines.append(f"- [{d['deal_date']}成交]({link})：{d['area_sqm']}㎡，{text(d.get('layout'))}，{d['total_price_wan']}万，{text(d.get('floor'))}；{d['comparability']}。采集{r.get('community_read_at')}。")
        if not deals:
            lines.append('- 现有公开样本无相近面积记录，不给合理购买价。')
        else:
            lines.append('- 挂牌与以上样本的差价原因尚未解释；精确楼层、电梯、装修、时间不能匹配，不做溢价率或未来价格预测。')
        lines += ['', '**C. 必须取得的现场资料**']
        lines.extend('- ' + check for check in f['onsite'])
        if r.get('visit_blockers'):
            lines.append('- 当前阻碍：' + '；'.join(r['visit_blockers']) + '。')
        ident = r['url'].split('/')[-1].split('.')[0]
        lines.append(f"- [全部六维证据、结构材料缺口、图片及历史样本](property_discovery/acoustic_investigations.md#{ident})。")
        if r.get('images'):
            lines.append(f"- [贝壳本套公开图片]({r['images'][0]})（可能含VR效果，不能证明隔音）。")
    lines += ['', '## 其他已有房源：待调查或单列环外', '',
              '不因低价补进名单。环外不再沿用V3南区放宽；边界附近也不是已确认环外。', '',
              '| 小区 / 真实挂牌 | 面积 / 万元 | 地理初核 | 未进看房名单的原因 |', '| --- | --- | --- | --- |']
    for r in run['properties']:
        if r in focuses:
            continue
        reason = r.get('qualification_reason') if r.get('qualification') == 'excluded' else '；'.join(r.get('visit_blockers', []))
        lines.append(f"| [{text(r['community'])}]({r['url']}) | {r['area_sqm']}㎡ / {r['price_wan']} | {labels.get(r.get('geography', {}).get('status'), '未知')} | {text(reason)} |")
    lines += ['', '## 来源、缺口与下一步', '',
              '- [三环道路来源、坐标系、闭合方法和逐小区台账](property_discovery/third_ring_review.md)。使用道路空间闭合，不使用行政区；750米保守待核带不是法定误差上限。',
              '- 当前房源楼号、分户墙/楼板厚度、井道/设备房/管井位置均未取得对应可靠资料，已转为业主/物业取证和现场任务；不重复搜索或用房龄推算分贝。',
              '- 历史成交沿用当天已合法取得的贝壳小区页记录，本轮未冒充新采集；[原始快照](property_discovery/data/latest.json)保留各来源时间及访问失败记录。',
              '- 先对煤建四处、合群索取带楼号的定位和上下层布局，确认可正常交易；预约早晚两次，以正常生活声测试脚步、说话、冲水和门声。明显不满意就退出，不靠便宜抵消。',
              '- 民和园先补三环楼栋位置；湖滨西村先纠正西村/东村及地图定位冲突，再决定是否进入名单。',
              '- [沿用原六维工程调查与有效标准参考](property_discovery/acoustic_reference.md)；安静30分/隔音20分仍不填未知中分，不创建新评分。']
    return '\n'.join(lines) + '\n'


def render_acoustic_details(run):
    names = {'structure': '建筑结构', 'materials': '建筑材料', 'layout': '楼栋与户型布局',
             'external': '外部噪声环境', 'equipment': '设备与管道', 'field': '现场声学验证'}
    lines = ['# 房源六维声学工程调查', '', f"资料截至：{run['collected_at']}；快照：`{run['run_id']}`。",
             '', '[候选住宅首页](../candidate_properties.md) · [规范、参考构造与现场流程](acoustic_reference.md)',
             '', '下列每条证据关联具体房源或小区参考点。A/B/C/D是证据等级，不是隔音等级。地图C级不证明实际室内噪声。']
    for row in run['properties']:
        acoustic = row.get('acoustics')
        if not acoustic:
            continue
        ident = row['url'].split('/')[-1].split('.')[0]
        lines += ['', f'<a id="{ident}"></a>', '', f"## {text(row.get('community'))} · {text(row.get('area_sqm'))}㎡ / {text(row.get('price_wan'))}万元",
                  '', f"[贝壳房源]({row['url']})；状态：{text(row.get('qualification'))}。",
                  '', '### 已有证据', '', '| 维度 | 等级 | 实际取得的资料及范围 | 获取时间 | 来源 |',
                  '| --- | --- | --- | --- | --- |']
        for item in acoustic['evidence']:
            lines.append('| ' + ' | '.join([names[item['dimension']], item['grade'], text(item['fact']),
                                           text(item['retrieved_at']), f"[原页]({item['source_url']})"]) + ' |')
        lines += ['', '### 六维缺口与下一步', '', '| 维度 | 尚未核实 | 获取/验证方法 |', '| --- | --- | --- |']
        methods = {'structure': '业主/物业/城建档案核对本楼栋竣工和改造图纸；对应户号与节点',
                   'materials': '索取具体层序、厚度及完整构件检测；现场核查安装、缝隙和声桥',
                   'layout': '取得带方位平面图、楼栋定位及上下层对应，经许可现场核实',
                   'external': '核对具体卧室到声源路径与时段，昼夜访问及关窗代表性测量',
                   'equipment': '物业标注设备房/管井，经许可运行各设备，测低频/排水与振动',
                   'field': '许可邻户配合；采用有效版本现场标准、校准仪器和完整报告，手机只作观察'}
        for dimension, gaps in acoustic['gaps'].items():
            lines.append(f"| {names[dimension]} | {text('、'.join(gaps))} | {methods[dimension]} |")
        lines += ['', '### 本套结论', '', '- 已确认的有利工程条件：没有A级或B级证明；不得把下列线索当成已验证性能。',
                  '- 值得核实的线索：' + ('；'.join(acoustic['favorable_leads']) or '仅有周边、布局和平台字段，尚缺具体有利条件'),
                  '- 风险/需要排除的路径：' + ('；'.join(acoustic['risk_questions']) or '未识别不等于不存在，需补声源和房间定位'),
                  '- 隔音实际验证：未完成。结构材料可靠资料：未取得；普通窗/结构标签不能证明指标。',
                  f"- 原评分输出：`{text(row.get('score_assessment'))}`。数值分为空，不以0—100区间推荐购买。"]
        if run.get('schema_version', 1) >= 4:
            lines += ['', '### 地理、楼层及现场调查结果', '',
                      f"- 地理：{text(row.get('geography'))}。三环内字段仅参考点初核，不是本套测绘。",
                      f"- 楼层：{floor_text(row)}；电梯：{elevator_text(row)}；证据状态：{text(row.get('evidence_level'))}。",
                      '- 当前阻碍：' + ('；'.join(row.get('visit_blockers', [])) or '可安排取证型看房；实际隔音、产权与安全仍未核验'),
                      '- 分间朝向：' + ('；'.join(' / '.join(room) for room in row.get('rooms', []) if room and '卧室' in room[0]) or '未知'),
                      '- 楼栋、每层户数、井道/设备房、楼板/墙体构造：尚未取得对应资料，须现场与档案核实。', '',
                      '### 公开成交样本（排序先匹配面积和室厅数）', '',
                      f"记录原采集：{text(row.get('community_read_at'))}；当前挂牌{row.get('price_wan')}万不是成交价。"]
            if row.get('images'):
                lines.append(f"- [本套公开图片]({row['images'][0]})（不能从普通图片推算墙板厚度或分贝）。")
            for d in history_rows(row):
                lines.append(f"- [{d['deal_date']}]({d.get('url') or d['source_url']})：{d['area_sqm']}㎡ / {d['total_price_wan']}万 / {text(d.get('layout'))} / {text(d.get('floor'))}；{d['comparability']}。")
            for item in row.get('geographic_environment', []):
                if item.get('image'):
                    lines.append(f"\n![公开地图复核：仅小区参考点]({item['image'].replace('property_discovery/', '', 1)})\n")
            for item in row.get('onsite_checks', []):
                lines.append('- 现场：' + item)
    return '\n'.join(lines) + '\n'
