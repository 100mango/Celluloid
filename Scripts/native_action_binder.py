"""Strict binder for real official XCTest Session activity/touch records.

Only reads exported native diagnostics. No SQLite/storage scraping, synthesized
native records, timing repair, or acceptance from the offline model is allowed.
Unknown log format is EvidenceError, not an alternate guessed path.
"""
from __future__ import annotations
from datetime import timezone
import importlib.util
import hashlib
from pathlib import Path
import re

BASE_PATH=Path(__file__).with_name('picker_native_receipt.py')
if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()!='77da47eec5392c93c972246a2699b1c057501c409dad9ca47c68e60ad072e2e6':
    raise RuntimeError('Existing reviewed receipt dependency hash mismatch')
spec=importlib.util.spec_from_file_location('early_cancel_existing_receipt',BASE_PATH)
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
require,one,EvidenceError=base.require,base.one,base.EvidenceError

PREFIX=re.compile(r'^(?:(?P<day>\d{4}-\d{2}-\d{2}) )?(?P<clock>\d{2}:\d{2}:\d{2}\.\d{3,6})(?P<zone>[+-]\d{4})? (?P<process>[\w.-]+)\[(?P<pid>\d+):(?P<thread>\d+)\](?: \[[^\]]*\])? (?P<body>.*)$')
ACTIVITY=re.compile(r'<XCTContext: (?P<context>0x[0-9a-fA-F]+)> (?P<state>started|finished) activity <XCActivityRecord: (?P<object>0x[0-9a-fA-F]+)> \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}: (?P<title>.*)$')

class Session:
    def __init__(self,path,content,near,runner_pid,logs=None,uncertainty=0.001):
        self.path,self.content,self.lines,self.runner_pid=path,content,content.splitlines(),str(runner_pid)
        self.logs=logs or {path:content}; self.uncertainty=uncertainty
        self.records=[]; self.activities=[]; stacks={}
        for index,line in enumerate(self.lines):
            m=PREFIX.match(line)
            if not m or not m['process'].endswith('UITests-Runner') or m['pid']!=self.runner_pid: continue
            r=m.groupdict(); r.update(line=index+1,wall=base.prefix_wall(r,near,timezone.utc))
            self.records.append(r)
            a=ACTIVITY.fullmatch(r['body'])
            if not a: continue
            key=(r['thread'],a['context']); stack=stacks.setdefault(key,[])
            if a['state']=='started':
                activity=dict(a.groupdict(),line=index+1,wall=r['wall'],thread=r['thread'],parent=stack[-1] if stack else None)
                self.activities.append(activity);stack.append(activity)
            else:
                title=re.sub(r' \([0-9.]+s\)$','',a['title'])
                require(stack and stack[-1]['object']==a['object'] and stack[-1]['title']==title,
                        f'Unmatched/out-of-order native activity {path}:{index+1}')
                top=stack.pop();top.update(end_line=index+1,end_wall=r['wall'])
        require(all(not stack for stack in stacks.values()),'Unclosed native activity')
        for a in self.activities:
            require(a['wall']<=a['end_wall'],'Native activity ends before start')
            if a['parent']:
                require(a['parent']['wall']<=a['wall']<=a['end_wall']<=a['parent']['end_wall'],'Native child clock outside parent')
    def text(self,a):return '\n'.join(self.lines[a['line']-1:a['end_line']])
    def records_in(self,a):return [r for r in self.records if a['line']<=r['line']<=a['end_line'] and r['thread']==a['thread']]
    def loc(self,r):return {'file':self.path,'line':r['line']}
    def find(self,title,lo,hi):
        return one([a for a in self.activities if a['title']==title and lo<=a['wall']<=a['end_wall']<=hi],title+' native window')


def single_record(records,pattern,description):
    found=[(r,re.fullmatch(pattern,r['body'])) for r in records]
    return one([(r,m) for r,m in found if m],description)


