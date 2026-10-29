"""Actual learning flows on an isolated synthetic ledger (no provider calls).
Run: ARX_BROWSER_EXECUTABLE=/path/to/chrome uv run --with playwright python -m unittest tests.browser.test_learning_flows
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright, "Install Playwright to run browser regressions")
class LearningFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_learn import ledger, run
        cls.project = p = ledger()
        p.add_model('base', title='Shared name', status='champion')
        run(p, 'base', [1] * 28 + [0] * 12)
        run(p, 'base', [1] * 12 + [0] * 8, 'ds/target')
        p.open_goal('g', 'Synthetic goal', 'full', .9)
        p.open_hill('h', 'Arithmetic hill', 'target', symptom='Arithmetic error')
        p.add_model('rejected', title='Shared name', parent='base', hill='h')
        run(p, 'rejected', [1] * 8 + [0] * 12, 'ds/target')
        p.set_model_status('rejected', 'rejected', 'Target regressed')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.url = f'http://127.0.0.1:{port}/'
        cls.server = subprocess.Popen([sys.executable, '-c', 'from autoresearch.server import serve; import sys; serve(int(sys.argv[1]), sys.argv[2])', str(port), str(p.root)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, 'ARX_HOME': tempfile.mkdtemp()})
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.url + 'api/state', timeout=.2).close()
                break
            except OSError:
                time.sleep(.05)
        cls.pw = sync_playwright().start()
        opts = {'headless': True}
        if os.environ.get('ARX_BROWSER_EXECUTABLE'):
            opts['executable_path'] = os.environ['ARX_BROWSER_EXECUTABLE']
        cls.browser = cls.pw.chromium.launch(**opts)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.terminate()
        cls.server.wait(timeout=10)

    def setUp(self):
        self.ctx = self.browser.new_context(viewport={'width': int(os.environ.get('ARX_BROWSER_WIDTH', '375')), 'height': 850})
        self.person = 'p-' + os.urandom(4).hex()
        self.ctx.add_init_script('localStorage.setItem("arx-me", ' + json.dumps(json.dumps({'id': self.person, 'name': 'Flow test'})) + ')')
        self.ctx.add_init_script("localStorage.setItem('arx-theme', " + json.dumps(os.environ.get('ARX_BROWSER_THEME', 'light')) + ")")
        self.page = self.ctx.new_page()
        self.errors = []
        self.page.on('pageerror', lambda e: self.errors.append(str(e)))
        self.page.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' else None)

    def tearDown(self):
        if os.environ.get('ARX_BROWSER_SCREENSHOTS'):
            out = Path(os.environ['ARX_BROWSER_SCREENSHOTS'])
            out.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(out / (self._testMethodName + '.png')), full_page=True)
        self.ctx.close()
        self.assertEqual(self.errors, [], 'Caught render errors count as failures too')

    def brief(self, card):
        # The primer is tested separately; mark concepts learned for focused Brief regressions.
        for lesson in self.page.request.get(self.url + 'api/course?viewer=' + self.person).json()['lessons']:
            self.page.request.post(self.url + 'api/course', data={'viewer': self.person, 'item': lesson['id'], 'hit': True})
        self.page.goto(self.url + '#learn')
        self.page.wait_for_function('typeof L!=="undefined" && L.b && L.b.cards.length')
        self.page.evaluate('(id)=>go(L.b.cards.findIndex(c=>c.id.startsWith(id)))', card)
        self.page.wait_for_timeout(100)

    def test_numeric_goal_and_hill_reveal(self):
        self.brief('goal|g')
        # Each offered answer path is exercised through its real controls.
        for prefix in ('goal|g', 'hill|h'):
            self.page.evaluate('(id)=>go(L.b.cards.findIndex(c=>c.id.startsWith(id)))', prefix)
            self.page.wait_for_timeout(100)
            for _ in range(4):
                if self.page.locator('[data-l=commit]').count():
                    self.page.locator('[data-l=commit]').click()
                    break
                if self.page.locator('#tsk').count():
                    self.page.locator('#tsk').focus()
                    self.page.keyboard.press('ArrowRight')
                    self.page.locator('[data-t=go]').click()
                    break
                self.page.locator('[data-t=skip]').click()
                self.page.wait_for_timeout(100)
            self.page.wait_for_selector('.reveal')
            self.assertNotIn('failed to draw', self.page.locator('#main').inner_text())
            if prefix == 'goal|g':
                self.assertIn('28', self.page.locator('.reveal').inner_text())
                self.assertIn('40', self.page.locator('.reveal').inner_text())
            self.assertTrue(self.page.locator('[data-l=next]').is_visible())
            self.page.locator('[data-l=next]').click()

    def test_self_assessment_and_consolidation(self):
        self.brief('rej|rejected')
        for _ in range(4):
            if self.page.locator('#tex').count():
                break
            self.page.locator('[data-t=skip]').click()
            self.page.wait_for_timeout(150)
        self.page.locator('#tex').fill('It improved and definitely clears zero.')
        self.page.locator('[data-t=go]').click()
        self.page.wait_for_selector('[data-t=self]')
        self.assertIn('degradation', self.page.locator('.t-after').inner_text())
        for box in self.page.locator('[data-t-self]').all():
            box.check()
        self.page.locator('[data-t=self]').click()
        self.page.wait_for_function('document.querySelector(".reveal").textContent.includes("Self-checked:")')
        self.assertNotIn('✓ Right', self.page.locator('.reveal').inner_text())
        cal = self.page.request.get(self.url + 'api/brief?since=0&viewer=' + self.person).json()['calibration']
        self.assertEqual(cal['all_n'], cal['n'])
        # Reach drag-n through the real follow-up controls and submit a wrong projection.
        for _ in range(3):
            if self.page.locator('#tpn').count():
                break
            self.page.locator('[data-t=step-skip]').click()
            self.page.wait_for_timeout(100)
        self.page.locator('#tpn').fill('0')
        self.page.locator('[data-t=step]').click()
        self.page.wait_for_function('document.querySelector(".t-after").textContent.includes("not a new measurement")')
        self.assertIn('not a new measurement', self.page.locator('.t-after').inner_text())
        self.assertIn('projection', self.page.locator('.t-after').inner_text())

    def test_lesson_reasoning_and_wrong_review(self):
        self.page.goto(self.url + '#course/goal')
        self.page.wait_for_selector('[data-cq]')
        self.assertEqual(self.page.locator('[data-study-check]').count(), 0)
        self.assertEqual(self.page.locator('.crs-fig').count(), 1)
        correct = self.page.evaluate("COURSE.lesson('goal').checks[0].a")
        for opt in self.page.locator('[data-cq]').all():
            if opt.locator('.opt-label').inner_text().strip() != str(correct):
                opt.click()
                break
        self.page.wait_for_selector('.crs-res')
        self.assertIn('Not quite', self.page.locator('.crs-res').inner_text())
        self.page.goto(self.url + '#course/review')
        self.page.wait_for_selector('[data-cq]')
        self.assertEqual(self.page.locator('.crs-fig').count(), 0)
        self.page.locator('[data-cq]').first.click()
        self.page.wait_for_selector('[data-next]')
        self.page.locator('[data-next]').click()
        self.assertNotIn('failed to draw', self.page.locator('#main').inner_text())

    def test_numeric_answer_is_separate_from_keyboard_shortcut(self):
        # Render the numeric answer "3" through the real component. A shortcut
        # badge must not turn it into a visually or audibly different answer.
        course = self.page.request.get(self.url + 'api/course').json()
        lesson = next(x for x in course['lessons'] if x['id'] == 'goal')
        lesson['checks'] = [{'q': 'Synthetic numeric choice', 'o': ['3', '2', '1'],
                             'a': '3', 'why': 'Three is the synthetic answer.'}]
        self.page.route('**/api/course?*', lambda route: route.fulfill(json=course))
        for width in (1200, 375):
            self.page.set_viewport_size({'width': width, 'height': 850})
            self.page.goto(self.url + '#course/goal')
            answer = self.page.get_by_role('button', name='3', exact=True)
            answer.wait_for()
            label = answer.locator('.opt-label').bounding_box()
            badge = answer.locator('kbd')
            self.assertEqual(badge.get_attribute('aria-hidden'), 'true')
            if width > 560:
                box = badge.bounding_box()
                self.assertGreaterEqual(label['x'] - box['x'] - box['width'], 8)
            else:
                self.assertFalse(badge.is_visible())
            self.assertLessEqual(label['x'] + label['width'], width)

    def test_interval_projection_crosses_and_clears(self):
        self.page.goto(self.url + '#course/interval')
        self.page.wait_for_selector('input[data-w="interval:nf"]')
        self.page.locator('input[data-w="interval:nf"]').fill('0')
        self.assertIn('Crosses zero', self.page.locator('.crs-fig').inner_text())
        self.page.locator('input[data-w="interval:nf"]').fill('1000')
        self.assertIn('Clears zero', self.page.locator('.crs-fig').inner_text())
        self.assertIn('Projection at fixed effect', self.page.locator('.crs-fig').inner_text())

    def test_catchup_primer_keeps_visual_reasoning_context(self):
        self.page.goto(self.url + '#learn?catchup=1')
        self.page.wait_for_selector('[data-primer] [data-cq]')
        self.assertEqual(self.page.locator('[data-primer] [data-study-check]').count(), 0)
        self.assertEqual(self.page.locator('[data-primer] .crs-fig').count(), 1)
        self.page.locator('[data-primer] [data-cq]').first.click()
        self.page.wait_for_selector('[data-l=primer-next]')
        self.page.locator('[data-l=primer-next]').click()
        self.assertNotIn('failed to draw', self.page.locator('#main').inner_text())

    def test_glossary_lesson_keyboard(self):
        self.page.goto(self.url + '#overview')
        self.page.wait_for_selector('.term')
        term = self.page.locator('.term').first
        term.focus()
        self.assertEqual(term.get_attribute('aria-describedby'), 'arx-term-definition')
        self.page.keyboard.press('Tab')
        self.assertTrue(self.page.evaluate('document.activeElement.matches(".term-pop a")'))
        self.page.keyboard.press('Enter')
        self.page.wait_for_url('**/#course/**')
        self.page.wait_for_selector('[data-cq]')


if __name__ == '__main__':
    unittest.main()
