"""One real-window capture case: original pixels, exact product, PID and clock."""
import hashlib
import math
from pathlib import Path
import re
import uuid

from mac_store_io import read_file, strict_json
from mac_store_io import admit_summary
from mac_store_png import store_copy, LIMIT as PNG_LIMIT
import mac_store_display as display_contract

CASE = 'testStoreOriginalDocumentScreenshots'
ARGS = ['-AppleLanguages','(en)','-AppleLocale','en_US','-ApplePersistenceIgnoreState','YES','--celluloid-store-capture']
STATES = {
    'citrus': {'sourceFilename':'demo-citrus-sunny.png',
        'sourceSHA256':'cd4c5178d550003b452b75904caba58a72c6eadc4658a083469c7684b4c00b03', 'sourceBytes':2880485,
        'sourceDimensions':[1254,1254], 'documentDimensions':'1254 × 1254 px', 'filter':'Original', 'layerCount':0},
    'coast': {'sourceFilename':'demo-coast-sunny.png',
        'sourceSHA256':'505e1348a049a9f88cf86b4fb936702b45323f5d411ebce8f0a3415150fedcda', 'sourceBytes':2997725,
        'sourceDimensions':[1254,1254], 'documentDimensions':'1254 × 1254 px', 'filter':'Original', 'layerCount':0}}
SOURCE_BLOBS = {'citrus':'49c4dfaa7f09c2db9f4853cadbb5baaa47490157', 'coast':'90b483ba6b398e39e63b15c11725fa6afe1df97c'}
MAX_PACKET = 14 * 1024 * 1024


def need(ok, reason):
    if not ok: raise ValueError(reason)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def number(value): return type(value) in (int, float) and math.isfinite(value)


def summary_admission(raw, command):
    admit_summary(raw, {'exit':command['returncode'], 'startedEpoch':command['started_epoch'],
                        'finishedEpoch':command['finished_epoch']})
    summary = strict_json(raw)
    configs = summary.get('devicesAndConfigurations')
    need(isinstance(configs, list) and len(configs) == 1, 'capture-destination-count')
    config = configs[0]; device = config.get('device', {})
    need(all(device.get(k) == v for k, v in {'platform':'macOS', 'architecture':'arm64', 'osVersion':'27.0'}.items()) and
        isinstance(device.get('deviceId'), str) and 0 < len(device['deviceId']) <= 256 and
        config.get('testPlanConfiguration', {}).get('configurationName') == 'Test Scheme Action', 'capture-destination')
    need(all(type(config.get(k)) is int and config[k] == summary[k]
        for k in ('passedTests','failedTests','skippedTests','expectedFailures')), 'capture-destination-counts')
    failures = summary.get('testFailures', [])
    need(isinstance(failures, list) and len(failures) == (0 if summary['passedTests'] else 1), 'capture-failure-count')
    for failure in failures:
        need(failure.get('testIdentifierString') == 'NativeEditorUITests/' + CASE + '()' and
             failure.get('testIdentifierURL') == 'test://com.apple.xcode/CelluloidNative/CelluloidMacUITests/NativeEditorUITests/' + CASE,
             'capture-foreign-failure')
    return summary


