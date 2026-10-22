import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402


class TestPresent(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_present_page(self):
        resp = self.client.get("/present")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("data-deck", html)
        self.assertIn("present.js", html)
        self.assertIn("present.css", html)
        self.assertGreaterEqual(html.count('<section class="slide'), 10)

    def test_present_static_files(self):
        for path in ("/static/js/present.js", "/static/css/present.css"):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            resp.close()


if __name__ == "__main__":
    unittest.main()