def bind_tap(session,tap,*,label,app_pid):
    """Bind one tap, one Synthesize child, actual target/hit point and waiter."""
    s=one([a for a in session.activities if a['title']=='Synthesize event' and a['parent'] is tap], 'Synthesize direct Tap child')
    records=session.records_in(s); text=session.text(s)
    # The target may occur again for other attribute faults; activationPoint
    # identifies the relevant block uniquely, including its real AX identity.
    targets=[]
    for r in records:
        m=re.fullmatch(r"Button, (?P<description>.*?) \(AX element pid: (?P<pid>\d+), elementOrHash.elementID: (?P<ax>[\d.]+)\) faulted in \{",r['body'])
        if not m:continue
        tail='\n'.join(session.lines[r['line']-1:min(r['line']+12,s['end_line'])])
        if '}: (no error) for activationPoint using XC_kAXXCAttributeVisiblePoint' in tail:
            targets.append((r,m))
    target,tm=one(targets,'native activation-point target')
    wanted=f"identifier: '{label}'" if label=='edit-photo' else "label: 'Cancel'"
    require(wanted in tm['description'],'Wrong actual tapped target')
    computing,cm=single_record(records,r'Computing hit point for Button, (?P<description>.*)', 'native hit-point target computation')
    require(wanted in cm['description'],'Hit-point computation targets a different control')
    hit,hm=single_record(records,r'Computed hit point \{(?P<x>-?[0-9.]+), (?P<y>-?[0-9.]+)\} \(hittable\)','successful real hit point')
    require(float(hm['x'])>=0 and float(hm['y'])>=0,'Negative hit point')
    dispatch,dm=single_record(records,r'Requesting local synthesis of event: ?','actual touch dispatch')
    require(target['line']<hit['line']<dispatch['line'],'Hit point/dispatch ordering')
    tail=[]
    for line in session.lines[dispatch['line']:]:
        if PREFIX.match(line):break
        tail.append(line)
    require(len(tail)==4 and re.fullmatch(r"<XCSynthesizedEventRecord 'tap display [0-9]+'>",tail[0]) and tail[1]=='Path 1:', 'Not exactly one tap touch path')
    display=re.fullmatch(r"<XCSynthesizedEventRecord 'tap display ([0-9]+)'>",tail[0])[1]
    display_ids=[]
    for row in session.records_in(tap):
        if row['line']>=dispatch['line']:continue
        if re.fullmatch(r"Button, .*\(AX element pid: "+tm['pid']+r", elementOrHash.elementID: "+re.escape(tm['ax'])+r"\) faulted in \{",row['body']):
            block=[]
            for line in session.lines[row['line']:]:
                if PREFIX.match(line):break
                block.append(line)
                if line.startswith('}:'):break
            raw='\n'.join(block)
            if '}: (no error) for frame using ' in raw:
                display_ids+=re.findall(r'"XC_kAXXCAttributeWindowDisplayId" = ([0-9]+);',raw)
    require(display_ids and set(display_ids)=={display},'Tap dispatch display differs from exact target frame/window')
    down=re.fullmatch(r'\s*Touch down at (-?[0-9.]+), (-?[0-9.]+), offset=0\.00s',tail[2])
    up=re.fullmatch(r'\s*Touch up at (-?[0-9.]+), (-?[0-9.]+), offset=0\.05s',tail[3])
    require(down and up and down.groups()==up.groups(),'Invalid touch down/up pair')
    require(abs(float(down[1])-float(hm['x']))<=0.1 and abs(float(down[2])-float(hm['y']))<=0.1,'Touch does not target computed hittable point')
    wait,wm=single_record(records,r'<XCTWaiter: (?P<waiter>0x[0-9a-fA-F]+)> entering wait loop for [0-9.]+s with expectations: `synthesizing event`','synthesis waiter')
    successes=[r for r in records if r['body']==f"Returning result XCTWaiterResultCompleted for synchronous waiter <XCTWaiter: {wm['waiter']}>" and r['line']>wait['line']]
    success=one(successes,'matching synthesis waiter success')
    require(dispatch['line']<wait['line']<success['line']<s['end_line'],'Synthesis completion order')
    ordered_times=[s['wall'],computing['wall'],target['wall'],hit['wall'],dispatch['wall'],wait['wall'],success['wall'],s['end_wall']]
    require(all(a<=b for a,b in zip(ordered_times,ordered_times[1:])),'Native input timestamps contradict action order')
    uuids=[]
    for name in ('kXCTAttachmentLegacySnapshot','kXCTAttachmentLegacySynthesizedEvent'):
        r,m=single_record(records,rf"Activity (?P<uuid>[0-9A-F-]{{36}}) added attachment with name '{name}', .*", name+' activity UUID')
        uuids.append(base.identifier(m['uuid'],'native activity UUID'))
    require(uuids[0]==uuids[1],'Snapshot/touch activity UUID mismatch')
    all_inputs=[a for a in session.activities if a['title']=='Synthesize event' and tap['line']<=a['line']<=a['end_line']<=tap['end_line']]
    require(all_inputs==[s],'Extra/competing synthesized input in Tap')
    require(not re.search(r'AXErrorInvalidUIElement|AXErrorCannotComplete|invalid AX element',session.text(tap),re.I),'Invalid/stale AX target during tap')
    target_evidence=bind_target(session,tap,tm,app_pid,label,dispatch['wall'])
    return dict(activity_uuid=uuids[0],synthesis_start=s['wall'],synthesis_completed=s['end_wall'],
                dispatch=dispatch['wall'],waiter_completed=success['wall'],tap_start=tap['wall'],tap_end=tap['end_wall'],
                target_pid=int(tm['pid']),target_ax_id=tm['ax'],target_evidence=target_evidence,
                thread=s['thread'],evidence={'tap':session.loc(tap),'synthesis':session.loc(s),'target':session.loc(target),'hit':session.loc(hit),'dispatch':session.loc(dispatch),'success':session.loc(success)})


