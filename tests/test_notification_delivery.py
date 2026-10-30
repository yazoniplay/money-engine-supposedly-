import unittest
from unittest.mock import patch, MagicMock

import money_engine


class NotificationDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.lead = {
            "id": "reddit_abc123",
            "title": "Need an AI automation developer",
            "url": "https://reddit.com/r/example/abc123",
            "score": 9,
            "rationale": "Explicit request for help.",
            "source": "r/example",
            "content": "This field should not be persisted for notification retries.",
        }

    @patch("money_engine.urllib.request.urlopen")
    def test_successful_http_delivery_returns_true(self, urlopen):
        response = MagicMock()
        response.status = 204
        urlopen.return_value.__enter__.return_value = response

        self.assertTrue(money_engine.send_discord_notification(
            self.lead, "https://discord.com/api/webhooks/test"
        ))

    @patch("money_engine.urllib.request.urlopen", side_effect=OSError("network unavailable"))
    def test_network_failure_returns_false(self, _urlopen):
        self.assertFalse(money_engine.send_discord_notification(
            self.lead, "https://discord.com/api/webhooks/test"
        ))

    @patch("money_engine.send_discord_notification", return_value=False)
    def test_failed_new_delivery_is_queued_without_full_post_content(self, send):
        state = {}
        money_engine.notify_or_queue_notification(
            self.lead, "https://discord.com/api/webhooks/test", state
        )

        send.assert_called_once()
        self.assertEqual(len(state["pending_notifications"]), 1)
        queued = state["pending_notifications"][0]
        self.assertEqual(queued["id"], self.lead["id"])
        self.assertNotIn("content", queued)

    @patch("money_engine.send_discord_notification", return_value=True)
    def test_successful_new_delivery_is_not_queued(self, _send):
        state = {}
        money_engine.notify_or_queue_notification(
            self.lead, "https://discord.com/api/webhooks/test", state
        )
        self.assertNotIn("pending_notifications", state)

    @patch("money_engine.send_discord_notification", return_value=False)
    def test_failed_pending_delivery_remains_queued(self, _send):
        state = {"pending_notifications": [money_engine._notification_record(self.lead)]}
        remaining = money_engine.retry_pending_notifications(
            state, "https://discord.com/api/webhooks/test"
        )
        self.assertEqual(remaining, state["pending_notifications"])

    @patch("money_engine.send_discord_notification", return_value=True)
    def test_successful_pending_delivery_is_removed(self, _send):
        state = {"pending_notifications": [money_engine._notification_record(self.lead)]}
        remaining = money_engine.retry_pending_notifications(
            state, "https://discord.com/api/webhooks/test"
        )
        self.assertEqual(remaining, [])

    @patch("money_engine.send_discord_notification")
    def test_pending_delivery_is_preserved_without_a_webhook(self, send):
        pending = [money_engine._notification_record(self.lead)]
        remaining = money_engine.retry_pending_notifications(
            {"pending_notifications": pending}, ""
        )
        send.assert_not_called()
        self.assertEqual(remaining, pending)


if __name__ == "__main__":
    unittest.main()
