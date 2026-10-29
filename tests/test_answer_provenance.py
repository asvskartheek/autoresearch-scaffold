"""Answer retries and snapshots preserve the authored evidence across later runs."""
import json
import tempfile
import unittest
from pathlib import Path
from autoresearch import questions, features
from autoresearch.core import Project, Task

class AnswerProvenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'research.json').write_text(json.dumps({'name':'answers', 'ladder':[]}))
        self.p = Project(root)
        self.p.add_dataset('ds', list(range(4)))
        self.p.add_model('base', parent='', status='champion')
        self.run_scores([1,1,1,0])

    def tearDown(self):
        self.tmp.cleanup()

    def run_scores(self, scores):
        t = Task(self.p, 'eval', 'Synthetic answer evidence', model='base', slice='ds/full')
        for i, score in enumerate(scores):
            t.add_row(dict(id=i, score=score))
        t.finish()
        return t.id

    def test_snapshot_keeps_value_and_run_ids(self):
        q = questions.add(self.p, 'What did the baseline score?')
        saved = questions.settle(self.p, q['id'], 'answered', 'Three of four.', evidence=[dict(model='base',slice='ds/full')])
        snapshot = saved['evidence_snapshot']
        self.assertEqual(snapshot[0]['c'], 3)
        self.assertEqual(len(snapshot[0]['task_ids']), 1)
        self.run_scores([0,0,0,0])
        node = next(n for n in questions.tree(self.p)['nodes'] if n['id']==q['id'])
        self.assertEqual(node['evidence_snapshot'], snapshot)
        self.assertEqual(node['ev'][0]['c'], 2)
        self.assertEqual(len(node['ev'][0]['task_ids']), 2)

    def test_retry_preserves_failure_and_does_not_duplicate_active_request(self):
        q = questions.add(self.p, 'Why did the answer fail?')
        questions._save(self.p, q['id'], questions.stored(self.p)[q['id']] | {'error':'No answer returned'})
        retried = questions.retry(self.p, q['id'])
        self.assertEqual(retried['status'], 'agent')
        self.assertEqual(retried['attempts'][0]['error'], 'No answer returned')
        self.assertNotIn('error', retried)
        again = questions.retry(self.p, q['id'])
        self.assertEqual(again['inbox'], retried['inbox'])
        self.assertEqual(len(features.inbox(self.p)), 1)
        questions.settle(self.p, q['id'], 'answered', 'Recovered.')
        self.assertEqual(questions.stored(self.p)[q['id']]['attempts'][0]['error'], 'No answer returned')

if __name__ == '__main__':
    unittest.main()
