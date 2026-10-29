"""Content regressions based on captured public project metadata, not rendering health."""
import json
from pathlib import Path
import unittest
from autoresearch import course, learn

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/course_project_semantics.json').read_text())


class CapturedProject:
    def __init__(self, key):
        self.data = FIXTURES[key]
        self.config = self.data['config']
    def slices(self): return self.data['slices']
    def datasets(self): return self.data['datasets']
    def goals(self): return self.data['goals']
    def goal_status(self, name): return self.data['goals'][name]
    def models(self): return self.data['models']
    def champion(self): return self.data['champion']
    def hills(self): return self.data['hills']
    def evals(self): return []


class CourseSemantics(unittest.TestCase):
    def test_three_case_goal_never_offers_thirteen_more_answers(self):
        # Exact reported failure: old lesson_goal used [left, need, have, left+10]
        # for N=3/have=0/need=3, producing ["3", "0", "13"].
        from tests.test_learn import ledger, run
        p=ledger();p.add_slice('ds/tiny',['0','1','2']);p.add_model('base',status='champion')
        run(p,'base',[0,0,0],'ds/tiny');p.open_goal('g','Three-case goal','ds/tiny',1)
        lesson=course.lesson_goal(p,course._ledger(p),learn)
        self.assertEqual((lesson['fig']['N'],lesson['fig']['have'],lesson['fig']['need']),(3,0,3))
        options=[o for c in lesson['checks'] for o in c['o']]
        self.assertNotIn('13',options)
        self.assertTrue(all(not o.isdigit() for o in options))
        self.assertIn('ds/tiny',lesson['checks'][0]['q'])

    def test_projector_scopes_never_claim_thirteen_of_forty(self):
        p=CapturedProject('projector')
        for lesson in [course.lesson_slice(p,{},learn),course.lesson_project_data(p,{},learn)]:
            f=lesson['fig'];self.assertNotIn('N',f)
            row=next(r for r in f['rows'] if r['id']=='android/checks')
            self.assertEqual(row['n'],13)
            self.assertIsNone(row['dataset_n'])
            self.assertEqual(row['name'],'android/checks')
            self.assertNotIn('13 of',json.dumps(lesson))

    def test_registered_dataset_is_own_denominator(self):
        p=CapturedProject('gsm8k');rows=course._slice_rows(p,learn)
        self.assertTrue(rows)
        self.assertTrue(all(r['dataset_n']==1319 for r in rows))
        self.assertTrue(all(r['n']<=r['dataset_n'] for r in rows))

    def test_projector_goal_uses_positive_ms_and_lower_direction(self):
        p=CapturedProject('projector');g=course._goals(p)[0]
        # Prefer the actual continuous goal, independent of dictionary insertion order.
        g=next(g for g in course._goals(p) if g['slice']=='cold/n24')
        row=course._goal_row(p,g,learn)
        self.assertEqual(row['unit'],'ms');self.assertTrue(row['lower'])
        self.assertEqual(row['target'],1000);self.assertGreater(row['value'],1000)
        self.assertEqual(row['n'],24)
        self.assertNotIn('N',row)

    def test_unmeasured_qwen_goal_remains_visible_and_has_its_unit(self):
        p=CapturedProject('qwen');lesson=course.lesson_project_goal(p,{'goals':course._goals(p)},learn)
        self.assertTrue(lesson['fig']['rows'])
        for row in lesson['fig']['rows']:
            self.assertFalse(row['measured']);self.assertIsNone(row['value'])
            self.assertEqual(row['unit'],'tok/s')
        self.assertIn('no champion is registered',lesson['checks'][0]['q'])
        self.assertNotIn('80 of 100',json.dumps(lesson))

    def test_real_project_goal_options_require_evidence_not_count_guessing(self):
        for key in FIXTURES:
            p=CapturedProject(key)
            lesson=course.lesson_goal(p,{'goals':course._goals(p)},learn)
            for check in lesson['checks']:
                self.assertIn(check['a'],check['o'])
                self.assertEqual(len(check['o']),len(set(check['o'])))
                self.assertTrue(all(not o.replace(',','').isdigit() for o in check['o']))

    def test_passing_candidate_is_not_automatically_promoted(self):
        p=CapturedProject('projector')
        check=course.lesson_candidate(p,{'models':p.models()},learn)['checks'][0]
        self.assertEqual(check['a'],'Ready for promotion; still a candidate')

    def test_real_hill_examples_have_honest_provenance(self):
        p=CapturedProject('gsm8k')
        lesson=course.lesson_project_hills(p,{},learn)
        examples=[r for r in lesson['fig']['rows'] if r['examples']]
        self.assertTrue(examples)
        self.assertTrue(all('not per-example evaluation evidence' in r['example_provenance'] for r in examples))
        self.assertTrue(all({'input','wrong','right','why'}<=set(e) for r in examples for e in r['examples']))
        self.assertIn('control result violates',lesson['checks'][0]['q'])

    def test_project_without_examples_never_refers_to_an_illustration(self):
        import copy
        p=CapturedProject('qwen');p.data=copy.deepcopy(p.data)
        for hill in p.data['hills'].values():hill.pop('examples',None)
        lesson=course.lesson_project_hills(p,{},learn)
        self.assertNotIn('illustrated error',lesson['checks'][0]['q'])

    def test_duplicate_model_titles_keep_recorded_qualifiers_and_budgets(self):
        p=CapturedProject('gsm8k')
        self.assertEqual(learn._title(p,'qwen3-4b-rl-archived'),'Qwen3-4B RL — archived baseline')
        self.assertEqual(learn._title(p,'qwen3-4b-rl-fresh-v1'),'Qwen3-4B RL — fresh audited harness')
        for model,budget in [('thinking4b-numeric8192-v1','8,192'),('thinking4b-numeric32768-v1','32,768')]:
            title=learn._title(p,model)
            self.assertIn(budget+' output tokens',title)
            self.assertNotIn(model,title)

    def test_rung_continuous_tolerance_is_not_scaled_to_percentage_points(self):
        from tests.test_goal_units import ledger
        p=ledger();p.add_dataset('mem',list(range(4)))
        p.add_slice('cold/n4',list(range(4)),scale='continuous',unit='ms',metric='minus ms')
        p.add_slice('mem/n4',list(range(4)),scale='continuous',unit='MB',metric='minus MB')
        p.open_hill('h','Cold start','cold/n4',control='mem/n4')
        p.add_model('base',status='champion');p.add_model('candidate',parent='base',hill='h')
        config=p.config;config['ladder']=[{'rung':'dev','checks':[{'slice':'@hill.target','rule':'better'}, {'slice':'@hill.control','rule':'not_worse','tolerance':.05}]}]
        (p.root/'research.json').write_text(json.dumps(config))
        lesson=course.lesson_rung(p,{},learn)
        check=next(c for c in lesson['fig']['checks'] if c['source_ref']=='@hill.control')
        self.assertEqual((check['slice'],check['unit'],check['display_bar'],check['better']),('mem/n4','MB',.05,-1))

    def test_unresolved_symbolic_rung_has_no_invented_numeric_unit(self):
        from tests.test_learn import ledger
        p=ledger();p.add_model('base',status='champion')
        config=p.config;config['ladder']=[{'rung':'dev','checks':[{'slice':'@hill.control','rule':'not_worse','tolerance':.05}]}]
        (p.root/'research.json').write_text(json.dumps(config))
        check=course.lesson_rung(p,{},learn)['fig']['checks'][0]
        self.assertFalse(check['resolved']);self.assertIsNone(check['unit']);self.assertIsNone(check['display_bar'])

    def test_champion_settings_are_recorded_not_inferred_from_hill_examples(self):
        p=CapturedProject('gsm8k')
        data={'champ':p.champion(),'models':p.models(),'full':None}
        lesson=course.lesson_project_champion(p,data,learn)
        row=lesson['fig']['rows'][0]
        self.assertEqual(row['settings'],[{'label':'Adapter','value':'Disabled'},{'label':'Output budget','value':'1,024 tokens'},{'label':'Decoding','value':'Greedy'}])
        self.assertNotIn('examples',row)
        self.assertTrue(all('settings' not in r for r in lesson['fig']['rows'][1:]))
        self.assertIn('holding the others',lesson['checks'][0]['a'])

    def test_continuous_interval_preserves_improvement_direction(self):
        class Display:
            @staticmethod
            def _ci_viz(*args):return dict(delta=7,lo=-3,hi=17,n=12,unit='MB',better=-1)
        fig=course._ci_of(None,Display,{'slice':'mem/n12'})
        self.assertEqual(fig['better'],-1)


if __name__=='__main__':unittest.main()
