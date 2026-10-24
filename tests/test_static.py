import unittest

import helpers as H  # noqa: F401  (must come first)
from test_server import Served


class Static(Served):
    def test_index_and_assets(self):
        code, html = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("<script", html)
        for js in ("lib.js", "app.js", "style.css"):
            code, body = self.get(f"/static/{js}", raw=True)
            self.assertEqual(code, 200, js)
            self.assertGreater(len(body), 100)
        self.assertEqual(self.get("/index.html")[0], 200)

    def test_every_script_in_shell_is_served(self):
        import re
        _, html = self.get("/")
        refs = re.findall(r'(?:src|href)="(/?static/[^"]+)"', html)
        self.assertTrue(refs)
        for r in refs:
            self.assertEqual(self.get("/" + r.lstrip("/"))[0], 200, r)

    def test_unknown_404(self):
        for path in ("/nope", "/static/nope.js", "/static/", "/static", "/api/nope"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_path_traversal_404(self):
        attacks = ["/static/../core.py", "/static/%2e%2e/core.py", "/static/..%2fcore.py", "/static/%2e%2e%2fcore.py",
                   "/static/..%5ccore.py", "/static/..\\core.py", "/static//etc/passwd", "/static/%2fetc/passwd",
                   "/static/....//core.py", "/static/./../server.py", "/static/..", "/static/../", "/static/%00.js",
                   "/static/lib.js/../../core.py", "/static/%252e%252e/core.py", "/../autoresearch/core.py",
                   "/static/..;/core.py"]
        for a in attacks:
            code, body = self.get(a, raw=True)
            self.assertEqual(code, 404, a)
            self.assertNotIn(b"class Project", body, a)

    def test_query_string_ignored(self):
        self.assertEqual(self.get("/static/lib.js?v=1")[0], 200)


if __name__ == "__main__":
    unittest.main()
