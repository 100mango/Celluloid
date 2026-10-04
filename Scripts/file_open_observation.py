"""Read only the exact unclassified file-open messages on one owned simulator.

Sender-image metadata is diagnostic evidence, never an automatic exemption.
"""
import json
MESSAGE='fopen failed for data file: errno = 2 (No such file or directory)'
FIELDS={'timestamp','processImagePath','processID','senderImagePath','senderImageUUID','subsystem','category','eventMessage','messageType','threadID'}

def capture(run,udid,source,binary_sha):
    report={'source_sha':source,'device_id':udid,'installed_binary_sha256':binary_sha,'message':MESSAGE,
            'classified':False,'acceptance':False,'scope':'Exact synthetic consumer diagnostic only; sender ownership alone does not excuse this failure.'}
    try:
        result=run(['xcrun','simctl','spawn',udid,'log','show','--last','5m','--style','json',
            '--predicate','process == "Celluloid" AND eventMessage == "'+MESSAGE+'"'],timeout=20,check=False,echo=False)
        report['exit_code']=result.returncode
        if result.returncode!=0:raise ValueError('Owned-device log query did not succeed')
        if len(result.stdout.encode())>100_000:raise ValueError('Filtered log output exceeded diagnostic bound')
        values=json.loads(result.stdout)
        if not isinstance(values,list) or len(values)>12:raise ValueError('Unexpected filtered log result count')
        rows=[]
        for value in values:
            if not isinstance(value,dict) or value.get('eventMessage')!=MESSAGE:raise ValueError('Filtered query returned another message')
            if not str(value.get('processImagePath','')).endswith('/Celluloid.app/Celluloid'):raise ValueError('Filtered query returned another process')
            rows.append({k:value[k] for k in FIELDS if k in value})
        report['records']=rows;report['observed_records_available']=bool(rows)
        if not rows:report['unavailable_reason']='Exact message has no observable unified-log records'
    except Exception as error:
        report['observed_records_available']=False;report['unavailable_reason']=type(error).__name__+': '+str(error)
    if len(json.dumps(report).encode())>20_000:
        report.pop('records',None);report['observed_records_available']=False;report['unavailable_reason']='Selected metadata exceeded20KB bound'
    return report