def bind_target(session,tap,target,app_pid,label,dispatch_wall):
    text=session.text(tap)
    if label=='edit-photo':
        require(target['pid']==str(app_pid),'Opening target outside app PID')
        require("identifier: 'edit-photo'" in target['description'],'Opening target identity missing')
        return {'kind':'app_edit_photo','source':'actual target record'}
    # Exact singleton resolution and ancestor tree must be inside this Tap,
    # not borrowed from an earlier preflight property read.
    candidates=[a for a in session.activities if a['title'] in ('Find the "Cancel" Button','Find the Button') and a['parent'] is tap]
    require(candidates,'No native target-resolution child')
    finds=[]
    for a in candidates:
        block=session.text(a)
        matches=re.findall(r'(?:matches:|found) \{\(\n(.*?)\n\)\}',block,re.S)
        for match in matches:
            rows=[line.strip() for line in match.splitlines() if line.strip()]
            if len(rows)==1 and rows[0].startswith('Button,') and ("label: 'Cancel'" in rows[0] or "identifier: 'Cancel'" in rows[0]):finds.append(a)
    find=one(finds,'singleton Cancel resolution')
    block=session.text(find)
    if target['pid']==str(app_pid):
        tree,tree_evidence=loading_query_tree(session,find,target,app_pid)
        ancestry=target_ancestry(tree,target,app_pid)
        require(any("NavigationBar," in a and "identifier: 'PUPickerUnavailableView'" in a for a in ancestry),'Loading Cancel not in system-loading nav subtree')
        kind='system_loading_cancel'
    else:
        trees=current_trees(block)
        tree=one(trees,'complete Current tree in remote Find')
        ancestry=target_ancestry(tree,target,app_pid)
        require(any("NavigationBar," in a and "identifier: 'Photos'" in a for a in ancestry),'Remote Cancel outside Photos navigation subtree')
        placeholders=re.findall(r'RemotePlaceholder, pid: (\d+)',block)
        require(placeholders and set(placeholders)=={target['pid']},'Ambiguous/wrong remote placeholder PID')
        roots=re.findall(r'Fetching snapshot for AX element pid: (\d+), elementOrHash.elementID: ([\d.]+) from testmanagerd',block)
        remote_pid,host_id=one(roots,'remote snapshot root request')
        require(remote_pid==target['pid'],'Snapshot root PID differs from actual target')
        lineage=list(reversed(ancestry))+[one([row for row in tree if f"<AX element pid: {target['pid']}, elementOrHash.elementID: {target['ax']}>" in row],'target tree identity')]
        nodes=[(row,re.search(r'<AX element pid: (\d+), elementOrHash.elementID: ([\d.]+)>',row)) for row in lineage]
        nodes=[(row,m) for row,m in nodes if m]
        boundary=one([(nodes[k-1],nodes[k]) for k in range(1,len(nodes)) if nodes[k-1][1][1]==str(app_pid) and nodes[k][1][1]==target['pid']],'actual app-to-remote PID boundary')
        require(boundary[0][1][2]==host_id,'Remote snapshot root is not the immediate app-side host bridge')
        kinds=[]
        for a in reversed(ancestry):
            m=re.search(r'<AX element pid: (\d+),',a)
            if m and (not kinds or kinds[-1]!=m[1]):kinds.append(m[1])
        require(kinds==[str(app_pid),target['pid']],'Broken/multiple PID transitions in remote host chain')
        tree_evidence=session.loc(find)
        kind='system_remote_cancel'
    controller='PUPickerUnavailableViewController' if kind=='system_loading_cancel' else 'PUPickerRemoteViewController'
    lifecycle=[]
    for m in base.NATIVE.finditer(session.content):
        if m['app_pid']!=str(app_pid) or not re.search(r'^\s+controllerClass = '+controller+r';$',m['body'],re.M):continue
        p=base.prefix_info(m['prefix'])
        require(p and p['pid']==session.runner_pid and p['process'].endswith('UITests-Runner'),'Wrong system controller event origin')
        wall=base.prefix_wall(p,tap['wall'],timezone.utc)
        if wall<=dispatch_wall:
            event=one(re.findall(r'^\s+event = (\w+);$',m['body'],re.M),'controller lifecycle event')
            lifecycle.append((wall,event))
    require(lifecycle and max(lifecycle)[1]=='ViewDidAppear','Actual system controller is not active through Cancel dispatch')
    require('No alerts or notifications found for Target Application \'Mango.Celluloid\'' in text,'No fail-closed interrupting UI check')
    return {'kind':kind,'query_evidence':session.loc(find),'tree_evidence':tree_evidence,'identity_limit':'Observed system hierarchy plus source-reviewed unique PHPicker presentation; no private API calls'}