def validate_capture(root, summary_raw, product, test, *, tick=lambda: None, read=read_file):
    summary = summary_admission(summary_raw, test)
    need(summary['passedTests'] == 1 and test['returncode'] == 0, 'capture-case-failed')
    manifest_raw = read(root/'manifest.json', 512*1024); groups = strict_json(manifest_raw)
    need(isinstance(groups, list) and len(groups) == 1, 'capture-not-one-exported-case')
    group = groups[0]
    need(group.get('testIdentifier') == 'NativeEditorUITests/' + CASE + '()' and
        group.get('testIdentifierURL') == 'test://com.apple.xcode/CelluloidNative/CelluloidMacUITests/NativeEditorUITests/' + CASE,
        'capture-foreign-exported-case')
    items = group.get('attachments'); need(isinstance(items,list) and 5 <= len(items) <= 32, 'capture-attachment-count')
    device = summary['devicesAndConfigurations'][0]['device']['deviceId']; selected = {}; used = set()
    for state in STATES:
        for kind, ext in [('window','png'), ('proof','txt')]:
            prefix = 'Native Mac Store ' + kind + ' ' + state
            matches = [x for x in items if isinstance(x,dict) and isinstance(x.get('suggestedHumanReadableName'),str) and
                       re.fullmatch(re.escape(prefix) + r'_[0-9]+_[0-9A-Fa-f-]{36}\.' + ext, x['suggestedHumanReadableName'])]
            need(len(matches) == 1, 'capture-missing-or-duplicate-' + kind + '-' + state)
            item = matches[0]; filename = item.get('exportedFileName', '')
            need(isinstance(filename,str) and re.fullmatch(r'[0-9A-Fa-f-]{36}\.' + ext,filename) and filename not in used, 'capture-file-name')
            used.add(filename)
            need(item.get('deviceId') == device and item.get('configurationName') == 'Test Scheme Action' and
                item.get('isAssociatedWithFailure') is False and number(item.get('timestamp')) and
                summary['startTime'] <= item['timestamp'] <= summary['finishTime']+.001, 'capture-attachment-scope')
            selected[state,kind] = item
    display_items={};display_raw={}
    for suffix in ('setup','restore'):
        prefix='Native Mac Store display '+suffix
        matches=[x for x in items if isinstance(x,dict) and isinstance(x.get('suggestedHumanReadableName'),str) and
            re.fullmatch(re.escape(prefix)+r'_[0-9]+_[0-9A-Fa-f-]{36}\.txt',x['suggestedHumanReadableName'])]
        if suffix=='restore' and not matches:
            display_items[suffix]=None;display_raw[suffix]=None;continue
        need(len(matches)==1,'display-receipt-missing-or-duplicate')
        item=matches[0];filename=item.get('exportedFileName','')
        need(isinstance(filename,str) and re.fullmatch(r'[0-9A-Fa-f-]{36}\.txt',filename) and filename not in used,'display-receipt-path')
        used.add(filename)
        need(item.get('deviceId')==device and item.get('configurationName')=='Test Scheme Action' and
            item.get('isAssociatedWithFailure') is False and number(item.get('timestamp')) and
            summary['startTime']<=item['timestamp']<=summary['finishTime']+.001,'display-attachment-scope')
        display_items[suffix]=item;display_raw[suffix]=read(root/filename,display_contract.LIMIT)
    display=display_contract.validate(display_raw['setup'],display_raw['restore'],summary)
    display.update(setupAttachment=display_items['setup'],restoreAttachment=display_items['restore'])
    need(display['setup']['test']=='-[CelluloidMacUITests.NativeEditorUITests '+CASE+']' and
        all(display[suffix]['finished']<=display_items[suffix]['timestamp']+.001 for suffix in ('setup','restore') if display_items[suffix] is not None),
        'display-case-or-attachment-clock')
    proofs = {}; images = {}; format_failures = {}; previous = None
    fields = {'v','state','token','pid','test','started','captured','sequential','args','sandbox','bundle','applicationPath',
              'expectedPath','executable','executableSHA256','logicSHA256','imageName','pngSHA256','pngBytes','width','height',
              'windowFrame','sourceFilename','sourceSHA256','sourceBytes','sourceDimensions','documentDimensions','filter','layerCount','backingScale','visibleFrameAX','displaySetupSHA256'}
    for state,visible_state in STATES.items():
        tick(); image_item = selected[state,'window']; record_item = selected[state,'proof']
        record_raw = read(root/record_item['exportedFileName'],4096); row = strict_json(record_raw)
        need(isinstance(row,dict) and set(row) == fields and type(row['v']) is int and row['v'] == 1 and row['state'] == state,
             'capture-receipt-fields')
        token = row['token']; need(isinstance(token,str) and re.fullmatch('[0-9A-F-]{36}',token) is not None and str(uuid.UUID(token)).upper() == token, 'capture-token')
        need(type(row['pid']) is int and row['pid'] > 0 and row['test'] == '-[CelluloidMacUITests.NativeEditorUITests ' + CASE + ']' and
            row['sequential'] is True and row['args'] == ARGS and row['sandbox'] is False, 'capture-launch-scope')
        need(all(row.get(k) == v for k,v in product.items()) and row['expectedPath'] == product['applicationPath'] and
            row['bundle'] == 'Mango.Celluloid', 'capture-product')
        need(number(row['started']) and number(row['captured']) and
            summary['startTime'] <= row['started'] <= row['captured'] <= image_item['timestamp']+.001 and
            image_item['timestamp'] <= record_item['timestamp']+.001, 'capture-clock')
        need(row['token']==display['setup']['token'] and row['displaySetupSHA256']==display['setupSHA256'] and
            number(row['backingScale']) and row['backingScale']==display['scale'] and
            display['setup']['finished']<=row['started'] and
            (display['restore'] is None or display['restore']['started']>=record_item['timestamp']-.001),'capture-display-binding')
        frame = row['windowFrame']
        need(isinstance(frame,list) and len(frame)==4 and all(number(x) for x in frame) and
            abs(frame[2]-1280)<.5 and abs(frame[3]-800)<.5 and type(row['width']) is int and type(row['height']) is int and
            (row['width'],row['height'])==(1280*display['scale'],800*display['scale']) and
            abs(row['width']-frame[2]*display['scale'])<1 and abs(row['height']-frame[3]*display['scale'])<1, 'capture-window-size')
        visible=display_contract.rect(row['visibleFrameAX']);screen=display['setup']['after']['frame']
        need(visible[0]>=-.5 and visible[1]>=-.5 and visible[0]+visible[2]<=screen[2]+.5 and visible[1]+visible[3]<=screen[3]+.5 and
            frame[0]>=visible[0]-.5 and frame[1]>=visible[1]-.5 and frame[0]+frame[2]<=visible[0]+visible[2]+.5 and
            frame[1]+frame[3]<=visible[1]+visible[3]+.5,'capture-window-offscreen')
        need(row['imageName']=='Native Mac Store window '+state and all(row.get(k)==v for k,v in visible_state.items()) and
            type(row['sourceBytes']) is int and type(row['layerCount']) is int and
            all(type(x) is int for x in row['sourceDimensions']), 'capture-visible-state')
        if previous is not None:
            need(all(row[k] == previous[k] for k in ('token','pid','started','windowFrame')) and
                previous['captured'] < row['captured'] and selected['citrus','proof']['timestamp'] <= row['captured'], 'capture-second-launch-or-order')
        original = read(root/image_item['exportedFileName'],PNG_LIMIT)
        need(type(row['pngBytes']) is int and row['pngBytes'] == len(original) and row['pngSHA256'] == digest(original), 'capture-pixel-binding')
        images['native-'+state+'.png'] = original
        try:
            store, conversion = store_copy(original, tick=tick)
            images['store-'+state+'.png'] = store
            store_identity = dict(bytes=len(store),sha256=digest(store))
        except ValueError as error:
            # Keep already source/PID/time/hash-bound native pixels for review.
            # A deadline/capture subclass is never downgraded to a format issue.
            if type(error) is not ValueError: raise
            format_failures[state] = str(error)[:256]; conversion = None; store_identity = None
        proofs[state] = dict(receipt=row, receiptText=record_raw.decode('utf-8'), receiptSHA256=digest(record_raw), imageAttachment=image_item,
            receiptAttachment=record_item, conversion=conversion,
            nativePNG=dict(bytes=len(original),sha256=digest(original)), storePNG=store_identity)
        previous = row
    need(proofs['citrus']['nativePNG']['sha256'] != proofs['coast']['nativePNG']['sha256'], 'capture-identical-state-images')
    tick()
    return {'summarySHA256':digest(summary_raw),'manifestSHA256':digest(manifest_raw),
        'summary':summary,'manifest':groups,'manifestText':manifest_raw.decode('utf-8'),'states':proofs,'visualAcceptance':'pending-human-review',
        'display':display,'formatFailures':format_failures,'effectiveAppLocale':'English-observed-in-fixed-UI-labels','signingQualified':False}, images
