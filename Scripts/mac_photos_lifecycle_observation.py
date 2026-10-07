"""One fixed owned lifecycle observation; the original <=2 result stays separate."""
import datetime,hashlib,json,math,re
from pathlib import Path
from validation_route import LIFECYCLE,current_route,context_clock
from mac_host_transport import parse,load_json,CASE,HOST_CONTRACT,ORDER
from mac_host_self_identity import validate as identity_validate,RECEIPT,IDENTIFIER
from consumer_runtime_binding import validate_raw_execution
from mac_host_lifecycle import validate as lifecycle_validate,PHASES
from mac_host_lifecycle_pixels import NAMES,PNG_LIMIT

MODE='defer-known-saved-pixel-assertion-v1'
FIXTURE='6138992615dd7d5bd499b80d9f11e39a0815111feccd5d4d3e59a676f4384772'
KNOWN_SAVED='744dfa09d6ab997552cdb11393a53761c8e098ffd37e6a8c3a9febdfd0972c99'
KNOWN_REFERENCE='eacc2ada4af742470b52d2ed14996d07e71db7c2b68b2da4f7947efcc7f9855a'
PIXEL_REASON='Stored saved raster disagrees with independent JPEG-aware reference'
PIXEL_FAILURE_TEXT='failed: caught error: "Error Domain=MacPhotosHostPrerequisite Code=1 "'+PIXEL_REASON+'" UserInfo={NSLocalizedDescription='+PIXEL_REASON+'}"'
OBSERVED='photos-filter-lifecycle-observed'
MARKER='MAC_HOST_FILTER_LIFECYCLE_OBSERVED owned Save, Fade reentry, nonmutating Cancel, Revert, original bytes and Original reentry observed; strict saved-pixel result remains separate'
def require(value,message):
    if not value:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def decode(data):return load_json(data)

def bind_context(context):
    require(context.get('validation_route')==LIFECYCLE and current_route(context['runner_environment'])==LIFECYCLE,'wrong fixed lifecycle route')
    require(context_clock(context)['case_seconds']==900 and context.get('seed')=={'mode':'require-empty-library'},'wrong lifecycle clock/fixture mode')
    require('boundary_probe' not in context and 'owned_saved_pixel_observation' not in context,'unexpected diagnostic mode')
    return dict(context,owned_saved_pixel_observation=MODE)