def parse_candidate_traces(logs):
    old=base.MARKER
    try:
        base.MARKER=re.compile(r'\b(PICKER_APP_TRACE|PICKER_CANCEL_CYCLE_UI) (?P<fields>.*)$')
        return base.parse_logs(logs)
    finally:base.MARKER=old


def bind_fresh_home(session,observation,app_pid,runner_thread,uncertainty):
    require(all(observation.get(k)==v for k,v in {'home_exists':'true','home_enabled':'true','home_hittable':'true','picker_exists':'false'}.items()),'Fresh home booleans not established')
    start=base.number(observation.get('query_started_uptime'),'query start uptime')
    require(start<=observation['uptime'],'Home query begins after it ends')
    wall_start=observation['wall']-(observation['uptime']-start)
    # Same-runner prefix milliseconds may be truncated. Widen only the log
    # association window by 1ms; never the acceptance deadline or causality.
    candidates=[a for a in session.activities if a['thread']==runner_thread and wall_start-0.001<=a['wall']<=a['end_wall']<=observation['wall']+0.001]
    exists=one([a for a in candidates if a['title']=='Checking existence of `"edit-photo" Button`'],'fresh home existence action')
    require("Button, identifier: 'edit-photo'" in session.text(exists) and 'matches: {(' in session.text(exists),'Home existence lacks actual positive resolution')
    absent=one([a for a in candidates if a['title'] in ('Checking existence of `"Cancel" Button`','Checking existence of `Button`')],'fresh Cancel absence action')
    absent_text=session.text(absent)
    require('no matches found' in absent_text and 'matches: {(' not in absent_text and 'found {(' not in absent_text and 'RemotePlaceholder' not in absent_text,'Cancel absence is ambiguous or remote unresolved')
    local=[r for r in session.records if r['thread']==runner_thread and wall_start-0.001<=r['wall']<=observation['wall']+0.001]
    computing,cm=single_record(local,r"Computing hit point for Button, .*identifier: 'edit-photo'.*",'fresh home hittable query')
    hit,hm=single_record(local,r'Computed hit point \{(?P<x>-?[0-9.]+), (?P<y>-?[0-9.]+)\} \(hittable\)','fresh home hit point success')
    require(float(hm['x'])>=0 and float(hm['y'])>=0 and computing['line']<hit['line']<absent['line'],'Fresh home hit/absence order')
    require(f'Application, pid: {app_pid}' in session.text(exists),'Fresh home wrong application')
    return {'start_wall':wall_start,'end_wall':observation['wall'],'exists':session.loc(exists),'hittable':session.loc(hit),'picker_absent':session.loc(absent),'marker':observation['source_locations']}


