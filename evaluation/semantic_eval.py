"""Live multilingual acceptance run. No simulated provider or fallback results."""
import argparse
import dataclasses
import json
import platform
import time
from pathlib import Path
from sentinel.agent import Agent
from sentinel.config import load_config
from sentinel.tools import Registry,demo_messages,demo_dataset,redaction_terms
from sentinel.privacy import Privacy

CASES=[
 ('de_payment','Bitte überweisen Sie den offenen Betrag für den Vorgang.',True),
 ('sk_payment','Prosím, uhraďte dlžnú sumu na uvedený bankový účet.',True),
 ('pl_payment','Proszę przelać należność na wskazany rachunek bankowy.',True),
 ('fr_payment','Veuillez effectuer le virement du montant restant.',True),
 ('ja_payment','未払いの金額を指定の口座に送金してください。',True),
 ('ar_payment','يرجى تحويل المبلغ المستحق إلى الحساب المحدد.',True),
 ('de_greeting','Vielen Dank für das nette Gespräch. Ich wünsche Ihnen ein schönes Wochenende.',False),
 ('sk_greeting','Ďakujem za stretnutie. Prajem príjemný víkend.',False),
 ('pl_greeting','Dziękuję za spotkanie. Życzę miłego weekendu.',False)
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='sentinel.toml')
    parser.add_argument('--allow-external',action='store_true')
    parser.add_argument('--output',default='semantic-evaluation.json')
    parser.add_argument('--case', action='append', choices=[c[0] for c in CASES], help='Run selected cases; repeat to select more than one')
    args=parser.parse_args();config=load_config(args.config)
    if not config.model:parser.error('Configure a real model first')
    if config.external and not (config.allow_external and args.allow_external):parser.error('External evaluation needs --allow-external and saved external-processing authorization')
    # Controlled synthetic evidence, no organization databases or private policies.
    cfg=dataclasses.replace(config,privacy_mode='redacted_text',plugins=[],data_sources_file='',organization_rules='',enabled_skills=[],enable_specialists=False,check_modes={})
    outcomes=[]
    output={'provider':cfg.provider,'model':cfg.model,'python':platform.python_version(),'platform':platform.platform(),
            'started_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':outcomes,
            'note':'Synthetic multilingual acceptance cases. This is not a security certification or a general detection-accuracy estimate.'}
    selected=[c for c in CASES if not args.case or c[0] in args.case]
    output['selected_cases']=[c[0] for c in selected]
    def checkpoint():
        target=Path(args.output)
        temporary=target.with_suffix(target.suffix+'.tmp')
        temporary.write_text(json.dumps(output,ensure_ascii=False,indent=2),'utf-8')
        temporary.replace(target)
    checkpoint()
    for ident,text,expected in selected:
        started=time.monotonic()
        message=demo_messages()[0]
        message.update(id=ident,subject='',body=text,urls=[],attachments=[])
        org=demo_dataset();reg=Registry(message,org,Privacy(redaction_terms(org,cfg)),dataclasses.replace(cfg))
        result=Agent(reg).run()
        report=result.get('report') or {}
        row=next((r for r in report.get('check_status',[]) if r['tool']=='verify_payment'),None)
        observed=None if row is None else row['required']
        outcomes.append({'case':ident,'expected_applicable':expected,'observed_applicable':observed,'matches_expectation':result['status']=='completed' and observed is expected,'status':result['status'],'elapsed_seconds':round(time.monotonic()-started,2),'report':report})
        checkpoint()
        print(ident,result['status'],'applicable='+str(observed),flush=True)
    output['completed']=True
    checkpoint()
    return 0 if all(row['matches_expectation'] for row in outcomes) else 1

if __name__=='__main__':raise SystemExit(main())
