"""Language-independent host routing; model doubles do not measure language accuracy."""
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from sentinel.config import Config
from sentinel.tools import Registry,Tool,schema
from sentinel.privacy import Privacy
from sentinel.agent import Agent
from sentinel.rules import check_status
from test_security import registry,ModelDouble,call,finish


class SemanticPluginTests(unittest.TestCase):
    def evidence(self,reg,name,args):
        return {'id':'E01','tool':name,'status':'ok','arguments':args,'observation':reg.execute(name,args)}

    def test_no_language_controls_whether_a_check_is_required(self):
        for body in ['Bitte überweisen Sie den Betrag.','Prosím, uhraďte sumu.','Proszę przelać należność.','送金してください。','يرجى تحويل المبلغ','Merci de virer la somme.']:
            reg=registry(privacy_mode='redacted_text');reg.message['body']=body
            rows=check_status(reg,[])
            self.assertTrue(next(r for r in rows if r['tool']=='verify_payment')['required'])
            self.assertNotIn('local_signals',reg.execute('inspect_message',{}))

    def test_model_can_waive_only_conditional_checks(self):
        reg=registry(privacy_mode='redacted_text')
        args={'applicable':[],'not_applicable':['verify_payment','search_policy'],'uncertain':[],'reason':'The message is a social greeting, with no requested business action.'}
        rows=check_status(reg,[self.evidence(reg,'assess_applicability',args)])
        self.assertFalse(next(r for r in rows if r['tool']=='verify_payment')['required'])
        self.assertTrue(next(r for r in rows if r['tool']=='inspect_prompt_injection')['required'])
        args['not_applicable'].append('inspect_prompt_injection')
        with self.assertRaises(ValueError):reg.execute('assess_applicability',args)

    def test_withheld_or_truncated_text_cannot_waive_semantic_checks(self):
        for privacy,truncated in [('evidence_only',False),('redacted_text',True)]:
            reg=registry(privacy_mode=privacy);reg.message['body_truncated']=truncated
            args={'applicable':[],'not_applicable':['verify_payment','search_policy'],'uncertain':[],'reason':'No relevant request.'}
            result=self.evidence(reg,'assess_applicability',args)
            self.assertEqual(result['observation']['not_applicable'],[])
            self.assertTrue(next(r for r in check_status(reg,[result]) if r['tool']=='verify_payment')['required'])

    def test_scope_assessment_must_cover_every_conditional_check(self):
        reg=registry(privacy_mode='redacted_text')
        with self.assertRaises(ValueError):reg.execute('assess_applicability',{'applicable':['verify_payment'],'not_applicable':[],'uncertain':[],'reason':'Payment requested'})

    def test_custom_plugin_controls_its_own_completion(self):
        reg=registry()
        reg.add(Tool('verify_contract','Check contract approval',schema(),lambda:{'approved':False},default_mode='required',available=lambda result:result['approved']))
        e=self.evidence(reg,'verify_contract',{})
        row=next(r for r in check_status(reg,[e]) if r['tool']=='verify_contract')
        self.assertEqual(row['state'],'unverifiable')
        self.assertEqual(next(r for r in reg.check_catalog() if r['name']=='verify_contract')['mode'],'required')

    def test_custom_plugin_blocker_prevents_low_risk(self):
        reg=registry()
        reg.add(Tool('verify_contract','Check contract approval',schema(),lambda:{},blockers=lambda result:['Contract suspended']))
        result=Agent(reg,ModelDouble([call('verify_contract'),finish(verdict='LOW_RISK')])).run()
        self.assertIn('Contract suspended',result['report']['uncertainties'])

    def test_policy_retrieval_does_not_filter_by_language_or_fixed_topic(self):
        reg=registry();reg.org['policies']=[{'id':'采购','title':'採購審批','text':'付款前必須審批。'}]
        result=reg.execute('search_policy',{'topic':'beliebiges Thema'})
        self.assertEqual(result['policies'][0]['id'],'采购')

    def test_admin_rules_reach_the_model_separately_from_mail(self):
        reg=registry(privacy_mode='redacted_text');reg.c.organization_rules='Require an approved case number before releasing customer data.'
        class Model(ModelDouble):
            def decide(self,system,context,tools):
                self.system=system
                return super().decide(system,context,tools)
        model=Model([call('inspect_message'),finish()]);Agent(reg,model).run()
        self.assertIn(reg.c.organization_rules,model.system)
        self.assertIsInstance(model.contexts[0]['check_rules'],list)

    def test_dynamic_config_accepts_plugin_check_names(self):
        config=Config(check_modes={'inspect_message':'required','verify_contract':'conditional'})
        config.validate()
        with self.assertRaises(ValueError):Config(check_modes={'inspect_message':'off'}).validate()
