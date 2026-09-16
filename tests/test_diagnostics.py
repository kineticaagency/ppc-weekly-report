import unittest

from weekly_ads_monitor.diagnostics import analyze, significance
from weekly_ads_monitor.models import Metrics


class DiagnosticTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(significance(0.099), "normal")
        self.assertEqual(significance(0.10), "attention")
        self.assertEqual(significance(0.20), "attention")
        self.assertEqual(significance(0.201), "diagnostic")

    def test_preliminary_quality(self):
        current = Metrics(spend=110, clicks=10, leads=5, unprocessed_leads=1)
        previous = Metrics(spend=100, clicks=10, leads=5)
        result = analyze(current, previous, 0.2)
        self.assertTrue(result["quality_preliminary"])

    def test_human_comment_keeps_technical_layers_separate(self):
        current = Metrics(spend=95, clicks=106, leads=85, target_leads=20, unprocessed_leads=55)
        previous = Metrics(spend=100, clicks=100, leads=100, target_leads=30)
        result = analyze(current, previous, 0.2)
        comment = result["human_comment"]
        self.assertNotIn("Подтверждено", comment)
        self.assertNotIn("Ограничение", comment)
        self.assertIn("Качество трафика пока рано оценивать", comment)
        self.assertIn("Доля целевых заявок", comment)
        self.assertNotIn("качество трафика ухудшилось", comment)
        self.assertLessEqual(len(comment.split(". ")), 5)

    def test_network_selection_uses_absolute_contribution(self):
        previous = {
            "account": Metrics(clicks=1100, leads=110),
            "network:search": Metrics(clicks=1000, leads=100),
            "network:context": Metrics(clicks=100, leads=10),
        }
        current = {
            "account": Metrics(clicks=1100, leads=81),
            "network:search": Metrics(clicks=1000, leads=75),
            "network:context": Metrics(clicks=100, leads=6),
        }
        result = analyze(
            current["account"], previous["account"], 0.2, current, previous,
            {"network:search": "Поиск", "network:context": "РСЯ"}, {},
        )
        self.assertIn("Наибольший вклад внёс Поиск", result["human_comment"])

    def test_relevant_operational_changes_are_cautious_hypotheses(self):
        previous = Metrics(spend=1000, clicks=100, leads=10)
        current = Metrics(spend=900, clicks=100, leads=12)
        result = analyze(current, previous, 0.2, operational_changes=[{
            "change": "Отключила неэффективные ключевые фразы и расширила список минус-слов"
        }])
        comment = result["human_comment"]
        self.assertIn("могли повлиять", comment)
        self.assertIn("требуется дополнительная статистика", comment)
        self.assertNotIn("из-за отключения", comment)


if __name__ == "__main__":
    unittest.main()
