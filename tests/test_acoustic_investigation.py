"""Synthetic fixtures only; no invented houses are written to market reports."""

import unittest

from property_discovery.acoustics import enrich
from property_discovery.discover import diverse_order
from property_discovery.investigate import community_key, floor_and_elevator, history_rows, investigate
from property_discovery.report import representatives


def fixture(**kwargs):
    return dict({'url': 'https://xz.ke.com/ershoufang/999999999999.html',
                 'community': 'synthetic_only', 'area_sqm': 50, 'price_wan': 25,
                 'public_base': {}, 'qualification': 'public_fields_match'}, **kwargs)


class AcousticTests(unittest.TestCase):
    def test_community_id_not_display_name(self):
        a = fixture(community_url='https://xz.ke.com/xiaoqu/123/')
        b = fixture(community='different display', community_url=a['community_url'])
        self.assertEqual(community_key(a), community_key(b))
        self.assertEqual(len(representatives([a, b])), 1)
        self.assertIsInstance(community_key(fixture(region=None)), str)

    def test_diversity_before_same_community_alternatives(self):
        rows = [fixture(community='a', search_region='east', price_wan=p) for p in (20, 22, 24)]
        rows += [fixture(community='b', search_region='west')]
        self.assertEqual([r['community'] for r in diverse_order(rows)][:2], ['a', 'b'])

    def test_segments_are_not_exact_floors(self):
        r = floor_and_elevator(fixture(public_base={'所在楼层': '低楼层 (共7层)'}))
        self.assertIsNone(r['floor_number'])
        self.assertIsNone(r['elevator'])

    def test_walkup_four_excluded_three_allowed(self):
        for n, status in ((4, 'excluded_walkup_above_3'), (3, 'eligible_next_round')):
            r = floor_and_elevator(fixture(title=f'{n}楼步梯房'))
            self.assertEqual(r['floor_status'], status)

    def test_mixed_estate_elevator_is_unknown(self):
        r = floor_and_elevator(fixture(title='5楼', features={'小区介绍': '小区里有步梯房和电梯房'}))
        self.assertIsNone(r['elevator'])

    def test_conflicting_floor_stays_unknown(self):
        r = floor_and_elevator(fixture(title='二楼', features={'核心卖点': '此房三楼有电梯'}))
        self.assertEqual(r['floor_status'], 'pending_conflict')
        self.assertIsNone(r['floor_number'])

    def test_new_structure_and_map_never_create_ratings(self):
        r = enrich(investigate(fixture(info='2025年', public_base={'建筑结构': '钢筋混凝土结构'},
                                      surroundings={'medical': [{'name': 'synthetic hospital', 'distance_text': '500米'}]})))
        self.assertIsNone(r['acoustics']['sound_rating'])
        self.assertIsNone(r['score_assessment']['score'])
        self.assertEqual(r['score_assessment']['dimension_points'], {})
        self.assertEqual(r['acoustics']['evidence_counts']['A'], 0)
        self.assertEqual(r['acoustics']['evidence_counts']['B'], 0)
        self.assertFalse(r['acoustics']['actual_performance_verified'])

    def test_not_street_claim_is_not_verified_benefit(self):
        r = enrich(investigate(fixture(features={'适宜人群': '此房不临街'})))
        self.assertTrue(r['acoustics']['favorable_leads'])
        self.assertFalse(r['window_street_relation_verified'])
        self.assertTrue(all(e['grade'] == 'D' for e in r['acoustics']['evidence']))

    def test_history_separate_from_listing_and_unmatched(self):
        row = fixture(history=[{'area_text': '80㎡', 'total_text': '35万', 'deal_date': '2025-01-01'}])
        self.assertEqual(history_rows(row)[0]['comparability'], '面积不同，不直接可比')
        self.assertEqual(row['price_wan'], 25)

    def test_dense_claim_defers_without_noise_verdict(self):
        row = enrich(investigate(fixture(public_base={'梯户比例': '两梯二十八户'})))
        self.assertTrue(row['living_conflicts'])
        self.assertIsNone(row['acoustics']['quiet_rating'])
        self.assertFalse(row['acoustics']['actual_performance_verified'])

    def test_null_ratings_keep_original_six_dimensions(self):
        row = enrich(investigate(fixture()))
        self.assertEqual(set(row['score_assessment']['unknown_dimensions']),
                         {'quiet', 'sound', 'density', 'convenience', 'price', 'liquidity'})
        self.assertEqual(row['score_assessment']['evidence_coverage_percent'], 0)


if __name__ == '__main__':
    unittest.main()
