"""Actual isolated dashboard answer flows. No providers or real-project writes.
ARX_BROWSER_EXECUTABLE=/path/to/chrome uv run --with playwright python tests/browser/test_answer_flows.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from autoresearch import questions, features, answer
from autoresearch.core import Project, Task
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

@unittest.skipUnless(sync_playwright, 'Install Playwright for actual browser flows')
class AnswerFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / 'project'
        root.mkdir()
        (root/'research.json').write_text(json.dumps({'name':'Answer flow fixture','ladder':[]}))
        cls.project = p = Project(root)
        p.add_dataset('ds',list(range(4)))
        p.add_model('base', parent='', status='champion', title='Base model')
        t=Task(p,'eval','Four synthetic cases',model='base',slice='ds/full')
        for i in range(4): t.add_row(dict(id=i,score=int(i<3)))
        t.finish()
        p.open_goal('goal','Four of four','ds/full',1)
        p.open_hill('hill','Example hill','ds/full',goal='goal')
        cls.failed = questions.ask(p,'Why did this attempt fail?')['id']
        item=next(it for it in features.inbox(p) if it['ref']==cls.failed)
        features.update(p,item['id'],status='failed',error='The agent returned no answer. Retry the question.')
        answer._fail_reply(p,item,'The agent returned no answer. Retry the question.')
        cls.human=questions.add(p,'Restart stalled full-set candidate evals',needs_human=True,lenient=True)['id']
        cls.doc=questions.add(p,'Explain the result')['id']
        html='''<!doctype html><html><head><title>Evidence</title></head><body>
        <button onclick="document.getElementById('result').textContent='Revealed'">Reveal</button><p id="result">Hidden</p>
        <a href="#model/base">Base model</a><a href="#hill/hill">Example hill</a><a href="#goal/goal">Example goal</a>
        <a href="#details">Details section</a><div style="height:1500px"></div><section id="details">Section content</section>
        </body></html>'''
        questions.settle(p,cls.doc,'answered','Three of four.',evidence=[dict(model='base',slice='ds/full')],doc=html)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        cls.url=f'http://127.0.0.1:{port}/'
        env=os.environ|{'ARX_HOME':str(Path(cls.tmp.name)/'arx-home'),'PYTHONPATH':str(ROOT)}
        cls.log=open(Path(cls.tmp.name)/'server.log','w')
        cls.server=subprocess.Popen([sys.executable,'-c',f'from autoresearch.server import serve; serve({port}, {str(root)!r})'],cwd=ROOT,env=env,stdout=cls.log,stderr=cls.log)
        for _ in range(100):
            try: urlopen(cls.url+'api/state',timeout=1);break
            except OSError: time.sleep(.05)
        cls.pw=sync_playwright().start()
        opts={'headless':True}
        if os.environ.get('ARX_BROWSER_EXECUTABLE'): opts['executable_path']=os.environ['ARX_BROWSER_EXECUTABLE']
        cls.browser=cls.pw.chromium.launch(**opts)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.server.terminate();cls.server.wait(timeout=10);cls.log.close();cls.tmp.cleanup()

    def setUp(self):
        self.page=self.browser.new_page(viewport={'width':1280,'height':900})
        self.page.route('**/favicon.ico', lambda r:r.fulfill(status=204))
        self.errors=[]
        self.page.on('pageerror', lambda error:self.errors.append(str(error)))
        self.page.on('console',lambda message:self.errors.append(message.text+' '+str(message.location)) if message.type=='error' else None)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors,[])

    def open_doc(self):
        self.page.goto(self.url+'#answer/'+self.doc)
        self.page.wait_for_selector('.q-rwrap.ok .q-reader')
        self.page.wait_for_function("getComputedStyle(document.querySelector('.q-reader')).opacity==='1'")
        self.page.wait_for_timeout(150)
        return self.page.locator('.q-reader').element_handle().content_frame()

    def test_evidence_links_route_host_sections_stay_in_sandbox(self):
        for route,label in [('model/base','Base model'),('hill/hill','Example hill'),('goal/goal','Example goal')]:
            frame=self.open_doc()
            frame.get_by_text('Reveal',exact=True).click()
            frame.wait_for_function("document.getElementById('result').textContent==='Revealed'",timeout=2000)
            frame.get_by_text(label,exact=True).click()
            self.page.wait_for_url('**/#'+route)
        frame=self.open_doc()
        frame.get_by_text('Details section',exact=True).click()
        self.assertEqual(self.page.url,self.url+'#answer/'+self.doc)
        frame.wait_for_function("document.getElementById('details').getBoundingClientRect().top < innerHeight",timeout=2000)
        self.assertLess(frame.locator('#details').bounding_box()['y'],900)
        self.assertEqual(self.page.locator('.q-reader').get_attribute('sandbox'),'allow-scripts allow-popups')
        self.assertTrue(frame.evaluate("(()=>{try{parent.document;return false}catch(e){return e.name==='SecurityError'}})()"))
        frame.evaluate("parent.postMessage({type:'arx-answer-route',href:'javascript:alert(1)'},'*')")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.url,self.url+'#answer/'+self.doc)

    def test_failed_attempt_retry_and_legacy_handoff(self):
        self.page.goto(self.url+'#questions/'+self.failed)
        self.page.get_by_text('Retry answer',exact=True).wait_for()
        self.assertIn('The agent returned no answer',self.page.locator('#q-panel').inner_text())
        self.page.get_by_text('Retry answer',exact=True).click()
        self.page.wait_for_function("!document.querySelector('[data-qact=retry]')")
        self.assertEqual(questions.stored(self.project)[self.failed]['status'],'agent')
        self.page.goto(self.url+'#questions/'+self.human)
        self.page.get_by_text('Request decision context',exact=True).wait_for()
        self.assertIn('Time and cost are not recorded',self.page.locator('#q-panel').inner_text())

    def test_authored_snapshot_and_mobile_reference(self):
        self.page.goto(self.url+'#questions/'+self.doc)
        self.page.get_by_text('Refresh answer',exact=True).wait_for()
        self.assertIn('Evidence saved with this answer',self.page.locator('#q-panel').inner_text())
        self.page.get_by_text('Current ledger evidence',exact=True).click()
        self.assertEqual(self.page.locator('.q-ev').count(),2)
        self.page.set_viewport_size({'width':375,'height':900})
        self.page.goto(self.url+'reference/base')
        self.page.locator('#bTheme').wait_for()
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),375)
        self.assertLessEqual(self.page.locator('#bTheme').bounding_box()['x']+self.page.locator('#bTheme').bounding_box()['width'],375)

if __name__=='__main__': unittest.main()