def validate_early_logs(logs,expected_run):
    """A native-evidence receipt only. CLI must additionally bind actual files."""
    expected_run=base.identifier(expected_run,'expected run')
    traces,native,_=parse_candidate_traces(logs)
    require(traces and {r['run'] for r in traces}=={expected_run},'Wrong/multiple trace run')
    app=[r for r in traces if r['kind']=='PICKER_APP_TRACE'];ui=[r for r in traces if r['kind']=='PICKER_CANCEL_CYCLE_UI']
    begin,end=base.event(ui,'run-begin'),base.event(ui,'run-end')
    require(all(r['prefix'] and r['prefix']['process']=='Celluloid' and r['prefix']['pid']==r['pid'] for r in app),'App trace native process prefix mismatch')
    require(all(r['prefix'] and r['prefix']['process'].endswith('UITests-Runner') for r in ui),'UI trace native runner prefix missing')
    require(begin['uptime']<end['uptime'] and begin['wall']<end['wall'],'Run anchor order')
    require(all(begin['uptime']<=r['uptime']<=end['uptime'] and begin['wall']<=r['wall']<=end['wall'] for r in traces),'Trace outside run anchors')
    offsets=[r['wall']-r['uptime'] for r in traces]
    drift=max(offsets)-min(offsets);require(drift<=base.CLOCK_TOLERANCE,'App/runner drift >50ms')
    anchor_errors=[]
    for anchor in (begin,end):
        p=anchor['prefix'];require(p and p['process'].endswith('UITests-Runner'),'No genuine runner anchor')
        e=abs(base.prefix_wall(p,anchor['wall'],timezone.utc)-anchor['wall']);require(e<=base.CLOCK_TOLERANCE,'Native anchor error >50ms');anchor_errors.append(e)
    runner=begin['prefix']['pid'];require(end['prefix']['pid']==runner,'Runner changed')
    ui_threads=set()
    for r in ui:
        proofs=trace_prefixes(logs,r,'runner',runner)
        ui_threads.update(p['thread'] for p in proofs)
    require(len(ui_threads)==1,'UI command/home marker thread changed')
    for r in app:trace_prefixes(logs,r,'app',r['pid'])
    require(all(r['prefix']['pid']==runner for r in ui),'UI marker borrowed from another runner')
    uncertainty=drift+max(anchor_errors)+0.001
    require(len({r['pid'] for r in app})==1,'App PID changed');pid=app[0]['pid']
    session_candidates=[]
    for path,text in logs.items():
        if re.search(rf'UITests-Runner\[{runner}:\d+\] <XCTContext:',text):session_candidates.append((path,text))
    path,text=one(session_candidates,'original runner Session stream')
    session=Session(path,text,begin['wall'],runner,logs=logs,uncertainty=uncertainty)
    # The official Session must name this selector; new markers do not convert
    # a historic test into a candidate test.
    selector='testStockPickerEarlyCancelCompletesWithinOpeningWindow'
    require(re.search(r'Test Case .*'+selector+r'.*started',text),'Official Session test selector missing')
    starts=sorted([r for r in ui if r.get('event')=='open-command-start'],key=lambda r:r['uptime'])
    require([r['iteration'] for r in starts]==[1,2,3],'Exactly three ordered iterations required')
    require(all(r['iteration'] in (0,1,2,3) for r in ui),'Unexpected UI iteration')
    taps=[r for r in app if r.get('event')=='app-beautify-tap']
    require(len(taps)==3 and len({r['instance'] for r in taps})==3,'Presentation UUID mismatch')
    require({r['instance'] for r in app}=={r['instance'] for r in taps},'Orphan app presentation')
    cycles=[];used_native=set();used_input=set();previous_end=begin['wall']
    def ordered(a,b,description):require(a+uncertainty<=b,description+' has overlapping clock bounds')
    for start in starts:
        i=start['iteration'];local=[r for r in ui if r['iteration']==i]
        returned=base.event(local,'open-command-returned');cancel_start=base.event(local,'cancel-command-start');cancel_return=base.event(local,'cancel-command-returned');observed=base.event(local,'cycle-observed')
        require(previous_end<start['wall']<=returned['wall']<=cancel_start['wall']<=cancel_return['wall']<=observed['wall'],'Overlapping or reordered command windows')
        action=one([r for r in taps if start['uptime']<=r['uptime']<=returned['uptime']],'app action in open window')
        instance=[r for r in app if r['instance']==action['instance']]
        construction=base.event(instance,'picker-construction-returned');delegate=base.event(instance,'picker-cancel-delegate');dismiss=base.event(instance,'root-cover-dismissal-completed')
        require(not any(r.get('event') in ('picker-selection-delegate','picker-duplicate-finish-ignored') for r in instance),'Wrong/duplicate callback')
        pointers={r['picker'].lower() for r in instance if r['picker']!='none'}
        require(len(pointers)==1 and construction['picker']!='none' and delegate['picker']==construction['picker'],'Bound coordinator pointer mismatch')
        outer_open=session.find(f'EARLY_CANCEL_OPEN_{expected_run.upper()}_{i}',start['wall']-0.001,returned['wall']+0.001)
        outer_cancel=session.find(f'EARLY_CANCEL_NATIVE_TAP_{expected_run.upper()}_{i}',cancel_start['wall']-0.001,cancel_return['wall']+0.001)
        open_tap=one([a for a in session.activities if a['parent'] is outer_open and a['title']=='Tap "edit-photo" Button'],'opening Tap child')
        cancel_tap=one([a for a in session.activities if a['parent'] is outer_cancel and a['title'] in ('Tap "Cancel" Button','Tap Button')],'Cancel Tap child')
        opened=bind_tap(session,open_tap,label='edit-photo',app_pid=pid);cancelled=bind_tap(session,cancel_tap,label='Cancel',app_pid=pid)
        require(opened['thread']==cancelled['thread'] and {opened['thread']}==ui_threads,'Native input/UI marker thread changed')
        for inp in (opened,cancelled):
            require(inp['activity_uuid'] not in used_input,'Input event reused');used_input.add(inp['activity_uuid'])
        ordered(opened['dispatch'],action['wall'],'open dispatch -> app action')
        require(action['uptime']<=construction['uptime']<=delegate['uptime']<=dismiss['uptime'],'App lifecycle order')
        ordered(cancelled['dispatch'],delegate['wall'],'Cancel dispatch -> delegate')
        candidates=[]
        for idx,n in enumerate(native):
            if n['pid']!=pid or n['prefix']['pid']!=runner:continue
            wall=base.prefix_wall(n['prefix'],action['wall'],timezone.utc)
            if construction['wall']<=wall<=observed['wall']:candidates.append((idx,n,wall))
        appeared=one([x for x in candidates if x[1]['event']=='ViewDidAppear'],'native appearance');disappeared=one([x for x in candidates if x[1]['event']=='ViewDidDisappear'],'native disappearance')
        for idx,n,w in (appeared,disappeared):require(idx not in used_native,'Native lifecycle event reused');used_native.add(idx)
        ordered(construction['wall'],appeared[2],'construction -> native appearance')
        ordered(appeared[2],cancelled['dispatch'],'native appearance -> Cancel dispatch')
        ordered(delegate['wall'],disappeared[2],'delegate -> native disappearance')
        successes=[r for r in local if r.get('event')=='home-observation' and all(r.get(k)==v for k,v in {'home_exists':'true','home_enabled':'true','home_hittable':'true','picker_exists':'false'}.items())]
        require(successes,'No actual home observation');home=min(successes,key=lambda r:r['uptime'])
        fresh=bind_fresh_home(session,home,pid,opened['thread'],uncertainty)
        ordered(dismiss['wall'],fresh['start_wall'],'root dismissal -> fresh query')
        ordered(disappeared[2],fresh['start_wall'],'native disappearance -> fresh query')
        require(cancelled['tap_end']<=fresh['start_wall']+0.001 and home['wall']<=observed['wall'],'Home observation outside post-action window')
        endpoint=max(fresh['end_wall'],cancelled['synthesis_completed'],delegate['wall'],dismiss['wall'],disappeared[2],appeared[2])
        upper=endpoint-opened['synthesis_start']+uncertainty
        cycles.append({'iteration':i,'presentation_id':action['instance'],'open_input':opened,'cancel_input':cancelled,'delegate':delegate['source_locations'],'root_dismiss':dismiss['source_locations'],'native_events':[{'file':n['path'],'line':n['line'],'event':n['event'],'wall':w} for _,n,w in (appeared,disappeared)],'fresh_home':fresh,'open_to_home_upper_seconds':upper,'within_original_three_seconds':upper<=3.0})
        previous_end=observed['wall']
    all_syntheses=[a for a in session.activities if a['title']=='Synthesize event' and begin['wall']<=a['wall']<=end['wall']]
    require(len(all_syntheses)==6,'Unexpected input/gesture within candidate run')
    require(len(used_input)==6 and len(used_native)==6,'Input/lifecycle coverage missing')
    for idx,n in enumerate(native):
        if n['pid']==pid and n['prefix']['pid']==runner and begin['wall']<=base.prefix_wall(n['prefix'],begin['wall'],timezone.utc)<=end['wall']:
            require(idx in used_native,'Orphan native picker lifecycle')
    return {'schema':'celluloid.early-cancel.native-evidence.v1','status':'passed' if all(c['within_original_three_seconds'] for c in cycles) else 'not_accepted','budget_seconds':3.0,'clock_uncertainty_seconds':uncertainty,'runner_pid':int(runner),'app_pid':int(pid),'run_id':expected_run,'run_bounds':{'start_wall':begin['wall'],'end_wall':end['wall']},'cycles':cycles,'scope':'Actual opening input through real Cancel, bound coordinator callback and fresh post-teardown home. Not photo library readiness.','delegate_identity_limit':'Bound coordinator pointer and reviewed source wiring, not independently recorded callback-argument pointer','release_qualification':False,'requires_identity_wrapper':True}


