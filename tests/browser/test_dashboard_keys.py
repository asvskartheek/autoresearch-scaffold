"""Browser regressions for keyboard navigation; run with Playwright installed.

    uv run --with playwright python tests/browser/test_dashboard_keys.py

Set ARX_BROWSER_EXECUTABLE to use an existing Chromium installation.
"""
import os
from pathlib import Path
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

KEYS = Path(__file__).resolve().parents[2] / 'autoresearch/web/keys.js'


@unittest.skipUnless(sync_playwright, "Install Playwright to run browser regressions")
class Keyboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        options = {'headless': True}
        if os.environ.get('ARX_BROWSER_EXECUTABLE'):
            options['executable_path'] = os.environ['ARX_BROWSER_EXECUTABLE']
        cls.browser = cls.pw.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1280, 'height': 900})
        self.page.route('http://arx.test/**', lambda r: r.fulfill(body='<html><head></head><body></body></html>', content_type='text/html'))
        self.page.goto('http://arx.test/')

    def tearDown(self):
        self.page.close()

    def load(self, html):
        self.page.set_content(html)
        self.page.add_script_tag(path=str(KEYS))
        self.page.wait_for_timeout(80)

    def test_open_thread_never_clicks_resolve(self):
        self.load('''<main id="main"></main><aside id="col">
          <div class="card" data-id="thread"><button id="resolve">Resolve</button><p>Thread</p></div>
          </aside><script>window.resolves=0;window.opens=0;
          document.querySelector('#resolve').onclick=e=>{e.stopPropagation();resolves++};
          document.querySelector('.card').onclick=()=>opens++;</script>''')
        self.page.keyboard.press('j')
        self.page.keyboard.press('Enter')
        self.page.keyboard.press('o')
        self.assertEqual(self.page.evaluate('resolves'), 0)
        self.assertEqual(self.page.evaluate('opens'), 2)

    def test_ring_moves_dom_focus_and_opens_question(self):
        self.load('''<main id="main"><button id="filter">All</button>
          <div class="q-row" data-qgo="one" tabindex="0"><span role="button" id="caret">Fold</span>
          <a href="#questions/one" tabindex="-1">Question one</a></div></main>
          <script>window.folds=0;document.querySelector('#caret').onclick=e=>{e.stopPropagation();folds++};
          document.querySelector('.q-row').onclick=()=>location.hash='questions/one';</script>''')
        self.page.locator('#filter').focus()
        self.page.keyboard.press('j')
        self.assertTrue(self.page.evaluate('document.activeElement===ARXK.focused()'))
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('location.hash'), '#questions/one')
        self.assertEqual(self.page.evaluate('folds'), 0)

    def test_start_items_and_search_leave_typing(self):
        self.load('''<main id="main"><input type="search" value="raw">
          <a class="sx-g" href="#goal/first">First goal</a>
          <a class="sx-g" href="#goal/second">Second goal</a></main>''')
        self.page.keyboard.press('j')
        self.assertEqual(self.page.evaluate('ARXK.focused().textContent'), 'First goal')
        self.page.keyboard.press('j')
        self.assertEqual(self.page.evaluate('ARXK.focused().textContent'), 'Second goal')
        self.page.keyboard.press('/')
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.locator('input').input_value(), 'raw')
        self.assertNotEqual(self.page.evaluate('document.activeElement.tagName'), 'INPUT')
        self.page.keyboard.press('/')
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('ARXK.focused().textContent'), 'First goal')

    def test_search_prefers_result_rows_over_section_links(self):
        self.load('''<main id="main"><input type="search">
          <a style="display:block;width:300px;height:30px" href="#hill/context">Context hill</a>
          <table><tbody><tr class="click" data-q="raw"><td><a href="#model/raw">Raw model</a></td></tr></tbody></table></main>''')
        self.page.keyboard.press('/')
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('ARXK.focused().tagName'), 'TR')

    def test_find_without_search_and_help_trap_focus(self):
        self.load('''<main id="main"><a class="sx-g" href="#goal/first">First goal</a>
          <a class="sx-g" href="#goal/second">Second goal</a></main>''')
        self.page.keyboard.press('/')
        self.page.keyboard.type('Second')
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('ARXK.focused().textContent'), 'Second goal')
        self.page.keyboard.press('?')
        for _ in range(30):
            self.page.keyboard.press('Tab')
            self.assertTrue(self.page.evaluate('!!document.activeElement.closest(".kh-ov")'))
        self.page.keyboard.press('Escape')
        self.assertEqual(self.page.locator('.kh-ov').count(), 0)

    def test_comment_pin_stays_on_its_brief_card(self):
        self.load('''<main id="main"><section data-card="goal:first"><h2>The same question</h2>
          <svg id="lnl" width="300" height="100"><circle cx="80" cy="50" r="12"/></svg></section></main>
          <script>window.S={afterRender:[]};window.saved=[];window.fetch=async (url,opts={})=>{
            if(opts.method==='POST'){const row=JSON.parse(opts.body);if(row.kind==='comment')saved.push({id:'test-pin',route:'overview',anchor:row.anchor,resolved:false,waiting:false,last_t:1,messages:[{body:row.body,author:'Tester',t:1}]});
              return {ok:true,json:async()=>({id:'test-pin'})}};
            return {ok:true,json:async()=>({threads:saved})}};</script>''')
        self.page.add_style_tag(path=str(KEYS.with_name('comments.css')))
        self.page.add_script_tag(path=str(KEYS.with_name('comments.js')))
        self.page.evaluate("S.afterRender.forEach(f=>f());ARXC.comment(document.querySelector('circle'))")
        self.page.keyboard.press('Enter')
        self.page.locator('.cm-pop textarea').fill('This guess belongs to the first card')
        self.page.locator('.cm-pop .go').click()
        self.page.wait_for_function("saved.length===1")
        self.assertEqual(self.page.evaluate("saved[0].anchor.key.context"), 'goal:first')
        self.page.keyboard.press('Escape')
        self.page.evaluate("document.querySelector('[data-card]').dataset.card='goal:second';S.afterRender.forEach(f=>f())")
        self.assertEqual(self.page.locator('.cm-pin[data-id="test-pin"]').count(), 0)
        self.page.evaluate("document.querySelector('[data-card]').dataset.card='goal:first';S.afterRender.forEach(f=>f())")
        self.assertEqual(self.page.locator('.cm-pin[data-id="test-pin"]').count(), 1)

    def test_project_number_includes_current_project(self):
        self.load('''<aside id="nav"><a class="nav proj" href="#project/one">One</a>
          <a class="nav proj on" href="#project/two">Two</a>
          <a class="nav proj" href="#project/three">Three</a></aside><main id="main"></main>''')
        self.page.keyboard.press('g')
        self.page.keyboard.press('3')
        self.assertEqual(self.page.evaluate('location.hash'), '#project/three')

    def test_pending_g_wins_over_view_digit_handler(self):
        self.load('''<aside id="nav"><a class="nav" href="#course">Course</a>
          <a class="nav proj" href="#project/one">One</a></aside><main id="main"></main>
          <script>window.answers=0;addEventListener('keydown',e=>{if(e.key==='1'){e.preventDefault();answers++}});</script>''')
        self.page.keyboard.press('g')
        self.page.keyboard.press('1')
        self.assertEqual(self.page.evaluate('answers'), 0)
        self.assertEqual(self.page.evaluate('location.hash'), '#project/one')


if __name__ == '__main__':
    unittest.main()
