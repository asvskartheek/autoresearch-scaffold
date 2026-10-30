import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from autoresearch import Project

class HarnessMatchedGates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);(root/'.research').mkdir()
        (root/'research.json').write_text(json.dumps({'primary_dataset':'d','ladder':[{'rung':'full','checks':[{'slice':'full','rule':'better'}]}]}))
        self.p=Project(root);self.p.add_dataset('d',['a','b','c','d'])
        self.p.add_model('base',status='champion');self.p.add_model('cand',parent='base')
        h=self.p.slice('d/full')['hash']
        self.runs=[{'id':'old','model':'base','slice':'d/full','slice_hash':h,'ended':1,'config':{'baseline_contract':'A'}},
                   {'id':'new','model':'base','slice':'d/full','slice_hash':h,'ended':3,'config':{'baseline_contract':'B'}},
                   {'id':'cand','model':'cand','slice':'d/full','slice_hash':h,'ended':2,'config':{'baseline_contract':'A'}}]
        self.p.evals=Mock(side_effect=lambda:self.runs)
        self.values={'old':[1,1,0,0],'new':[1,1,1,1],'cand':[1,1,1,0]}
        self.p.rows=Mock(side_effect=lambda tid:[{'id':i,'score':v} for i,v in zip('abcd',self.values[tid])])
    def test_parallel_newer_baseline_cannot_change_comparison(self):
        g=self.p.gate('cand');self.assertTrue(g['promotable'])
        self.assertEqual(g['rungs'][0]['checks'][0]['base_task'],'old')
        self.assertEqual(g['rungs'][0]['checks'][0]['delta'],.25)
    def test_missing_contract_match_requires_baseline(self):
        self.runs=self.runs[1:];g=self.p.gate('cand')
        self.assertFalse(g['promotable']);self.assertEqual(g['next'],[{'model':'base','slice':'d/full'}])
    def test_candidate_repeats_from_other_contract_are_excluded(self):
        self.runs.insert(0, dict(self.runs[-1], id="other-cand", ended=0,
                                 config={"baseline_contract": "B"}))
        self.values["other-cand"] = [0, 0, 0, 0]
        check = self.p.gate("cand")["rungs"][0]["checks"][0]
        self.assertEqual(check["delta"], .25)
        self.assertEqual((check["cand_runs"], check["base_runs"]), (1, 1))
        self.assertEqual(check["baseline_contract"], "A")

    def test_matching_repeats_are_still_pooled(self):
        self.runs.append(dict(self.runs[0], id="repeat", ended=4))
        self.values["repeat"] = [1, 0, 0, 0]
        check = self.p.gate("cand")["rungs"][0]["checks"][0]
        self.assertEqual(check["base_task"], "repeat")
        self.assertEqual(check["base_runs"], 2)
        self.assertEqual(check["delta"], .375)

    def test_pooled_scores_and_teaching_match_the_gate_contract(self):
        from autoresearch import learn, reference
        self.assertEqual(sum(self.p.pooled_scores("base", "d/full").values()), 4)
        self.assertEqual(sum(self.p.pooled_scores("base", "d/full", reference_model="cand").values()), 2)
        self.assertEqual(learn._pair(self.p, "cand", "base", "d/full", 1)["delta"], .25)
        ix = reference._Index(self.p)
        self.assertEqual(reference._paired(ix, "cand", "base", "d/full", 1)["delta"], .25)
        self.assertEqual([t["id"] for t in ix.compatible("base", "d/full", "cand")], ["old"])

    def test_teaching_does_not_invent_an_unmatched_comparison(self):
        from autoresearch import learn, reference
        self.runs = self.runs[1:]
        self.assertIsNone(learn._pair(self.p, "cand", "base", "d/full", 1))
        self.assertIsNone(reference._paired(reference._Index(self.p), "cand", "base", "d/full", 1))

    def test_errors_are_exposed_without_altering_gate_policy(self):
        self.runs[0]['summary'] = {'errors': 2}
        check = self.p.gate('cand')['rungs'][0]['checks'][0]
        self.assertEqual(check['base_errors'], 2)
        self.assertEqual(check['cand_errors'], 0)
        self.assertEqual(check['delta'], .25)
        self.assertEqual(check['state'], 'pass')

    def test_undeclared_candidate_never_pools_declared_champion_runs(self):
        # the champion's A and B runs are two harnesses: a candidate that declares none is paired with neither
        self.runs[-1]['config']={};g=self.p.gate('cand')
        self.assertFalse(g['promotable']);self.assertEqual(g['rungs'][0]['checks'][0]['state'],'need_baseline')
        self.assertEqual(g['next'],[{'model':'base','slice':'d/full'}])

    def test_undeclared_runs_pool_with_each_other(self):
        for t in self.runs:t['config']={}
        check=self.p.gate('cand')['rungs'][0]['checks'][0]
        self.assertEqual((check['base_task'],check['base_runs']),('new',2))
        self.assertEqual(check['delta'],.0)
        self.assertNotIn('baseline_contract',check)

if __name__=='__main__':unittest.main()
