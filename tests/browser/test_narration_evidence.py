"""Actual dashboard flows over isolated ledgers; no provider or real-project writes."""
import json, os, socket, subprocess, sys, tempfile, time, unittest, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
from autoresearch.core import Project, Task
ROOT=Path(__file__).resolve().parents[2]

class EvidenceFlows(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
  (self.root/'research.json').write_text(json.dumps(dict(name='Narration regression',primary_dataset='ds',higher_is_better=True,ladder=[dict(rung='full',checks=[dict(slice='full',rule='better')])])))
  self.p=Project(self.root);self.p.add_dataset('ds',list(range(10)))
  self.p.add_model('base',status='champion',title='Base');self.run_eval('base',4)
  self.p.open_goal('g','Eight correct','full',.8);self.p.open_hill('h','Improve answers','full',goal='g')
  self.p.add_model('winner',hill='h',title='Winner');self.run_eval('winner',9)
  sock=socket.socket();sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1];sock.close()
  env=os.environ|{'PYTHONPATH':str(ROOT),'ARX_HOME':str(self.root/'registry')}
  self.proc=subprocess.Popen([sys.executable,'-m','autoresearch','serve','--port',str(self.port)],cwd=self.root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  self.url=f'http://127.0.0.1:{self.port}'
  for _ in range(100):
   try: urllib.request.urlopen(self.url+'/api/state');break
   except OSError:time.sleep(.05)
  self.pw=sync_playwright().start();self.browser=self.pw.chromium.launch(headless=True,executable_path=os.environ.get('ARX_BROWSER_EXECUTABLE','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
  self.page=self.browser.new_page();self.errors=[]
  self.page.on('pageerror',lambda e:self.errors.append(str(e)))
  self.page.on('console',lambda e:self.errors.append(e.text) if e.type=='error' else None)
 def tearDown(self):
  self.browser.close();self.pw.stop();self.proc.terminate();self.proc.wait();self.tmp.cleanup()
  self.assertEqual(self.errors,[])
 def run_eval(self,m,n):
  t=Task(self.p,'eval','Controlled observation',model=m,slice='ds/full')
  for i in range(10):t.add_row(dict(id=str(i),score=int(i<n)))
  t.finish();return t
 def go(self,route):
  self.page.goto(self.url+'/'+route);self.page.wait_for_function("typeof S !== 'undefined' && S.state?.goals?.g")
  self.page.wait_for_timeout(150)
 def test_achieved_same_model_poll_keeps_one_snapshot(self):
  self.p.set_model_status('base','retired');self.p.set_model_status('winner','champion');ev=self.p.achieve_goal('g')
  self.go('#goal/g');self.assertIn('+5 against',self.page.locator('#main').inner_text())
  self.run_eval('winner',2)
  self.page.wait_for_function('S.state.goals.g.current_observation?.runs === 2',timeout=15000)
  self.assertEqual(self.page.evaluate('S.state.goals.g.value'),.9)
  self.assertEqual(self.page.evaluate('S.state.goals.g.task'),ev['task'])
  text=self.page.locator('#main').inner_text();self.assertIn('+5 against',text);self.assertIn('Later observations',text)
  self.assertNotIn('+2 against',text)
  self.assertEqual(self.page.locator('.gl-prog .gl-bar i').get_attribute('style'),'width:100.0%')
 def test_ready_candidate_and_mobile_gate_rules(self):
  self.go('#goal/g');text=self.page.locator('#main').inner_text();self.assertIn('ready for promotion review',text);self.assertNotIn('No candidate is climbing',text)
  self.page.set_viewport_size(dict(width=375,height=900));self.go('#model/winner')
  details=self.page.locator('.md-mobile-evidence').first;details.locator('summary').click()
  self.assertIn('Better than champion',details.inner_text());self.assertIn('9 of 10',details.inner_text());self.assertIn('4 of 10',details.inner_text())
  details.locator('a').click();self.page.wait_for_url('**/#task/*');self.assertIn('Controlled observation',self.page.locator('#main').inner_text())
 def test_incompatible_baseline_does_not_imply_progress(self):
  for model,contract in [('base','old'),('winner','new')]:
   for t in self.p.slice_evals(model,'ds/full'):
    f=self.p.task_dir(t['id'])/'task.json';data=json.loads(f.read_text());data['config']={'baseline_contract':contract};f.write_text(json.dumps(data))
  self.p.set_model_status('base','retired');self.p.set_model_status('winner','champion')
  self.go('#goal/g');text=self.page.locator('#main').inner_text()
  self.assertIn('no matching comparison under the current harness',text)
  self.assertNotIn('latest runs, unpaired',text)
  self.assertNotIn('+5 against',text)
  self.assertEqual(self.page.locator('.gl-prog .gl-trk.abs').count(),1)

 def test_measurement_action_names_actual_slice_and_stalled_attempt(self):
  self.p.add_dataset('other',list(range(2)));self.p.open_goal('unmeasured','Other goal','other/full',1)
  t=Task(self.p,'eval','Interrupted full audit',model='winner',slice='ds/full');t.add_row(dict(id='0',score=1))
  # Remove the prior candidate completion, leaving an actual stalled first full attempt.
  for r in self.p.slice_evals('winner','ds/full'):self.p.supersede('winner','ds/full',t.id)
  f=self.p.task_dir(t.id)/'task.json';r=json.loads(f.read_text());r['heartbeat']=r['updated']=time.time()-172800;f.write_text(json.dumps(r))
  self.go('#start');text=self.page.locator('#main').inner_text();self.assertNotIn('never measured',text)
  copies=self.page.locator('.sx-nx button').evaluate_all('(xs)=>xs.map(x=>x.outerHTML).join(" ")');self.assertIn('other/full',copies);self.assertIn('arx eval record',copies)
  self.go('#model/winner');text=self.page.locator('#main').inner_text();self.assertNotIn('Not run yet',text);self.assertIn('Close the stalled attempt',text)

if __name__=='__main__':unittest.main()
