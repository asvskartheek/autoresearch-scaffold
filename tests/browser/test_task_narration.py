"""Actual dashboard flows for incomplete runs, benchmark results and observed chronology.
Run: ARX_BROWSER_EXECUTABLE=/path/to/chrome uv run --with playwright python tests/browser/test_task_narration.py
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
from urllib.request import urlopen

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE))
from autoresearch.core import Project, Task


@unittest.skipUnless(sync_playwright, 'Install Playwright')
class TaskNarration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        (cls.root / 'research.json').write_text(json.dumps(dict(name='Narration fixtures', ladder=[])))
        project = Project(cls.root)
        project.add_dataset('ds', list(range(20)))
        project.add_model('base', status='champion')
        project.add_model('candidate', change='Use a custom vector kernel.')
        start = int(time.time() // 86400 - 4) * 86400 + 86300
        def task(tid, kind, title, summary=None, offset=0, duration=60, model=None, parent=None, failed=False, n=None):
            t = Task(project, kind, title, tid=tid, model=model, parent=parent, slice='ds/full' if kind == 'eval' else None)
            if n is not None:
                for i in range(n):
                    t.add_row(dict(id=str(i), score=int(i < n - 1)))
                t.progress(n, 20)
            t.finish('failed' if failed else 'done', summary=summary)
            data = json.loads((t.dir / 'task.json').read_text())
            data.update(created=start+offset, ended=start+offset+duration, updated=start+offset+duration, heartbeat=start+offset+duration)
            (t.dir / 'task.json').write_text(json.dumps(data))
            return t
        task('base-run', 'eval', 'Complete baseline', model='base', n=20)
        task('partial-run', 'eval', 'Cancelled candidate audit', model='candidate', n=4, failed=True, offset=70)
        stalled = task('stalled-run', 'eval', 'Silent candidate audit', model='candidate', n=3, failed=True, offset=140)
        data=json.loads((stalled.dir/'task.json').read_text());data.pop('ended');data['status']='running'
        (stalled.dir/'task.json').write_text(json.dumps(data))
        task('analysis', 'analysis', 'Kernel investigation', model='candidate', offset=210)
        task('throughput', 'result', 'Measured kernel rows', parent='analysis', offset=220, summary={'throughput':[
            dict(backend='vllm', concurrency=1, tokens_per_second=324.4, minimum=323.0, maximum=324.7, repeats=5, source_run='kernel-one'),
            dict(backend='vllm', concurrency=512, tokens_per_second=9874.1, minimum=9847.7, maximum=9878.9, repeats=5, source_run='kernel-many')]})
        task('conclusion', 'result', 'Final throughput findings', offset=300, summary={'benchmark_report':{
            'conclusion':'Stock reached 9,876.4 generated tokens/s. The custom kernel improved one sequence by 3.8%.',
            'scope':'Five timed repeats; fixed-length offline batches, not a quality benchmark.',
            'cost':'Estimated rental $0.47; final invoice pending.'}})
        task('unknown', 'result', 'Other recorded result', offset=310, summary={'validation': {'hashes_matched':80,'caveats':['Offline only','No quality claim']}})
        task('maintenance', 'experiment', 'Paper port maintenance', offset=3*86400)
        models=project.models()
        for model in models.values():model['created']=start
        project._save('models', models)
        decisions=project.dir/'decisions.jsonl'
        if decisions.exists():
            decisions.write_text('\n'.join(json.dumps(dict(json.loads(line), t=start)) for line in decisions.read_text().splitlines()))
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port=sock.getsockname()[1]
        cls.log=(cls.root/'server.log').open('w+')
        cls.proc=subprocess.Popen([sys.executable,'-m','autoresearch','serve','--port',str(port)],cwd=cls.root,
            env=dict(os.environ,PYTHONPATH=str(SOURCE),ARX_HOME=str(cls.root/'registry')),stdout=cls.log,stderr=cls.log)
        cls.base=f'http://127.0.0.1:{port}'
        for _ in range(100):
            try:
                urlopen(cls.base+'/api/state',timeout=1).close();break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Server did not start')
        cls.pw=sync_playwright().start()
        options={'headless':True}
        if os.environ.get('ARX_BROWSER_EXECUTABLE'):options['executable_path']=os.environ['ARX_BROWSER_EXECUTABLE']
        cls.browser=cls.pw.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.proc.terminate();cls.proc.wait(timeout=5);cls.log.close();cls.tmp.cleanup()

    def setUp(self):
        self.page=self.browser.new_page(viewport={'width':1280,'height':900},timezone_id='UTC')
        self.errors=[]
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.on('console',lambda m:self.errors.append(m.text) if m.type=='error' and 'render' in m.text.lower() else None)

    def tearDown(self):
        self.assertEqual(self.errors,[])
        self.page.close()

    def route(self, route):
        self.page.goto(self.base+'/#'+route)
        self.page.wait_for_function("document.querySelector('#main') && !document.querySelector('#main .skel')")
        self.page.wait_for_timeout(250)
        return self.page.locator('#main')

    def test_failed_partial_run_leads_with_scope(self):
        main=self.route('task/partial-run')
        self.assertIn('Partial run · unranked', main.locator('.finding').inner_text())
        self.assertIn('4 of 20',main.locator('.finding').inner_text())
        self.assertNotIn('against the champion',main.locator('.finding').inner_text())
        self.assertIn('Exploratory subset comparison',main.inner_text())
        self.assertIn('Unranked; paired on the same 4',main.inner_text())
        self.assertIn('Failed · partial',main.inner_text())

    def test_stalled_archive_does_not_span_inactivity(self):
        main=self.route('archive')
        story=main.locator('.arc-st')
        self.assertIn('Latest research session',story.inner_text())
        self.assertNotIn('Paper port maintenance',story.inner_text())
        self.assertIn('Inactivity is excluded',story.inner_text())
        self.assertNotIn('4 d',story.locator('.arc-sn').inner_text())
        self.assertRegex(story.locator('.arc-sn').inner_text(), r'\d+ \w+, \d\d:\d\d–\d+ \w+, \d\d:\d\d')
        self.page.set_viewport_size({'width':375,'height':900})
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
        self.assertIn('Final throughput findings',story.inner_text())
        story.get_by_role('link',name='Silent candidate audit',exact=True).last.click()
        self.page.wait_for_function("location.hash==='#task/stalled-run' && document.querySelector('.tk-fix')")
        self.assertIn('Partial observations are unranked',main.inner_text())
        self.assertIn('arx task finish stalled-run --status failed',main.inner_text())

    def test_result_parent_child_navigation_and_mobile_rows(self):
        main=self.route('task/analysis')
        main.locator('a[href="#task/throughput"]').first.click()
        self.page.wait_for_selector('.tk-result-table')
        for width in (1280,375):
            self.page.set_viewport_size({'width':width,'height':900})
            self.assertEqual(self.page.locator('.tk-result-table tbody tr').count(),2)
            self.assertIn('9,874.1',main.inner_text())
            self.assertIn('Timed repeats',main.inner_text())
            self.assertIn('kernel-many',main.inner_text())
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth>innerWidth'))
        self.route('task/conclusion')
        self.assertIn('3.8%',main.locator('.finding').inner_text())
        self.assertIn('not a quality benchmark',main.inner_text())
        self.assertIn('final invoice pending',main.inner_text())
        self.route('task/unknown')
        self.assertIn('Recorded summary',main.inner_text())
        self.assertIn('Hashes matched',main.inner_text())
        self.assertIn('No quality claim',main.inner_text())


if __name__=='__main__':unittest.main()
