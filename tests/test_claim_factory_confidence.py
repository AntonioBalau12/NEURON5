import unittest
from experiments.claim_factory.confidence import (
    calculate_fact_confidence,
    calculate_compare_confidence,
    calculate_change_confidence,
    calculate_at_event_confidence,
    calculate_relation_confidence,
    IMMUTABLE_ATTRIBUTES,
)


class TestClaimFactoryConfidence(unittest.TestCase):
    def test_immutable_fact_gets_top_tier_confidence(self):
        conf = calculate_fact_confidence("screen_size", age_days=300)
        self.assertEqual(conf, 0.95)

        conf_date = calculate_fact_confidence("founded", age_days=1000)
        self.assertEqual(conf_date, 0.95)

        conf_explicit = calculate_fact_confidence("custom_attr", is_immutable=True)
        self.assertEqual(conf_explicit, 0.95)

    def test_mutable_fact_recency_decay(self):
        conf_recent = calculate_fact_confidence("active_users", age_days=0)
        self.assertAlmostEqual(conf_recent, 0.92, places=2)

        conf_old = calculate_fact_confidence("active_users", age_days=180)
        self.assertTrue(0.50 <= conf_old < conf_recent)

        # Multi-row corroboration boost
        conf_boosted = calculate_fact_confidence("active_users", age_days=0, n_support_rows=3)
        self.assertAlmostEqual(conf_boosted, conf_recent + 0.02, places=2)

    def test_compare_confidence(self):
        conf_dates = calculate_compare_confidence("date", "date", is_date_compare=True)
        self.assertEqual(conf_dates, 0.95)

        conf_imm = calculate_compare_confidence("screen_size", "inner_screen_size")
        self.assertEqual(conf_imm, 0.95)

        conf_mutable = calculate_compare_confidence("price", "price", age_left=10, age_right=10)
        self.assertTrue(0.50 <= conf_mutable <= 1.0)

    def test_change_confidence(self):
        conf_engine_safe = calculate_change_confidence(is_safe_transition=True, is_engine_verified=True)
        self.assertEqual(conf_engine_safe, 0.92)

        conf_safe = calculate_change_confidence(is_safe_transition=True, is_engine_verified=False)
        self.assertEqual(conf_safe, 0.88)

    def test_at_event_and_relation_confidence(self):
        conf_event = calculate_at_event_confidence(is_immutable_event=True)
        self.assertEqual(conf_event, 0.95)

        conf_rel = calculate_relation_confidence(target_immutable=True, is_engine_verified=True)
        self.assertEqual(conf_rel, 0.95)

        conf_rel_mutable = calculate_relation_confidence(target_immutable=False, is_engine_verified=True)
        self.assertEqual(conf_rel_mutable, 0.90)

    def test_bounds(self):
        for days in [-10, 0, 5, 30, 100, 365, 1000]:
            c = calculate_fact_confidence("active_users", age_days=days)
            self.assertTrue(0.50 <= c <= 1.00, f"Confidence {c} out of bounds for days={days}")


if __name__ == "__main__":
    unittest.main()
