import copy
import unittest

from tools.score_property import GATES, WEIGHTS, score


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.data = {"community": "synthetic", "area_sqm": 50, "price_wan": 40,
                     "floor": 3, "total_floors": 6, "elevator": False,
                     "gates": dict.fromkeys(GATES, True),
                     "ratings": dict.fromkeys(WEIGHTS, 5),
                     "evidence": dict.fromkeys(WEIGHTS, "synthetic test evidence"),
                     "price_evidence_confidence": "high"}

    def test_complete_a(self):
        result = score(self.data)
        self.assertEqual((result["score"], result["grade"]), (100, "A"))

    def test_missing_is_not_zero_or_a(self):
        self.data["ratings"]["sound"] = None
        result = score(self.data)
        self.assertIsNone(result["score"])
        self.assertEqual(result["score_range"], [80, 100])
        self.assertEqual(result["grade"], "C")

    def test_unknown_gate_caps_grade(self):
        self.data["gates"]["inside_third_ring"] = None
        self.assertEqual(score(self.data)["grade"], "C")

    def test_each_hard_gate_vetoes(self):
        for key in GATES:
            data = copy.deepcopy(self.data)
            data["gates"][key] = False
            self.assertEqual(score(data)["grade"], "D")

    def test_walkup_four_vetoes(self):
        self.data["floor"] = 4
        self.assertEqual(score(self.data)["grade"], "D")

    def test_budget_and_area(self):
        for field, value in (("price_wan", 51), ("area_sqm", 61)):
            data = copy.deepcopy(self.data)
            data[field] = value
            self.assertEqual(score(data)["grade"], "D")

    def test_quiet_cannot_be_compensated(self):
        self.data["ratings"]["quiet"] = 2
        self.assertEqual(score(self.data)["grade"], "C")

    def test_evidence_required(self):
        self.data["evidence"] = {}
        result = score(self.data)
        self.assertEqual(result["grade"], "C")
        self.assertEqual(result["score_range"], [0, 100])

    def test_medium_price_cannot_a(self):
        self.data["price_evidence_confidence"] = "medium"
        self.assertEqual(score(self.data)["grade"], "B")

    def test_unit_mismatch_requires_check(self):
        self.data["unit_price_yuan"] = 9000
        self.assertEqual(score(self.data)["grade"], "C")

    def test_invalid_numbers_and_booleans(self):
        for value in (True, -1, float("nan"), 6):
            data = copy.deepcopy(self.data)
            data["ratings"]["quiet"] = value
            with self.assertRaises(ValueError):
                score(data)
        self.data["gates"]["inside_third_ring"] = 1
        with self.assertRaises(ValueError):
            score(self.data)

    def test_complete_low_score_d(self):
        self.data["ratings"] = dict.fromkeys(WEIGHTS, 2)
        self.assertEqual(score(self.data)["grade"], "D")


if __name__ == "__main__":
    unittest.main()
