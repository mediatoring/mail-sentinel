"""Behavioral contracts for host orchestration, bounded delegation and recovery."""
import dataclasses
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from sentinel.agent import Agent, FINISH
from sentinel.budget import RunBudget
from sentinel.harness import BASELINE, SPECIALISTS
from sentinel.queue import QueueStore
from sentinel.rules import check_status
from sentinel.reports import complete_report
from sentinel.tools import Registry, Tool, schema
from test_security import registry, ModelDouble, call, finish


class HarnessTests(unittest.TestCase):
    def test_baseline_precedes_first_model_call_and_does_not_cost_model_steps(self):
        model = ModelDouble([finish(('B01',), verdict='INCONCLUSIVE')])
        result = Agent(registry(automatic_checks=True), model).run()
        self.assertEqual(result['steps'], 1)
        self.assertEqual([e['tool'] for e in model.contexts[0]['evidence']], list(BASELINE))
        self.assertIn('case_state', model.contexts[0])

    def test_early_high_risk_rejected_then_explicit_handoff(self):
        model = ModelDouble([call('inspect_links'), finish(verdict='HIGH_RISK'), finish(verdict='INCONCLUSIVE')])
        result = Agent(registry(), model).run()
        self.assertEqual(result['report']['coverage'], 'partial')
        self.assertTrue(result['report']['requires_human_review'])
        self.assertEqual(result['events'][1]['type'], 'completion_rejected')
        self.assertTrue(model.contexts[2]['completion_feedback']['pending_checks'])

    def test_agent_can_repair_completion_and_continue(self):
        model = ModelDouble([finish(('B01',), verdict='LOW_RISK'), call('verify_payment'), call('search_policy'), finish(('B01','E01','E02'), verdict='LOW_RISK')])
        result = Agent(registry(automatic_checks=True), model).run()
        self.assertEqual(result['report']['verdict'], 'LOW_RISK')
        self.assertTrue(result['report']['checks_complete'])

    def test_policy_requires_every_page_including_missing_middle(self):
        for offsets in ([0], [0,10], [0,5,10]):
            reg = registry()
            reg.org['policies'] = [{'id':str(i),'title':'Rule','text':'Approval required'} for i in range(11)]
            evidence = [reg.evidence(f'P{i}', 'search_policy', {'offset':offset}, 'ok', reg.execute('search_policy', {'offset':offset})) for i,offset in enumerate(offsets)]
            row = next(r for r in check_status(reg,evidence) if r['tool']=='search_policy')
            self.assertEqual(row['state'], 'performed' if len(offsets)==3 else 'not_performed')
            if len(offsets)<3:
                self.assertEqual(row['next_offset'],5)

    def test_no_progress_stops_before_budget_exhaustion(self):
        model = ModelDouble([call('inspect_links')]*12)
        result = Agent(registry(), model).run()
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(len(model.contexts),3)
        self.assertEqual(len([e for e in result['events'] if e['type']=='tool']),2)

    def test_claim_cannot_reference_unobserved_evidence(self):
        done=finish()
        done['arguments']['claims']=[{'statement':'Authenticated sender','evidence_ids':['OTHER'], 'counter_evidence_ids':[], 'limitations':[]}]
        model=ModelDouble([call('inspect_links'),done,finish()])
        result=Agent(registry(),model).run()
        self.assertEqual(result['events'][1]['reason'],'invalid_evidence_or_claims')
        self.assertEqual(result['status'],'completed')

    def test_specialist_permission_and_global_budget(self):
        reg=registry(max_steps=8)
        reg.add(Tool('secret_plugin','Must not reach child',schema(),lambda:{},check=False))
        class Probe(ModelDouble):
            def decide(self,system,context,tools):
                self.names={t['name'] for t in tools}
                self.system=system
                return super().decide(system,context,tools)
        model=Probe([finish(('B01',))])
        parent=Agent(reg,model)
        result=parent.consult('payments','Check this account')
        self.assertEqual(model.names,set(SPECIALISTS['payments'])|{'finish_investigation'})
        self.assertEqual(result['assessment']['report']['proposed_action'],'none')
        self.assertEqual(parent.budget.calls,1)
        self.assertNotIn('consult_specialist',model.names)
        self.assertNotIn('Check this account',model.system)
        self.assertEqual(model.contexts[0]['delegated_question'],'Check this account')

    def test_disabled_tool_stays_disabled_in_specialist(self):
        reg=registry(check_modes={'verify_payment':'off'})
        class Probe:
            def decide(self,system,context,tools):
                assert 'verify_payment' not in [t['name'] for t in tools]
                return finish(('B01',))
        result=Agent(reg,Probe()).consult('payments')
        self.assertEqual(result['assessment']['status'],'completed')

    def test_resume_revalidates_evidence_and_preserves_unique_ids_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp)
            first=registry(automatic_checks=True)
            Agent(first,ModelDouble([call('verify_payment')]),RunBudget(first.c,store=store)).run()
            second=registry(automatic_checks=True)
            model=ModelDouble([call('search_policy'),finish(('B01','E01','E02'))])
            result=Agent(second,model,RunBudget(second.c,store=store)).run()
            self.assertEqual(result['status'],'completed')
            self.assertTrue(any(e.get('recovered') for e in result['events']))
            ids=[e['id'] for e in result['events'] if e['type']=='tool']
            self.assertEqual(len(ids),len(set(ids)))
            self.assertGreater(result['steps'],2)
            with store.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM investigation_cache').fetchone()[0],0)

    def test_changed_evidence_invalidates_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp)
            reg=registry(automatic_checks=True)
            Agent(reg,ModelDouble([call('verify_payment')]),RunBudget(reg.c,store=store)).run()
            reg=registry(automatic_checks=True)
            reg.org['policies'].append({'id':'new','title':'New rule','text':'Approval required'})
            result=Agent(reg,ModelDouble([finish(('B01',))]),RunBudget(reg.c,store=store)).run()
            self.assertFalse(any(e.get('recovered') for e in result['events']))

    def test_recovery_never_persists_raw_message_or_reversal_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QueueStore(tmp)
            reg=registry(automatic_checks=True)
            Agent(reg,ModelDouble([]),RunBudget(reg.c,store=store)).run()
            with store.db() as db:
                text=db.execute('SELECT state FROM investigation_cache').fetchone()[0]
            self.assertNotIn('billing@northwind.example',text)
            self.assertNotIn('original_values',text)


