import json
from pathlib import Path
import unittest

from property_discovery.acoustics import assess
from property_discovery.geography import bd_to_wgs, classify, contains, road_ring
from property_discovery.investigate import floor_and_elevator, history_rows
from property_discovery.report import render_v4


def house(**kwargs):
    return dict({'url': 'https://xz.ke.com/ershoufang/999.html', 'community': 'test_only',
                 'area_sqm': 50, 'price_wan': 25, 'layout': '2室1厅1卫'}, **kwargs)


class V4Tests(unittest.TestCase):
    def test_low_exact_floor_unknown_elevator_passes(self):
        for n in (1, 2, 3):
            row = floor_and_elevator(house(title=f'此房{n}楼', public_base={'所在楼层': '中楼层 (共7层)'}))
            self.assertEqual(row['floor_status'], 'eligible_next_round')
            self.assertIsNone(row['elevator'])
            self.assertEqual(row['evidence_level'], 'public_platform_claims_not_on_site')

    def test_unknown_lift_fourth_floor_and_conflicts_hold(self):
        self.assertEqual(floor_and_elevator(house(title='4楼'))['floor_status'], 'pending_floor_or_elevator')
        for row in (house(title='2楼', features={'介绍': '3楼'}),
                    house(title='2楼有电梯', public_base={'配备电梯': '无'})):
            self.assertEqual(floor_and_elevator(row)['floor_status'], 'pending_conflict')

    def test_floor_band_never_mapped_to_three(self):
        self.assertIsNone(floor_and_elevator(house(public_base={'所在楼层': '中楼层 (共7层)'}))['floor_number'])

    def test_boundary_and_unknown_crs_are_not_inside(self):
        ring = {'crs': 'EPSG:4326', 'coordinates': [(117, 34), (117.1, 34), (117.1, 34.1), (117, 34.1), (117, 34)]}
        self.assertTrue(contains((117.05, 34.05), ring['coordinates']))
        def point(x, y, crs='EPSG:4326'):
            return house(coordinates={'longitude': x, 'latitude': y, 'crs': crs})
        self.assertEqual(classify(point(117.05, 34.05), ring)['status'], 'inside_reference')
        self.assertEqual(classify(point(116.95, 34.05), ring)['status'], 'outside_reference')
        for x in (117, 117.00001, 116.99999):
            self.assertIsNone(classify(point(x, 34.05), ring)['inside_third_ring'])
        self.assertEqual(classify(point(117.05, 34.05, 'GCJ-02'), ring)['status'], 'unknown')
        self.assertEqual(classify(house(region='泉山区'), ring)['status'], 'unknown')
        self.assertEqual(classify(point(float('nan'), 34.05), ring)['status'], 'unknown')

    def test_bd_coordinates_are_converted_not_mixed(self):
        lon, lat = bd_to_wgs(117.172787, 34.278436)
        self.assertTrue(117.16 < lon < 117.17)
        self.assertTrue(34.27 < lat < 34.275)

    def test_actual_trace_is_closed_and_four_named_roads(self):
        raw = json.loads(Path('property_discovery/data/third_ring_osm.json').read_text())
        ring = road_ring(raw)
        self.assertEqual(ring['coordinates'][0], ring['coordinates'][-1])
        self.assertFalse(ring['official_polygon'])
        self.assertGreater(len(ring['way_ids']), 40)
        with self.assertRaises(ValueError):
            road_ring({'elements': [], 'osm3s': {}})

    def test_clinic_or_distant_mall_not_automatic_sound_source(self):
        row = house(environment_evidence=[{'category': 'medical', 'name': '社区卫生站', 'distance': '100米', 'source_url': 'https://xz.ke.com/xiaoqu/1/'},
                                          {'category': 'shopping', 'name': '商场', 'distance': '1500米', 'source_url': 'https://xz.ke.com/xiaoqu/1/'}])
        result = assess(row)
        self.assertEqual(result['risk_questions'], [])
        self.assertEqual(result['evidence_counts']['C'], 2)
        self.assertIsNone(result['quiet_rating'])

    def test_historic_samples_rank_similar_not_first_visible(self):
        row = house(history=[{'area_text': '80㎡', 'total_text': '50万', 'deal_date': '2026-07-01', 'layout': '3室1厅'},
                             {'area_text': '49㎡', 'total_text': '23万', 'deal_date': '2026-01-01', 'layout': '2室1厅'}])
        deal = history_rows(row)[0]
        self.assertEqual(deal['area_sqm'], 49)
        self.assertTrue(deal['layout_match'])
        self.assertIsNone(deal['exact_floor_match'])
        self.assertIsNone(deal['elevator_match'])

    def test_pending_is_not_listed_as_visit_and_front_is_short(self):
        row = house(qualification='public_fields_match', geography={'status': 'near_boundary'}, visit_ready=False,
                    visit_blockers=['边界待核'])
        report = render_v4({'schema_version': 4, 'collected_at': 'test', 'properties': [row]})
        self.assertIn('实地调查：**0套**', report)
        self.assertIn('边界待核', report)
        self.assertLess(len(report.splitlines()), 70)

    def test_published_shortlist_has_no_unknown_gate_promoted(self):
        run = json.loads(Path('property_discovery/data/latest.json').read_text())
        if run.get('schema_version', 1) < 4:
            self.skipTest('V4 snapshot not generated')
        ready = [r for r in run['properties'] if r.get('visit_ready')]
        self.assertLessEqual(len(ready), 5)
        self.assertEqual(len({r['community_url'] for r in ready}), len(ready))
        for r in ready:
            self.assertTrue(r['inside_third_ring'])
            self.assertEqual(r['floor_status'], 'eligible_next_round')
            self.assertEqual(r['live_check']['status'], 'ok')
            self.assertTrue(r['focused_investigation']['visit_evidence'])
            self.assertFalse(r['acoustics']['actual_performance_verified'])
            self.assertIsNone(r['acoustics']['quiet_rating'])
        self.assertFalse(any(r.get('visit_ready') for r in run['properties']
                             if r['geography']['status'] != 'inside_reference'))


if __name__ == '__main__':
    unittest.main()
