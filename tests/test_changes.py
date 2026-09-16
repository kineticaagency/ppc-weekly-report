from datetime import date
import unittest

from weekly_ads_monitor.changes import fetch_project_changes
from weekly_ads_monitor.models import Period


class FakeSheetsClient:
    def metadata(self, spreadsheet_id):
        return {"sheets": [{"properties": {"title": "Сентябрь 2026", "gridProperties": {"rowCount": 10}}}]}

    def values_get(self, spreadsheet_id, range_name):
        return [
            ["Дата", "Глянуть результат", "Результат", "Проект", "Система", "Название РК",
             "Правка", "Время", "Время Клиент", "Зачем это делать? В чем проблема? KPI",
             "Характер правки", "Инициатор", "Комментарий"],
            ["04.09.26 17", "", "", "reduktor40.ru", "Яндекс.Директ", "Поиск",
             "Расширила список минус-слов", "", "", "Повысить релевантность", "Кампания"],
            ["07.09.26 12", "", "", "reduktor40.ru", "Яндекс.Директ", "РСЯ",
             "Отключила неэффективные объявления", "", "", "Снизить CPA", "Кампания"],
            ["08.09.26 12", "", "", "other.ru", "Яндекс.Директ", "Поиск",
             "Изменила бюджет", "", "", "", "Кампания"],
        ]


class ChangesTests(unittest.TestCase):
    def test_filters_project_and_includes_short_lookback(self):
        result = fetch_project_changes(
            FakeSheetsClient(), "sheet", "reduktor40.ru",
            Period(date(2026, 9, 7), date(2026, 9, 13)), 3,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["timing"], "before")
        self.assertEqual(result[1]["timing"], "during")


if __name__ == "__main__":
    unittest.main()