def admit_outcome(context_bytes,log,summary):
    """Exact terminal and completed functional evidence, before attachment export."""
    context=decode(context_bytes);env=context['runner_environment'];context_hash=sha(context_bytes)
    require(context.get('validation_route')==LIFECYCLE and current_route(env)==LIFECYCLE
        and context.get('owned_saved_pixel_observation')==MODE and 'boundary_probe' not in context,'wrong lifecycle observation context')
    require(context_clock(context)['case_seconds']==900 and context.get('seed')=={'mode':'require-empty-library'},'wrong original clock/ownership mode')
    require(env.get('GITHUB_RUN_ATTEMPT')=='1' and type(env.get('GITHUB_RUN_ID')) is str
        and re.fullmatch('[1-9][0-9]*',env['GITHUB_RUN_ID']) is not None
        and env['GITHUB_SHA']==env['GITHUB_WORKFLOW_SHA']==context['source_sha'],'wrong original run/source')
    records=parse(log,context,context_hash,complete=False)
    require(list(records)==ORDER,'missing original required host proofs')
    require(summary.get('result') in {'Passed','Failed'},'unknown original result')
    passed=summary['result']=='Passed'
    counts={'totalTestCount':1,'passedTests':int(passed),'failedTests':int(not passed),'skippedTests':0,'expectedFailures':0}
    require(all(type(summary.get(k)) is int and summary[k]==v for k,v in counts.items()),'wrong exact-case counts')
    configs=summary.get('devicesAndConfigurations');require(type(configs) is list and len(configs)==1,'ambiguous actual device')
    config=configs[0];device=config.get('device',{})
    require(all(type(config.get(k)) is int and config[k]==counts[k] for k in ['passedTests','failedTests','skippedTests','expectedFailures'])
        and (device.get('platform'),device.get('osVersion'),device.get('osBuildNumber'),device.get('architecture'))==('macOS','27.0','26A428','arm64'),'wrong actual device/counts')
    raw=validate_raw_execution(log,summary,photos_import_snapshot_diagnostic=True)
    expected_case='-['+CASE[0]+' '+CASE[1]+']'
    cases=[line for line in log.splitlines() if line.startswith('Test Case ')]
    require(len(cases)==2 and cases[0]=="Test Case '"+expected_case+"' started."
        and re.fullmatch(re.escape("Test Case '"+expected_case+"' "+('passed' if passed else 'failed'))+r' \([0-9]+(?:\.[0-9]+)? seconds\)\.',cases[1]),'wrong exact original case')
    require(raw['result_session_path_observation']==str(Path(env['RUNNER_TEMP'])/'MacPhotosHost.xcresult'),'wrong original result path')
    starts=[decode(line[len('BOUNDED_COMMAND_BEGIN '):]) for line in log.splitlines() if line.startswith('BOUNDED_COMMAND_BEGIN ')]
    ends=[decode(line[len('BOUNDED_COMMAND_END '):]) for line in log.splitlines() if line.startswith('BOUNDED_COMMAND_END ')]
    require(len(starts)==len(ends)==1 and ends[0]['exit_code']==(0 if passed else 65),'wrong native completion')
    started=datetime.datetime.fromisoformat(starts[0]['utc']).timestamp()
    require(all(type(summary.get(k)) in (int,float) and math.isfinite(summary[k]) for k in ['startTime','finishTime'])
        and started<=summary['startTime']<summary['finishTime']<=started+ends[0]['elapsed_seconds'],'summary outside original native interval')
    require('BOUNDED_COMMAND_TIMEOUT' not in log and 'BOUNDED_TIMEOUT_' not in log and 'MAC_HOST_FAIL_CLOSED_ABORT' not in log,'interrupted native case')
    require(not any(line.startswith('MAC_PHOTOS_BOUNDARY_ARM ') for line in log.splitlines()),'unexpected capture arm')
    require(log.splitlines().count(MARKER)==1,'missing/duplicate completed functional observation')
    require(sum(line.startswith('MAC_HOST_PREREQUISITE_PASSED ') for line in log.splitlines())==1,'missing/duplicate host prerequisite')
    photos=decode(records['photos-process.json']);ownership=decode(records['fixture-ownership.json'])
    containing=decode(records['containing-process.json']);fixture=decode(records['fixture.json'])
    require(photos.get('bundle')=='/System/Applications/Photos.app' and photos.get('executable')=='/System/Applications/Photos.app/Contents/MacOS/Photos'
        and type(photos.get('pid')) is int and photos['pid']>0,'wrong Photos host')
    require(containing.get('bundle')==context['app_path'] and containing.get('executable')==context['app_executable']
        and type(containing.get('pid')) is int and containing['pid']>0,'wrong containing app')
    require(ownership.get('source_sha')==context['source_sha'] and ownership.get('app_executable_sha256')==context['app_executable_sha256']
        and ownership.get('fixture_sha256')==fixture.get('sha256')==FIXTURE and fixture.get('source_sha')==context['source_sha']
        and ownership.get('mode')=='require-empty-library' and type(ownership.get('initial_count')) is int and ownership['initial_count']==0
        and type(ownership.get('selected_count')) is int and ownership['selected_count']==1
        and (ownership.get('width'),ownership.get('height'))==(1200,800),'wrong owned fixture')
    validate_host_ui(decode(records['host-selection.json']),decode(records['host-editor-before-process.json']),decode(records['host-editor-after-process.json']),photos,ownership,context['source_sha'])
    baseline=identity_validate(decode(records['extension-self-identity.json']),context,photos,ownership)
    prerequisite=decode(records['prerequisite.json']);outcome=decode(records['outcome.json']);lifecycle=decode(records['lifecycle.json'])
    required={'source_sha','host_entry_contract','last_stage','complete_host_e2e','save_reopen_cancel_revert','functional_observation_complete'}
    require(type(outcome) is dict and required<=set(outcome)<=required|{'first_blocked_operation','export_png_diagnostics','extension_menu_observation'},'unknown/missing final outcome')
    require(prerequisite.get('source_sha')==context['source_sha'] and prerequisite.get('host_entry_contract')==HOST_CONTRACT
        and prerequisite.get('prerequisite_passed') is True and prerequisite.get('complete_host_e2e') is False,'wrong actual host prerequisite')
    require(outcome.get('source_sha')==context['source_sha'] and outcome.get('host_entry_contract')==HOST_CONTRACT
        and outcome.get('complete_host_e2e') is False and outcome.get('functional_observation_complete') is True
        and outcome.get('last_stage')==('photos-filter-lifecycle-passed' if passed else OBSERVED)
        and outcome.get('save_reopen_cancel_revert')==('PhotosFilterLifecycle.1 complete' if passed else 'PhotosFilterLifecycle.1 incomplete'),'incomplete/unknown final outcome')
    require(lifecycle.get('source_sha')==context['source_sha'] and lifecycle.get('context_sha256')==context_hash
        and lifecycle.get('fixture_sha256')==FIXTURE and lifecycle.get('functional_observation_complete') is True
        and lifecycle.get('complete') is passed,'wrong lifecycle completion/binding')
    phases=lifecycle.get('phases');require(type(phases) is list and len(phases)==8
        and all(type(row) is dict and type(row.get('index')) is int and row['index']==i and row.get('name')==name
            for i,(row,name) in enumerate(zip(phases,PHASES))),'incomplete/reordered functional phases')
    blocked=[line for line in log.splitlines() if 'MAC_HOST_BLOCKED' in line]
    failures=summary.get('testFailures')
    if passed:
        require(not failures and not blocked and 'first_blocked_operation' not in outcome and not raw['scoped_errors'],'failed operation contradicts Passed')
    else:
        require(outcome.get('first_blocked_operation')=={'stage':OBSERVED,'reason':PIXEL_REASON,
            'operation':{'max_channel_delta':3,'deferred_from':'lifecycle-save-and-export'}}
            and blocked==['MAC_HOST_BLOCKED stage='+OBSERVED+' reason='+PIXEL_REASON],'new/unknown blocked operation')
        require(type(failures) is list and len(failures)==1 and failures[0].get('failureText')==PIXEL_FAILURE_TEXT
            and len(raw['scoped_errors'])==1 and raw['scoped_errors'][0]['line'].endswith(' : '+PIXEL_FAILURE_TEXT),'extra/non-pixel actual failure')
    require(sum(line.startswith('MAC_HOST_FILTER_LIFECYCLE_PASSED ') for line in log.splitlines())==int(passed),'contradictory strict lifecycle marker')
    return context,records,photos,ownership,baseline

