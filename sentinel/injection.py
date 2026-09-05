"""Bounded local prompt-injection indicators. No absence-of-attack guarantee."""
import re
import unicodedata

PATTERNS = {
 'instruction_override': r'ignore.{0,35}(previous|prior|above|instructions)|disregard.{0,35}instructions|ignoruj.{0,35}(předchozí|instrukce|pokyny)|zapomeň.{0,35}(pokyny|instrukce)',
 'role_spoofing': r'(^|\n)\s*(system|developer|assistant|systém|vývojář)\s*:|<\|(?:im_start|system|assistant)|\[/?INST\]',
 'forced_verdict': r'(return|output|finish|výsledek|vrať|označ).{0,65}(LOW_RISK|safe|bezpečn|nízké riziko)|skip.{0,30}(verification|checks)|neověřuj',
 'data_export': r'(export|send|upload|odešli|pošli|nahraj).{0,65}(database|credentials|password|api.key|databáz|hesl|klíč)',
 'tool_directive': r'(call|execute|run|zavolej|spusť).{0,35}(finish_investigation|shell|bash|powershell|update_vendor)',
}


def inspect_injection(message, privacy_mode):
    fields=[('subject',message.get('subject','')),('body',message.get('body',''))]
    fields += [(f'attachment-{i+1}',a.get('filename','')) for i,a in enumerate(message.get('attachments',[]))]
    findings=[]
    for location,text in fields:
        normalized=unicodedata.normalize('NFKC',text)
        normalized=''.join(c for c in normalized if unicodedata.category(c)!='Cf')
        for kind,pattern in PATTERNS.items():
            match=re.search(pattern,normalized,re.I)
            if match:
                item={'location':location,'indicator':kind}
                if privacy_mode=='redacted_text':
                    item['excerpt']=normalized[max(0,match.start()-25):min(len(normalized),match.end()+60)]
                findings.append(item)
    return {'findings':findings[:50],'indicator_found':bool(findings),'method':'local_patterns',
            'scope':['subject','parsed_body','attachment_names'],
            'content_truncated':bool(message.get('body_truncated')),
            'limitations':'Unknown, encoded or indirect instructions may be missed. Attachment contents are not scanned. No known pattern found does not mean no injection.'}
