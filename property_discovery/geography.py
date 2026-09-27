"""Conservative reference-point screening against a connected public road trace."""

import math
from collections import defaultdict


def road_ring(raw):
    ways = [w for w in raw['elements']
            if w.get('tags', {}).get('highway:CN:urban') == 'expressway'
            and w['tags'].get('name') in ('东三环快速路', '西三环快速路', '南三环快速路', '北三环快速路')]
    outgoing = defaultdict(list)
    for way in ways:
        outgoing[way['nodes'][0]].append(way)
    cycles = []
    for start in sorted(ways, key=lambda w: w['id']):
        path, seen, current = [], set(), start
        while current['id'] not in seen:
            path.append(current)
            seen.add(current['id'])
            next_ways = outgoing[current['nodes'][-1]]
            if len(next_ways) != 1:
                break
            current = next_ways[0]
        if (current['id'] == start['id'] and path[-1]['nodes'][-1] == start['nodes'][0]
                and {w['tags']['name'] for w in path} == {'东三环快速路', '西三环快速路', '南三环快速路', '北三环快速路'}):
            cycles.append(path)
    if not cycles:
        raise ValueError('No exact-node closed four-road ring; do not invent connecting segments')
    path = max(cycles, key=lambda p: len(p))
    coordinates = [(p['lon'], p['lat']) for w in path for p in w['geometry'][:-1]]
    coordinates.append(coordinates[0])
    return {'crs': 'EPSG:4326', 'coordinates': coordinates, 'way_ids': [w['id'] for w in path],
            'osm_base': raw['osm3s']['timestamp_osm_base'], 'official_polygon': False}


def bd_to_wgs(lon, lat):
    # Approximate BD-09 -> GCJ-02 -> WGS84; not a surveying transformation.
    x, y = lon - 0.0065, lat - 0.006
    z = math.hypot(x, y) - 0.00002 * math.sin(y * math.pi * 3000 / 180)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * math.pi * 3000 / 180)
    lon, lat = z * math.cos(theta), z * math.sin(theta)
    x, y = lon - 105, lat - 35
    dlat = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
    dlat += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dlat += (20*math.sin(y*math.pi)+40*math.sin(y/3*math.pi))*2/3
    dlat += (160*math.sin(y/12*math.pi)+320*math.sin(y*math.pi/30))*2/3
    dlon = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
    dlon += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dlon += (20*math.sin(x*math.pi)+40*math.sin(x/3*math.pi))*2/3
    dlon += (150*math.sin(x/12*math.pi)+300*math.sin(x/30*math.pi))*2/3
    rad = math.radians(lat)
    magic = 1 - .00669342162296594323 * math.sin(rad)**2
    dlat = dlat*180 / ((6378245*(1-.00669342162296594323)/(magic*math.sqrt(magic)))*math.pi)
    dlon = dlon*180 / (6378245/math.sqrt(magic)*math.cos(rad)*math.pi)
    return lon - dlon, lat - dlat


def contains(point, polygon):
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:]):
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside


def line_distance(point, line):
    lon, lat = point
    scale_x, scale_y = 111320*math.cos(math.radians(lat)), 111320
    best = float('inf')
    for a, b in zip(line, line[1:]):
        ax, ay = (a[0]-lon)*scale_x, (a[1]-lat)*scale_y
        bx, by = (b[0]-lon)*scale_x, (b[1]-lat)*scale_y
        dx, dy = bx-ax, by-ay
        t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        best = min(best, math.hypot(ax+t*dx, ay+t*dy))
    return best


def classify(row, ring, buffer_m=750):
    coords = row.get('coordinates') or {}
    crs = coords.get('crs')
    if crs not in ('BD-09', 'EPSG:4326') or any(coords.get(k) is None for k in ('longitude', 'latitude')):
        return {'status': 'unknown', 'reason': '缺少准确坐标或坐标系不支持', 'inside_third_ring': None}
    point = coords['longitude'], coords['latitude']
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)
            or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90
            or ring.get('crs') != 'EPSG:4326'):
        return {'status': 'unknown', 'reason': '坐标无效或道路坐标系不匹配', 'inside_third_ring': None}
    if crs == 'BD-09':
        point = bd_to_wgs(*point)
    distance = line_distance(point, ring['coordinates'])
    status = 'near_boundary' if distance <= buffer_m else 'inside_reference' if contains(point, ring['coordinates']) else 'outside_reference'
    return {'status': status, 'inside_third_ring': True if status == 'inside_reference' else False if status == 'outside_reference' else None,
            'wgs84_approx': point, 'distance_to_ring_m_approx': round(distance), 'buffer_m': buffer_m,
            'scope': '小区参考点初核；不是房源楼栋测绘确认',
            'reason': '750米保守待核带包含道路宽度、双向车道差异、坐标转换误差和未取得的小区范围；不是实际误差上限或法律边界'}