def current_trees(text):
    lines=text.splitlines();result=[]
    for i,line in enumerate(lines):
        p=PREFIX.match(line)
        if not p or p['body']!='Current tree:':continue
        tree=[]
        for following in lines[i+1:]:
            if PREFIX.match(following):break
            tree.append(following)
        require(tree and tree[0].startswith('Application,') and all(row.strip() for row in tree),'Malformed complete tree')
        result.append(tree)
    return result


def target_ancestry(tree,target,app_pid):
    require(re.match(rf'^Application, .*pid: {app_pid}\b',tree[0]),'Tree root does not match app')
    ax=f"<AX element pid: {target['pid']}, elementOrHash.elementID: {target['ax']}>"
    candidates=[(i,row) for i,row in enumerate(tree) if ax in row and re.match(r'\s*Button,',row)]
    index,row=one(candidates,'exact target AX node in complete tree')
    require("label: 'Cancel'" in row or "identifier: 'Cancel'" in row,'Target AX node is not Cancel')
    depth=len(row)-len(row.lstrip());ancestry=[]
    for before in reversed(tree[:index]):
        indent=len(before)-len(before.lstrip())
        if indent<depth:
            ancestry.append(before);depth=indent
    require(ancestry and ancestry[-1]==tree[0],'Target lacks complete app-root ancestry')
    require(not any(re.match(r'\s*(Alert|Sheet),',a) for a in ancestry),'Cancel belongs to alert/sheet')
    return ancestry