def admit_images(context_bytes,log,summary,images):
    context,records,photos,ownership,baseline=admit_outcome(context_bytes,log,summary)
    proof=lifecycle_validate(decode(records['lifecycle.json']),context,photos,ownership,baseline,images,sha(context_bytes),observe_saved_pixel_difference=True)
    require(proof['strict_saved_pixel_passed']==(summary['result']=='Passed'),'native/pixel result contradiction')
    return proof

def attachment_capacity(files,lifecycle):
    metadata=lifecycle.get('images');require(type(metadata) is dict and set(metadata)==set(NAMES),'missing mandatory lifecycle PNGs')
    sizes=[metadata[name].get('bytes') for name in NAMES]
    require(all(type(n) is int and 0<n<=PNG_LIMIT for n in sizes),'invalid declared lifecycle PNG sizes')
    used=sum(row['bytes'] for row in files.values());required=sum(sizes)+128_000+4096+32_000
    require(used+required<=1_000_000,'insufficient original1MB capacity before lifecycle attachment export')
    return dict(retained_before_export=used,declared_png_bytes=sum(sizes),attachment_manifest_reserve=128000,source_after_reserve=4096,final_reserve=32000,cap_bytes=1000000)


# Exact original host UI predicates, expressed with require so -O cannot remove them.
def validate_host_ui(selection, before, after, photos, ownership, source_sha):
    common = {'schema', 'host_entry_contract', 'source_sha', 'photos_pid', 'photos_bundle', 'photos_executable', 'fixture_sha256', 'asset_label'}
    selection_keys = {'menu_title', 'menu_identifier', 'menu_scope', 'extension_menu_button_count', 'opened_menu_count', 'menu_count', 'menu_enabled', 'menu_hittable', 'editor_count_before'}
    editor_keys = {'phase', 'editor_label', 'editor_count', 'preview_label', 'preview_count', 'placeholder_count', 'preparing_count', 'filter_identifier', 'filter_count', 'filter_enabled', 'read_only_count', 'error_count'}
    for name, row, keys, schema in [('selection', selection, selection_keys, 'Celluloid.HostSelection.3'), ('before', before, editor_keys, 'Celluloid.HostEditor.2'), ('after', after, editor_keys, 'Celluloid.HostEditor.2')]:
        require(type(row) is dict and set(row) == common | keys, 'Unknown/missing host UI receipt: ' + name)
        require(row['schema'] == schema and row['host_entry_contract'] == HOST_CONTRACT, 'Original host UI binding')
        require(row['source_sha'] == source_sha, 'Original host UI binding')
        require(type(row['photos_pid']) is int and row['photos_pid'] == photos['pid'] and (row['photos_pid'] > 0), 'Original host UI binding')
        require(row['photos_bundle'] == photos['bundle'] == '/System/Applications/Photos.app', 'Original host UI binding')
        require(row['photos_executable'] == photos['executable'] == '/System/Applications/Photos.app/Contents/MacOS/Photos', 'Original host UI binding')
        require(row['fixture_sha256'] == ownership['fixture_sha256'] and row['asset_label'] == ownership['asset_label'], 'Original host UI binding')
    require(selection['menu_title'] == 'Celluloid' and selection['menu_identifier'] == 'editWithPlugin:', 'Original host UI binding')
    require(selection['menu_scope'] == 'Extensions.menuButton/childMenu/directMenuItem', 'Original host UI binding')
    for key, wanted in [('menu_count', 1), ('editor_count_before', 0), ('extension_menu_button_count', 1), ('opened_menu_count', 1)]:
        require(type(selection[key]) is int and selection[key] == wanted, 'Original host UI binding')
    require(selection['menu_enabled'] is True and selection['menu_hittable'] is True, 'Original host UI binding')
    for phase, row in [('before-process', before), ('after-process', after)]:
        require(row['phase'] == phase and row['editor_label'] == 'Celluloid photo editor' and (row['preview_label'] == 'Edited photo preview'), 'Original host UI binding')
        require(row['filter_identifier'] == 'photos-extension.filter' and row['filter_enabled'] is True, 'Original host UI binding')
        for key, wanted in [('editor_count', 1), ('preview_count', 1), ('placeholder_count', 0), ('preparing_count', 0), ('filter_count', 1), ('read_only_count', 0), ('error_count', 0)]:
            require(type(row[key]) is int and row[key] == wanted, 'Unready/ambiguous host editor: ' + key)
