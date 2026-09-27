import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest

from property_discovery.browser import validate_url
from property_discovery.discover import apply_detail, collect, normalize, preliminary_filter, qualifies, render_report


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        # Entirely synthetic fixture: never a claimed market listing.
        self.row = normalize({'url': 'https://xz.ke.com/ershoufang/999999999999.html',
                              'community': 'synthetic_test_only', 'title': 'synthetic_test_only',
                              'info': '低楼层 (共6层) | 2000年 | 2室1厅 | 50平米 | 南',
                              'price_text': '15万', 'unit_text': '3,000元/平'})
        self.detail = {'status': 'ok', 'base': {'建筑面积': '50㎡', '所在楼层': '低楼层 (共6层)',
                                              '房屋户型': '2室1厅', '建筑结构': '混合结构'},
                       'transaction': {'房屋用途': '普通住宅', '交易权属': '商品房',
                                       '产权所属': '非共有', '房本备件': '已上传房本照片'}}

    def test_price_below_previous_minimum_allowed(self):
        self.assertIsNone(preliminary_filter(self.row))

    def test_zero_price_is_not_free_home(self):
        self.row['price_wan'] = 0
        self.assertEqual(preliminary_filter(self.row), 'zero_price_requires_verification')

    def test_exact_bounds_and_missing(self):
        for area in (40, 60):
            for price in (0.1, 50):
                self.assertIsNone(preliminary_filter(dict(self.row, area_sqm=area, price_wan=price)))
        self.assertEqual(preliminary_filter(dict(self.row, area_sqm=60.01)), 'outside_area_40_60')
        self.assertEqual(preliminary_filter(dict(self.row, price_wan=None)), 'missing_area_or_price')

    def test_public_fields_not_registry_proof(self):
        result = apply_detail(self.row, self.detail)
        self.assertEqual(result['qualification'], 'public_fields_match')
        self.assertFalse(result['title_registry_verified'])
        self.assertIsNone(result['inside_third_ring'])
        self.assertIsNone(result['elevator'])
        self.assertIsNone(result['floor_number'])

    def test_candidate_must_be_ke(self):
        row = apply_detail(self.row, self.detail)
        filters = {'min_price_wan': 0, 'max_price_wan': 50}
        self.assertTrue(qualifies(row, filters))
        row['url'] = 'https://xz.esf.fang.com/chushou/16_999.htm'
        self.assertFalse(qualifies(row, filters))

    def test_commercial_and_incomplete_title(self):
        detail = copy.deepcopy(self.detail)
        detail['transaction']['房屋用途'] = '商业办公'
        self.assertEqual(apply_detail(self.row, detail)['qualification'], 'excluded')
        del detail['transaction']['房屋用途']
        self.assertEqual(apply_detail(self.row, detail)['qualification'], 'pending_title')

    def test_missing_certificate(self):
        del self.detail['transaction']['房本备件']
        self.assertEqual(apply_detail(self.row, self.detail)['qualification'], 'pending_title')

    def test_detail_conflict_is_not_silently_overwritten(self):
        self.detail['base']['建筑面积'] = '51㎡'
        result = apply_detail(self.row, self.detail)
        self.assertEqual(result['qualification'], 'pending_conflict')
        self.assertEqual(result['conflicts'], ['area_sqm'])

    def test_title_quietness_and_floor_not_inferred(self):
        self.row['title'] = '安静 三楼'
        result = apply_detail(self.row, self.detail)
        self.assertIsNone(result['floor_number'])
        self.assertNotIn('quiet_score', result)

    def test_title_commercial_excluded(self):
        self.row['title'] = '商办公寓'
        self.assertEqual(preliminary_filter(self.row), 'possible_nonresidential_title')

    def test_name_does_not_establish_nonresidential_use(self):
        self.row['title'] = '测试公寓住宅 商铺旁 带车位'
        self.assertIsNone(preliminary_filter(self.row))

    def test_url_allowlist_and_no_credentials(self):
        validate_url(self.row['url'])
        for url in ('http://xz.ke.com/ershoufang/', 'https://example.com/',
                    'https://xz.ke.com/ershoufang/?token=secret',
                    'https://user:password@xz.ke.com/ershoufang/',
                    'https://xz.ke.com/private/messages'):
            with self.assertRaises(ValueError):
                validate_url(url)

    def args(self, output):
        return argparse.Namespace(min_price=0, max_price=50, target=10, max_details=30,
                                  delay=2, url=['https://xz.ke.com/ershoufang/',
                                                'https://xz.ke.com/ershoufang/p2/'],
                                  output=output / 'data', report=output / 'candidate.md')

    def test_gate_stops_same_platform_and_writes_reason(self):
        calls = []

        def reader(url, script):
            calls.append(url)
            return {'status': 'blocked', 'reason': 'verification_or_login_wall',
                    'url': 'https://hip.ke.com/captcha'}

        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            result = collect(args, reader=reader, sleeper=lambda _: None)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['access_log'][1]['status'], 'skipped')
            self.assertEqual(result['properties'], [])
            self.assertIn('缺10套', args.report.read_text())
            self.assertTrue((args.output / 'latest.json').exists())

    def test_deduplicate_and_collect_real_fields_only(self):
        raw = dict(self.row, info='低楼层 (共6层) | 2室1厅 | 50平米')

        def reader(url, script):
            if url.endswith('.html'):
                return self.detail
            return {'status': 'ok', 'rows': [raw]}

        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            result = collect(args, reader=reader, sleeper=lambda _: None)
            self.assertEqual(result['stats']['cards'], 2)
            self.assertEqual(result['stats']['unique_listings'], 1)
            self.assertEqual(len(result['properties']), 1)
            report = render_report(result)
            self.assertIn('未知', report)
            self.assertIn('三环内及登记产权均核验的房源：**0套**', report)
            snapshots = list((args.output / 'runs').glob('*.json'))
            self.assertEqual(len(snapshots), 1)
            self.assertEqual(json.loads(snapshots[0].read_text())['target'], 10)


if __name__ == '__main__':
    unittest.main()