def loading_query_tree(session,find,target,app_pid):
    found=[]
    for path,text in session.logs.items():
        lines=text.splitlines();requests=[]
        for i,line in enumerate(lines):
            p=PREFIX.match(line)
            if not p or p['pid']!=str(app_pid) or p['process']!='Celluloid':continue
            body=p['body'];wall=base.prefix_wall(p,find['wall'],timezone.utc)
            if body.startswith('Received request to fetch matches for query:') and find['wall']<=wall<=find['end_wall']:
                requests.append((i,p,wall))
        for i,p,start in requests:
            predicate=lines[i+1].strip() if i+1<len(lines) else ''
            require(predicate in ('↪︎ Elements matching predicate \'"Cancel" IN identifiers\'', '↪︎ Elements matching predicate label == "Cancel"', '↪︎ Elements matching predicate \'label == "Cancel"\''),'Unsupported exact Cancel query predicate')
            replies=[]
            for j in range(i+1,len(lines)):
                q=PREFIX.match(lines[j])
                if not q or q['pid']!=p['pid'] or q['thread']!=p['thread']:continue
                wall=base.prefix_wall(q,start,timezone.utc)
                if wall>find['end_wall']:break
                require(not q['body'].startswith('Received request to fetch matches for query:'),'Overlapping app query requests')
                if q['body'].startswith('Replying to query'):
                    require(j+1<len(lines) and predicate in lines[j+1].strip() and '(error: (null))' in lines[j+1],'Query reply predicate/error mismatch')
                    replies.append((j,wall));break
            j,end=one(replies,'app-side query reply')
            require(find['wall']+session.uncertainty<=start and end+session.uncertainty<=find['end_wall'],'App query not uniquely inside native Find clock bounds')
            block='\n'.join(lines[i:j+2])
            tree=one(current_trees(block),'app-side complete query tree')
            target_ancestry(tree,target,app_pid)
            matches=re.findall(r'found matching snapshots: \{\(\n(.*?)\n\)\} \(error: \(null\)\)',block,re.S)
            match=one(matches,'app query match results')
            require(len([row for row in match.splitlines() if row.strip()])==1 and "label: 'Cancel'" in match,'App query Cancel not singleton')
            found.append((tree,{'file':path,'request_line':i+1,'reply_line':j+1,'start_wall':start,'end_wall':end}))
    return one(found,'official app-side matching Cancel tree')


