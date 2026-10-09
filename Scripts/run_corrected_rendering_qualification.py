#!/usr/bin/env python3
"""One bounded43+1-case Mac producer and existing sequential2x/3x v2 consumers."""
from pathlib import Path
import json,math,os,re,sys,time
from corrected_rendering_admission import ROOT,DEPENDENCIES,admit,need,read_json,require_native_clear,mark_native_failure
from native_process import run
WORK_SECONDS=38*60  # Reserve90 seconds for source finalization inside the40-minute work window.
CONSUMER_RESERVE=21*60
MAC_SCHEME='CelluloidMac'
MAC_FILTER_SELECTOR='CelluloidMacTests/LegacyFilterAdjustmentTests/testNewlyAuthoredFilterOnlyArchivesAndOpaqueFallbackPreservation'
MAC_SELECTORS=('-only-testing:CelluloidMacPhotosExtensionTests','-only-testing:'+MAC_FILTER_SELECTOR)
MAC_AGGREGATE_CASES=44

def mac_fixture_selection(root=ROOT):
    # The complete project/generator/target inputs are pinned by admission. This
    # independent edge check prevents selecting a scheme that cannot emit the
    # required filter/baked-base fixtures before allocating native work.
    import xml.etree.ElementTree as ET
    manifest=read_json(root/DEPENDENCIES);graph=manifest['mac_producer_graph']
    need(MAC_SCHEME==graph['scheme']=='CelluloidMac','Wrong Mac fixture scheme')
    need(MAC_FILTER_SELECTOR==graph['filter_producer_selector'],'Wrong existing filter producer')
    need(MAC_SELECTORS==('-only-testing:CelluloidMacPhotosExtensionTests','-only-testing:'+MAC_FILTER_SELECTOR),'Missing or expanded native selector set')
    path=root/'CelluloidNative.xcodeproj/xcshareddata/xcschemes'/('CelluloidMac.xcscheme')
    xml=ET.fromstring(path.read_bytes())
    references=xml.findall('./TestAction/Testables/TestableReference')
    actual=[]
    for item in references:
        need(item.attrib.get('skipped')=='NO','Required Mac target skipped')
        ref=item.find('BuildableReference');need(ref is not None,'Missing scheme target reference')
        name=ref.attrib.get('BlueprintName');actual.append(name)
        need(ref.attrib.get('BlueprintIdentifier')==graph['target_ids'].get(name),'Scheme target identity changed')
    need(actual==['CelluloidMacTests','CelluloidMacPhotosExtensionTests'],'Fixture target absent or unreviewed scheme test target')
    source_path=graph['filter_producer_source']
    need(source_path in graph['compiled_sources_by_target']['CelluloidMacTests'],'Producer source is not compiled by selected target')
    source=(root/source_path).read_text();module,owner,method=MAC_FILTER_SELECTOR.split('/')
    need(len(re.findall(r'final class '+re.escape(owner)+r'\s*:\s*XCTestCase',source))==1 and len(re.findall(r'func '+re.escape(method)+r'\(',source))==1,'Producer selector has no unique source method')
    need(MAC_AGGREGATE_CASES==43+1==graph['aggregate_expected_cases'],'Wrong explicit43+1 accounting')
    return {'scheme':MAC_SCHEME,'selectors':list(MAC_SELECTORS),'extension_cases':43,'filter_producer_cases':1,'aggregate_cases':MAC_AGGREGATE_CASES,'actual_project_graph_audit_sha256':graph['audit_sha256']}

def mac_outcome(log,summary,exit_code):
    need(exit_code==0,'Mac test command failed')
    need(summary.get('result')=='Passed','Mac finalized result did not pass')
    for key,value in {'totalTestCount':MAC_AGGREGATE_CASES,'passedTests':MAC_AGGREGATE_CASES,'failedTests':0,'skippedTests':0,'expectedFailures':0}.items():
        need(type(summary.get(key)) is int and summary[key]==value,'Wrong full Mac deterministic count: '+key)
    need(summary.get('testFailures')==[] and summary.get('runtimeWarnings')==[],'Mac failure or runtime warning retained')
    for key in ['startTime','finishTime']:
        need(type(summary.get(key)) in (int,float) and math.isfinite(summary[key]) and summary[key]>0,'Invalid Mac execution time')
    need(summary['finishTime']>summary['startTime'],'Invalid Mac execution interval')
    # Same narrow success-terminal normalization as uikit_full_shipping_handoff.py.
    lines=log.splitlines();terminals=[x.strip() for x in lines if re.match(r'^\s*\*\* TEST(?: EXECUTE)?\b',x)]
    need(terminals==['** TEST SUCCEEDED **'],'Wrong Mac test terminal')
    normalized='\n'.join('** TEST EXECUTE SUCCEEDED **' if x=='** TEST SUCCEEDED **' else x for x in lines)+'\n'
    from consumer_runtime_binding import validate_raw_execution
    result=validate_raw_execution(normalized,summary)
    from verify_required_interoperability import MAC_REQUIRED_CASES
    passed=re.findall(r"^Test Case '-\[([\w]+)\.([\w]+) (test\w+)\]' passed\b",log,re.M)
    actual=[module+'/'+owner+'.'+method for module,owner,method in passed]
    module,owner,method=MAC_FILTER_SELECTOR.split('/')
    expected={'CelluloidMacPhotosExtensionTests/'+name for name in MAC_REQUIRED_CASES}|{module+'/'+owner+'.'+method}
    need(len(actual)==MAC_AGGREGATE_CASES and set(actual)==expected,'Missing, extra or duplicate43+1 actual Mac cases')
    result.update(extension_passed_cases=43,filter_producer_passed_cases=1,filter_producer_selector=MAC_FILTER_SELECTOR)
    return result

