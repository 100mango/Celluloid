"""Pure validation of one UITestRunner-owned temporary display configuration."""
import hashlib
import math
from mac_store_io import strict_json

LIMIT = 16 * 1024
MODE_FIELDS = {'id','width','height','pixelWidth','pixelHeight','usable'}


def need(ok, reason):
    if not ok: raise ValueError(reason)


def number(value): return type(value) in (int,float) and math.isfinite(value)
def integer(value, low=0, high=2**32-1): return type(value) is int and low <= value <= high
def digest(value): return hashlib.sha256(value).hexdigest()


def mode(value):
    need(isinstance(value,dict) and set(value)==MODE_FIELDS and integer(value['id'],-2**31,2**31-1) and
        all(integer(value[k],1,32768) for k in ('width','height','pixelWidth','pixelHeight')) and
        type(value['usable']) is bool,'display-mode-fields')
    return value


def rect(value):
    need(isinstance(value,list) and len(value)==4 and all(number(x) and abs(x)<=32768 for x in value) and
        value[2]>0 and value[3]>0,'display-rectangle')
    return value


def snapshot(value, display):
    need(isinstance(value,dict) and set(value)=={'display','mode','frame','visibleFrame','cgBounds','scale'} and
        value['display']==display and integer(display,1),'display-snapshot-fields')
    m=mode(value['mode']);frame=rect(value['frame']);visible=rect(value['visibleFrame']);bounds=rect(value['cgBounds']);scale=value['scale']
    need(number(scale) and 0<scale<=4 and abs(m['pixelWidth']-m['width']*scale)<.5 and
        abs(m['pixelHeight']-m['height']*scale)<.5 and
        all(abs(a-b)<.5 for a,b in zip(frame,[0,0,m['width'],m['height']])) and
        all(abs(a-b)<.5 for a,b in zip(bounds,frame)),'display-mode-screen-scale-mismatch')
    need(visible[0]>=-.5 and visible[1]>=-.5 and visible[0]+visible[2]<=frame[2]+.5 and
        visible[1]+visible[3]<=frame[3]+.5,'display-visible-frame-outside-screen')
    return value


def fixed_mode(value):
    return value['usable'] and all(value[k]==v for k,v in
        {'width':1280,'height':960,'pixelWidth':1280,'pixelHeight':960}.items())


def fits(value):
    return (fixed_mode(value['mode']) and value['scale']==1 and
        value['visibleFrame'][2]>=1280 and value['visibleFrame'][3]>=800)


def choose(before, available):
    if fits(before):return before['mode']
    choices=[]
    for candidate in available:
        mode(candidate)
        if fixed_mode(candidate):choices.append(candidate)
    need(bool(choices),'no-supported-mode-fits-window')
    return min(choices,key=lambda x:x['id'])


def validate(setup_raw, restore_raw, summary):
    need(len(setup_raw)<=LIMIT and (restore_raw is None or len(restore_raw)<=LIMIT),'display-receipt-byte-limit')
    a=strict_json(setup_raw);b=None if restore_raw is None else strict_json(restore_raw)
    fields={'v','test','token','runnerPID','display','started','scope','requestedWindowPoints','changed','status',
        'activeDisplays','before','availableModeCount','availableModes','selected','configurationResult','after','finished'}
    need(isinstance(a,dict) and set(a)==fields and type(a['v']) is int and a['v']==1 and
        a['status']=='ready' and a['scope']=='forAppOnly' and a['requestedWindowPoints']==[1280,800] and
        type(a['changed']) is bool and integer(a['runnerPID'],1) and a['activeDisplays']==[a['display']] and
        type(a['configurationResult']) is int and a['configurationResult']==0,'display-setup-fields')
    before=snapshot(a['before'],a['display']);after=snapshot(a['after'],a['display'])
    modes=a['availableModes'];need(isinstance(modes,list) and 1<=len(modes)<=128 and
        type(a['availableModeCount']) is int and a['availableModeCount']==len(modes),'display-catalogue-bound')
    for value in modes:mode(value)
    selected=choose(before,modes)
    need(a['selected']==selected and selected in modes and after['mode']==selected and fits(after) and
        a['changed']==(not fits(before)),'display-selection-or-fit')
    need(all(number(a[k]) for k in ('started','finished')) and
        summary['startTime']<=a['started']<=a['finished']<=summary['finishTime'],'display-setup-clock')
    cleanup='unconfirmed'
    if b is not None:
        fields={'v','test','runnerPID','display','scope','started','finished','setupSHA256','changed','configurationResult','original','after','restored'}
        need(isinstance(b,dict) and set(b)==fields and type(b['v']) is int and b['v']==1 and
            b['scope']=='forAppOnly' and type(b['restored']) is bool and type(b['configurationResult']) is int and
            b['changed']==a['changed'] and b['test']==a['test'] and b['display']==a['display'] and b['runnerPID']==a['runnerPID'] and
            b['setupSHA256']==digest(setup_raw) and b['original']==before['mode'],'display-restore-fields')
        # An unconfirmed restore may observe CGDisplay and NSScreen mid-transition.
        # Keep that bounded raw observation without invalidating earlier capture proof.
        restored=snapshot(b['after'],a['display']) if b['restored'] and b['after'] else None
        observed=restored is not None and restored['mode']==before['mode'] and restored['scale']==before['scale']
        need(not b['restored'] or (b['configurationResult']==0 and observed),'contradictory-display-restoration')
        if b['restored']:cleanup='restored'
        need(all(number(b[k]) for k in ('started','finished')) and
            a['finished']<b['started']<=b['finished']<=summary['finishTime'],'display-restore-clock')
    frame=after['frame'];visible=after['visibleFrame']
    return {'setup':a,'restore':b,'setupText':setup_raw.decode('utf-8'),'restoreText':None if restore_raw is None else restore_raw.decode('utf-8'),
        'setupSHA256':digest(setup_raw),'restoreSHA256':None if restore_raw is None else digest(restore_raw),'scale':after['scale'],
        'cleanupStatus':cleanup,'automaticResetScope':'forAppOnly caller lifetime; exit/reset not independently observed here',
        'visibleFrameAX':[visible[0],frame[1]+frame[3]-visible[1]-visible[3],visible[2],visible[3]]}
