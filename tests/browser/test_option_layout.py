"""Brief shortcut badges must not become part of numeric answer labels."""
import os
from pathlib import Path
import unittest
from tests.browser import test_learning_flows as fixtures
sync_playwright = fixtures.sync_playwright

@unittest.skipUnless(sync_playwright, 'Install Playwright for option layout checks')
class OptionLayout(unittest.TestCase):
    setUpClass = classmethod(fixtures.LearningFlows.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.LearningFlows.tearDownClass.__func__)

    def test_brief_predict_and_spot_labels(self):
        page=self.browser.new_page(viewport={'width':1200,'height':850})
        errors=[]
        page.route('**/favicon.ico',lambda r:r.fulfill(status=204))
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
        # Render the real Brief components with inert synthetic cards. No learner POST is made.
        page.goto(self.url+'#overview')
        page.wait_for_function('typeof L!=="undefined" && S.state!==null')
        base={'id':'numeric-option-layout','type':'choice','method':'predict','label':'Synthetic','q':'Choose the numeric answer','tone':'acc','opts':['3','2','1']}
        spot={**base,'id':'spot-option-layout','method':'spot','methods':['spot'],'q':'Choose the inconsistent part','task':{'parts':['counts','delta','interval'],'viz':{'kind':'ci','n':4,'wins':3,'losses':1,'delta':50,'lo':-10,'hi':70,'unit':'pts'}}}
        try:
            for width in [1200,375]:
                page.set_viewport_size({'width':width,'height':850})
                for kind,card,label in [('predict',base,'3'),('spot',spot,'3 fixed · 1 broken')]:
                    page.evaluate('''c=>{
                        L.b={cards:[c]};L.cur=0;L.ui={};
                        document.querySelector('#app').classList.remove('nav-open');
                        document.querySelector('#main').innerHTML='<section class="lrn"><div class="stage">'+cardHTML(c)+'</div></section>';
                    }''',card)
                    if width<=560:
                        page.wait_for_function("document.querySelector('#nav').getBoundingClientRect().right <= 1")
                    answer=page.get_by_role('button',name=label,exact=True)
                    answer.wait_for()
                    self.assertEqual(answer.locator('kbd').get_attribute('aria-hidden'),'true')
                    self.assertEqual(answer.locator('.opt-label').inner_text(),label)
                    box=answer.locator('.opt-label').bounding_box()
                    if width>560:
                        badge=answer.locator('kbd').bounding_box()
                        self.assertGreaterEqual(box['x']-badge['x']-badge['width'],8)
                    else:
                        self.assertFalse(answer.locator('kbd').is_visible())
                    self.assertLessEqual(box['x']+box['width'],width)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                    if os.environ.get('ARX_BROWSER_SCREENSHOTS'):
                        out=Path(os.environ['ARX_BROWSER_SCREENSHOTS']);out.mkdir(parents=True,exist_ok=True)
                        page.screenshot(path=str(out/f'brief-{kind}-{width}.png'),full_page=True)
            self.assertEqual(errors,[])
        finally:page.close()

if __name__=='__main__':unittest.main()