def main():
    temp=Path(os.environ['RUNNER_TEMP']);clock=read_json(temp/'corrected-v2-clock.json')
    need(clock.get('source_sha')==os.environ['GITHUB_SHA'] and clock.get('run_id')==os.environ['GITHUB_RUN_ID'],'Wrong first-step clock binding')
    started=clock['started_monotonic'];need(type(started) in (int,float) and math.isfinite(started) and 0<=time.monotonic()-started<WORK_SECONDS,'Invalid or expired first-step clock')
    deadline=started+WORK_SECONDS
    result={'schema':'Celluloid.CorrectedRenderingQualification.1','source_sha':os.environ['GITHUB_SHA'],
            'mac_extension_expected_cases':43,'mac_filter_producer_expected_cases':1,'mac_expected_cases':MAC_AGGREGATE_CASES,'uikit_expected_cases_per_profile':1,'profiles':['2x','3x'],
            'work_budget_seconds':WORK_SECONDS,'qualified':False,'photos_host_qualified':False,'release_qualified':False,'stages':[]}
    def command(stage,args,seconds,**kwargs):
        require_native_clear()
        remaining=deadline-time.monotonic();need(remaining>seconds+30,'Insufficient whole-job budget and command cleanup before '+stage)
        row={'stage':stage,'timeout_seconds':seconds};result['stages'].append(row)
        try:
            value=run(args,timeout=seconds,**kwargs);row['exit_code']=value.returncode;return value
        except BaseException as error:
            row['error']=type(error).__name__+': '+str(error)
            mark_native_failure(error)
            raise
    primary=None
    try:
        identity=admit();result['source_admission']=identity
        need(read_json(temp/'combined-source-before.json')==identity,'First-step source receipt mismatch')
        (temp/'corrected-rendering-dependencies.json').write_bytes((ROOT/DEPENDENCIES).read_bytes())
        toolchain=command('xcode',['xcodebuild','-version'],30,log_name='corrected-xcode.log').stdout
        need('Xcode 27.0' in toolchain.splitlines(),'Wrong Xcode version')
        command('os',['sw_vers'],20,log_name='corrected-os.log')
        for script in ['validate_native_sources.py','validate_native_localization.py']:
            command(script,[sys.executable,'-B',ROOT/'Scripts'/script],60,log_name='corrected-'+script+'.log')
        command('materialize-icons',['swift','-swift-version','5',ROOT/'Scripts/materialize_native_icons.swift'],120,log_name='corrected-icons.log')
        command('verify-icons',[sys.executable,'-B',ROOT/'Scripts/verify_native_icon_inputs.py'],30,log_name='corrected-icon-verification.log')
        from verify_required_interoperability import required,verify
        need(len(required('mac')['CelluloidMacPhotosExtensionTests'])==43,'Current full Mac inventory changed')
        result['mac_fixture_reachability']=mac_fixture_selection()
        bundle=temp/'CelluloidMac.xcresult'
        mac=command('mac-deterministic',['xcodebuild','-project',ROOT/'CelluloidNative.xcodeproj','-scheme',MAC_SCHEME,
            '-configuration','Debug','-destination','platform=macOS','-derivedDataPath',temp/'corrected-mac',
            '-resultBundlePath',bundle,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
            *MAC_SELECTORS,'CODE_SIGNING_ALLOWED=NO','COMPILER_INDEX_STORE_ENABLE=NO','test'],900,check=False,log_name='mac.log')
        official=command('mac-summary',['xcrun','xcresulttool','get','test-results','summary','--path',bundle],30,echo=False)
        summary=json.loads(official.stdout);(temp/'corrected-mac-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        result['mac_raw_accounting']=mac_outcome((temp/'mac.log').read_text(),summary,mac.returncode)
        producer=verify('mac',temp/'mac.log',None,os.environ['GITHUB_SHA'],platform_contract=True)
        (temp/'mac-required-tests.json').write_text(json.dumps(producer,indent=2)+'\n')
        need(all(producer['checks'].values()),'Current required Mac producer failed')
        need(deadline-time.monotonic()>CONSUMER_RESERVE,'Insufficient active and cleanup reserve for both consumers')
        command('uikit-two-profiles',[sys.executable,'-B',ROOT/'Scripts/run_early_uikit_interop.py'],1200,log_name='corrected-consumer-driver.log')
        output=temp/'corrected-v2-step-output.txt'
        command('v2-continuation',[sys.executable,'-B',ROOT/'Scripts/verify_interop_continuation.py','--github-output',output],90,log_name='corrected-continuation.log')
        continuation=read_json(temp/'interop-continuation.json')
        need(continuation.get('continuation_safe') is True and continuation.get('platform_contract_accepted') is True,'Incomplete v2 continuation')
        need(continuation.get('final_archive_accepted') is False,'Unexpected final-release assertion')
        result['historical_strict_pixel_passed']=continuation['strict_pixel_passed']
        require_native_clear()
        result['qualified']=True
    except BaseException as error:
        primary=error;result['error']=type(error).__name__+': '+str(error)
    finally:
        try:
            after=admit();need(after==read_json(temp/'combined-source-before.json'),'Source changed during work')
            (temp/'combined-source-after.json').write_text(json.dumps(after,indent=2)+'\n')
        except BaseException as error:
            result['qualified']=False;result['source_after_error']=type(error).__name__+': '+str(error)
            if primary is None:primary=error
        result['elapsed_seconds']=round(time.monotonic()-started,3)
        (temp/'corrected-rendering-result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('CORRECTED_RENDERING_RESULT '+json.dumps(result,sort_keys=True))
    if primary is not None:raise primary
if __name__=='__main__':main()
