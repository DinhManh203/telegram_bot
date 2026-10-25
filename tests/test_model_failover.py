import unittest
from unittest.mock import MagicMock, patch
import time
from services.ai_service import (
    AIService,
    parse_reset_time_info,
    is_quota_limit_error,
    is_discontinued_error
)

class TestGeminiModelFailover(unittest.TestCase):
    def test_parse_reset_time_info(self):
        # 1. retryDelay: '57354s' (hơn 15 giờ)
        d1, c1 = parse_reset_time_info("Rate limit 'retryDelay': '57354s'")
        self.assertEqual(d1, "15h55m")
        self.assertEqual(c1, 57354.0)

        # 2. retryDelay: '45s'
        d2, c2 = parse_reset_time_info("retryDelay: 45s")
        self.assertEqual(d2, "45s")
        self.assertEqual(c2, 45.0)

        # 3. retry in 15h55m54.801153382s
        d3, c3 = parse_reset_time_info("Please retry in 15h55m54.801153382s. Details...")
        self.assertEqual(d3, "15h55m55s")
        self.assertEqual(c3, 57355.0)

        # 4. retry after 24.5s
        d4, c4 = parse_reset_time_info("Please retry after 24.5s. Details...")
        self.assertEqual(d4, "24s")
        self.assertEqual(c4, 24.0)

        # 5. try again in 2 minutes
        d5, c5 = parse_reset_time_info("Rate limit reached. Try again in 2 minutes.")
        self.assertIn("2 phút", d5)
        self.assertEqual(c5, 120.0)

    def test_error_detection(self):
        self.assertTrue(is_quota_limit_error(Exception("429 RESOURCE_EXHAUSTED")))
        self.assertTrue(is_quota_limit_error(Exception("Quota exceeded for quota metric...")))
        self.assertTrue(is_quota_limit_error(Exception("503 UNAVAILABLE: high demand")))
        self.assertFalse(is_quota_limit_error(Exception("Invalid syntax in prompt")))

        self.assertTrue(is_discontinued_error(Exception("404 NOT_FOUND. Model is no longer available.")))
        self.assertFalse(is_discontinued_error(Exception("429 RESOURCE_EXHAUSTED")))

    def test_model_rotation_on_rate_limit(self):
        service = AIService()
        service.client = MagicMock()
        service.models = ["gemini-mock-1", "gemini-mock-2", "gemini-mock-3"]
        service.current_model = "gemini-mock-1"
        service.model_cooldowns = {}
        service.discontinued_models = set()

        # Giả lập model-1 bị 429 RESOURCE_EXHAUSTED, model-2 thành công
        def fake_generate_content(model, contents, config):
            if model == "gemini-mock-1":
                raise Exception("429 RESOURCE_EXHAUSTED. Please retry in 45s.")
            resp = MagicMock()
            resp.text = '{"intent": "ADD_TRANSACTION", "transactions": [{"amount": 50000, "type": "Chi tiêu", "category": "Ăn uống", "note": "Phở bò"}], "debt_items": []}'
            return resp

        service.client.models.generate_content.side_effect = fake_generate_content

        switch_notifications = []
        def on_switch(msg):
            switch_notifications.append(msg)

        res = service.analyze_text("Ăn phở bò 50k", on_model_switch=on_switch)

        # Kiểm tra kết quả
        self.assertEqual(res.get("intent"), "ADD_TRANSACTION")
        self.assertEqual(res.get("active_model"), "gemini-mock-2")
        self.assertEqual(len(switch_notifications), 1)
        self.assertIn("gemini-mock-1", switch_notifications[0])
        self.assertIn("đã tới giới hạn", switch_notifications[0])
        self.assertIn("45s", switch_notifications[0])
        self.assertIn("gemini-mock-2", switch_notifications[0])

        # Kiểm tra model-1 đã được đưa vào cooldown
        self.assertGreater(service.model_cooldowns.get("gemini-mock-1", 0), time.time())

if __name__ == '__main__':
    unittest.main()