def inspect_historical_stock(logs):
    """Forensic regression fixture only: bind real old events, never qualify them."""
    traces,native,_=base.parse_logs(logs)
    ui=[r for r in traces if r['kind']=='PICKER_UI_TRACE'];app=[r for r in traces if r['kind']=='PICKER_APP_TRACE']
    begin,end=base.event(ui,'run-begin'),base.event(ui,'run-end')
    runner=begin['prefix']['pid'];pid=one(list({r['pid'] for r in app}),'historical app PID')
    paths=[path for path,content in logs.items() if re.search(rf'UITests-Runner\[{runner}:\d+\] <XCTContext:',content)]
    path=one(paths,'historical Session');session=Session(path,logs[path],begin['wall'],runner,logs)
    offsets=[r['wall']-r['uptime'] for r in traces]
    uncertainty=max(offsets)-min(offsets)+max(abs(base.prefix_wall(a['prefix'],a['wall'],timezone.utc)-a['wall']) for a in (begin,end))+0.001
    session.uncertainty=uncertainty
    output=[]
    for iteration in (1,2,3):
        local=[r for r in ui if r['iteration']==iteration]
        start=base.event(local,'tap-command-start');returned=base.event(local,'tap-command-returned');cancel_start=base.event(local,'cancel-command-start');home=base.event(local,'home-interactive-after-dismiss')
        opened=bind_tap(session,session.find('Tap "edit-photo" Button',start['wall']-0.001,returned['wall']+0.001),label='edit-photo',app_pid=pid)
        cancelled=bind_tap(session,session.find('Tap "Cancel" Button',cancel_start['wall']-0.001,home['wall']+0.001),label='Cancel',app_pid=pid)
        action=one([r for r in app if r['event']=='app-beautify-tap' and start['uptime']<=r['uptime']<=returned['uptime']],'historical app action')
        instance=[r for r in app if r['instance']==action['instance']]
        delegate=base.event(instance,'picker-cancel-delegate');dismiss=base.event(instance,'root-cover-dismissal-completed')
        require(cancelled['dispatch']+uncertainty<=delegate['wall']<=dismiss['wall']<=home['wall'],'Historical callback sequence invalid')
        upper=home['wall']-opened['synthesis_start']+uncertainty
        output.append({'iteration':iteration,'open_input':opened,'cancel_input':cancelled,'delegate_wall':delegate['wall'],'home_wall':home['wall'],'open_to_home_upper_seconds':upper,'within_three_seconds':upper<=3})
    return {'schema':'celluloid.early-cancel.historical-binding-diagnostic.v1','native_candidate_executed':False,'native_acceptance':False,'release_qualification':False,'historical_full_status':'failed','cycles':output,'purpose':'Regression fixture for native binding only; original timestamps and old test selector retained'}


def trace_prefixes(logs,record,kind,pid):
    proofs=[]
    for loc in record['source_locations']:
        line=logs[loc['file']].splitlines()[loc['line']-1]
        p=PREFIX.match(line)
        if p:
            wanted=p['process'].endswith('UITests-Runner') if kind=='runner' else p['process']=='Celluloid'
            require(wanted and p['pid']==str(pid),'Trace raw process/PID provenance mismatch')
            proofs.append(p.groupdict())
    require(proofs,'No original native-prefix trace source')
    return proofs
