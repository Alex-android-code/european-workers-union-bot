import datetime as dt
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ewu_channel_publisher.py"
spec = importlib.util.spec_from_file_location("ewu_channel_publisher", SCRIPT)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.today = dt.date(2026, 10, 16)
        self.offer = {
            "id": "test-1000", "status": "approved", "approved": True,
            "employer_verified": True, "approved_by": "EWU owner",
            "valid_until": "2026-10-31",
            "text": "🇵🇱 Работа в Польше. Подробности в EWU."
        }

    def test_approved_is_selected_and_bot_link_added(self):
        posts = publisher.eligible_posts([self.offer], {}, self.today)
        self.assertEqual(len(posts), 1)
        self.assertIn(publisher.BOT_LINK, posts[0][1])

    def test_unapproved_is_not_selected(self):
        for field, value in [
            ("approved", False), ("status", "draft"),
            ("employer_verified", False), ("approved_by", "")
        ]:
            offer = dict(self.offer)
            offer[field] = value
            self.assertEqual(publisher.eligible_posts([offer], {}, self.today), [])

    def test_expired_is_skipped(self):
        offer = dict(self.offer, valid_until="2026-10-15")
        self.assertEqual(publisher.eligible_posts([offer], {}, self.today), [])

    def test_publish_date_is_honored(self):
        offer = dict(self.offer, publish_from="2026-10-17")
        self.assertEqual(publisher.eligible_posts([offer], {}, self.today), [])

    def test_attempted_is_not_retried(self):
        state = {"test-1000": {"status": "attempted"}}
        self.assertEqual(publisher.eligible_posts([self.offer], state, self.today), [])

    def test_published_is_not_repeated(self):
        state = {"test-1000": {"status": "published"}}
        self.assertEqual(publisher.eligible_posts([self.offer], state, self.today), [])

    def test_duplicate_ids_raise(self):
        with self.assertRaises(ValueError):
            publisher.eligible_posts([self.offer, self.offer], {}, self.today)

    def test_no_personal_information_loaded_by_default(self):
        self.assertEqual(publisher.read_json(publisher.QUEUE, []), [])


if __name__ == "__main__":
    unittest.main()