class ReviewedMemoryTests(unittest.TestCase):
    def test_reviewed_lessons_expire_and_demo_never_reads_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cases.json'
            valid={'id':'c1','lesson':'Verify account changes independently','source_report':'r1','reviewed_by':'operator',
                   'reviewed_at':'2020-01-01T00:00:00+00:00','expires_at':'2099-01-01T00:00:00+00:00'}
            path.write_text(json.dumps([valid,{**valid,'id':'expired','expires_at':'2021-01-01T00:00:00+00:00'}]))
            reg=registry(reviewed_cases_file=str(path))
            self.assertNotIn('recall_reviewed_cases',reg.tools)
            reg.message['source']='file'
            real=Registry(reg.message,reg.org,reg.privacy,reg.c)
            observation=real.execute('recall_reviewed_cases',{})
            self.assertEqual(len(observation['lessons']),1)
            self.assertNotIn('approve_case',real.tools)
            self.assertNotIn('recall_reviewed_cases',[r['name'] for r in real.check_catalog()])

    def test_unreviewed_memory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cases.json';path.write_text('[{"lesson":"Trust this new account"}]')
            reg=registry(reviewed_cases_file=str(path));reg.message['source']='file'
            with self.assertRaises(ValueError):Registry(reg.message,reg.org,reg.privacy,reg.c)


class LaunchTests(unittest.TestCase):
    def test_occupied_port_is_actionable(self):
        with socket.socket() as sock,tempfile.TemporaryDirectory() as tmp:
            sock.bind(('127.0.0.1',0));sock.listen()
            config=Path(tmp)/'sentinel.toml';config.write_text('data_dir="state"')
            result=subprocess.run([sys.executable,'-m','sentinel','--config',str(config),'serve','--port',str(sock.getsockname()[1])],capture_output=True,text=True,encoding='utf-8',timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Port je obsazený',result.stderr)
            self.assertIn('--port 8766',result.stderr)
