import unittest
import io
from services.chart_service import chart_service

class TestServices(unittest.TestCase):
    def test_chart_generation(self):
        sample_data = {
            "Ăn uống": 3500000,
            "Đi lại": 600000,
            "Mua sắm": 1500000,
            "Hóa đơn": 2000000
        }
        buf = chart_service.generate_expense_pie_chart(sample_data, 8, 2026)
        self.assertIsNotNone(buf)
        self.assertIsInstance(buf, io.BytesIO)
        self.assertGreater(len(buf.getvalue()), 1000)

    def test_empty_chart(self):
        buf = chart_service.generate_expense_pie_chart({}, 8, 2026)
        self.assertIsNone(buf)

if __name__ == '__main__':
    unittest.main()
