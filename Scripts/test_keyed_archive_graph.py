import base64,copy,hashlib,json,plistlib,unittest
from pathlib import Path
from keyed_archive_graph import canonical_graph,prove_equivalent

ROOT=Path(__file__).resolve().parent
class ArchiveGraphTests(unittest.TestCase):
    def setUp(self):
        controls=json.loads((ROOT/'fixtures/platform-rendering-controls.json').read_text())
        self.raw=base64.b64decode(controls['inputArchive']['base64']);self.archive=plistlib.loads(self.raw)
    def encode(self,value):return plistlib.dumps(value,fmt=plistlib.FMT_BINARY,sort_keys=False)
    def test_actual_independent_public_archives_preserve_full_graph(self):
        witness=json.loads((ROOT/'fixtures/archive-ordering-witness.json').read_text());current=base64.b64decode(witness['base64'])
        self.assertEqual(hashlib.sha256(current).hexdigest(),witness['sha256'])
        self.assertNotEqual(current,self.raw)
        proof=prove_equivalent(current,self.raw)
        self.assertFalse(proof['raw_bytes_equal']);self.assertEqual(proof['object_count'],35)
    def test_pair_order_and_reference_renumbering_only(self):
        archive=copy.deepcopy(self.archive);objects=archive['$objects'];order=[0]+list(reversed(range(1,len(objects))));renumber={old:new for new,old in enumerate(order)}
        def update(value):
            if type(value) is plistlib.UID:return plistlib.UID(renumber[value.data])
            if isinstance(value,list):return [update(x) for x in value]
            if isinstance(value,dict):
                if 'NS.keys' in value:
                    pairs=list(reversed(list(zip(value['NS.keys'],value['NS.objects']))));value=dict(value,**{'NS.keys':[x[0] for x in pairs],'NS.objects':[x[1] for x in pairs]})
                return {k:update(v) for k,v in reversed(list(value.items()))}
            return value
        archive['$objects']=[update(objects[old]) for old in order];archive['$top']=update(archive['$top'])
        prove_equivalent(self.encode(archive),self.encode(self.archive))
    def test_missing_duplicate_dangling_and_changed_types_values_classes_reject(self):
        def root(a):return a['$objects'][a['$top']['root'].data]
        def transform(a):return next(x for x in a['$objects'] if isinstance(x,dict) and 'NS.atval.tx' in x)
        changes=[lambda a:a.pop('$top'),lambda a:root(a)['NS.keys'].append(root(a)['NS.keys'][0]),
            lambda a:root(a).update({'NS.keys':root(a)['NS.keys']+[root(a)['NS.keys'][0]],'NS.objects':root(a)['NS.objects']+[root(a)['NS.objects'][0]]}),
            lambda a:root(a)['NS.objects'].__setitem__(0,plistlib.UID(999)),
            lambda a:transform(a).__setitem__('NS.atval.tx',1.0),lambda a:transform(a).__setitem__('NS.atval.tx',0),
            lambda a:transform(a).__setitem__('NS.atval.tx',float('nan')),
            lambda a:next(x for x in a['$objects'] if isinstance(x,dict) and '$classname' in x).__setitem__('$classname','NSUUID'),
            lambda a:root(a).__setitem__('unknown',True),lambda a:a['$objects'].append('unreachable')]
        for change in changes:
            a=copy.deepcopy(self.archive);change(a)
            with self.subTest(change=change),self.assertRaises(ValueError):prove_equivalent(self.encode(a),self.encode(self.archive))
    def test_duplicate_physical_plist_key_rejects_before_loader_overwrite(self):
        self.assertIn(b'$objects',self.raw)
        with self.assertRaisesRegex(ValueError,'Duplicate physical'):canonical_graph(self.raw.replace(b'$objects',b'$version'))
    def test_array_order_aliases_resources_and_cycles_remain_distinct(self):
        uid=plistlib.UID
        a={'$version':100000,'$archiver':'NSKeyedArchiver','$top':{'root':uid(1)},'$objects':['$null',{'NS.objects':[uid(3),uid(3),uid(4)],'$class':uid(2)},{'$classname':'NSArray','$classes':['NSArray','NSObject']},'same',b'opaque resource\x00\xff']}
        control=self.encode(a);prove_equivalent(control,control)
        changes=[lambda b:b['$objects'][1]['NS.objects'].reverse(),lambda b:b['$objects'].__setitem__(4,b'opaque resource\x00\xfe'),
            lambda b:(b['$objects'].append('same'),b['$objects'][1]['NS.objects'].__setitem__(1,uid(5))),
            lambda b:b['$objects'][1]['NS.objects'].__setitem__(0,uid(1))]
        for change in changes:
            b=copy.deepcopy(a);change(b)
            with self.subTest(change=change),self.assertRaises(ValueError):prove_equivalent(self.encode(b),control)
    def test_unreachable_physical_payload_or_extra_detached_reference_rejects(self):
        def append_physical(blob):
            raw=self.raw;trailer=bytearray(raw[-32:]);width=trailer[6]
            count=int.from_bytes(trailer[8:16],'big');table=int.from_bytes(trailer[24:32],'big')
            trailer[8:16]=(count+1).to_bytes(8,'big');trailer[24:32]=(table+len(blob)).to_bytes(8,'big')
            return raw[:table]+blob+raw[table:-32]+table.to_bytes(width,'big')+trailer
        with self.assertRaisesRegex(ValueError,'Unreachable physical plist payload'):canonical_graph(append_physical(b'\x41x'))
        with self.assertRaisesRegex(ValueError,'semantic graph'):prove_equivalent(append_physical(b'\x80\x00'),self.raw)

    def test_changed_missing_dangling_detached_uids_and_physical_cycles_reject(self):
        # Rewrite the physical binary-plist table, independently of plistlib's
        # decoded archive. Removed records need physical references renumbered;
        # NSKeyedArchive UID values are a separate reference namespace.
        raw=self.raw;trailer=bytearray(raw[-32:]);ow,rw=trailer[6:8]
        count=int.from_bytes(trailer[8:16],'big');table=int.from_bytes(trailer[24:32],'big')
        offsets=[int.from_bytes(raw[table+i*ow:table+(i+1)*ow],'big') for i in range(count)]
        records=[bytearray(raw[a:b]) for a,b in zip(offsets,offsets[1:]+[table])]
        physical_references=set();slots=[]
        for index,record in enumerate(records):
            kind=record[0]>>4
            if kind not in (10,13):continue
            size=record[0]&15;start=1
            if size==15:
                width=1<<(record[1]&15);start=2+width;size=int.from_bytes(record[2:start],'big')
            for n in range(size*(2 if kind==13 else 1)):
                offset=start+n*rw;value=int.from_bytes(record[offset:offset+rw],'big')
                slots.append((index,offset,value));physical_references.add(value)
        detached=[i for i,r in enumerate(records) if r[0]>>4==8 and i not in physical_references]
        self.assertEqual(len(detached),12)
        def emit(values,top=0):
            body=bytearray(b'bplist00');locations=[]
            for value in values:locations.append(len(body));body.extend(value)
            end=len(body)
            for value in locations:body.extend(value.to_bytes(ow,'big'))
            final=bytearray(trailer);final[8:16]=len(values).to_bytes(8,'big');final[16:24]=top.to_bytes(8,'big');final[24:32]=end.to_bytes(8,'big')
            return bytes(body+final)
        changed=copy.deepcopy(records);changed[detached[0]][1:]=b'\x00'
        with self.assertRaisesRegex(ValueError,'semantic graph'):prove_equivalent(emit(changed),raw)
        dangling=copy.deepcopy(records);dangling[detached[0]][1:]=b'\xff'
        with self.assertRaisesRegex(ValueError,'Dangling detached'):canonical_graph(emit(dangling))
        missing=copy.deepcopy(records);removed=detached[0]
        for index,offset,value in slots:
            if value>removed:missing[index][offset:offset+rw]=(value-1).to_bytes(rw,'big')
        del missing[removed]
        with self.assertRaisesRegex(ValueError,'semantic graph'):prove_equivalent(emit(missing),raw)
        cyclic=copy.deepcopy(records)
        # Make the outer root array refer to itself. This must fail before the
        # public loader could recurse or overwrite any archive-level structure.
        cyclic[0]=bytearray(b'\xa1'+(0).to_bytes(rw,'big'))
        with self.assertRaisesRegex(ValueError,'Cyclic/overdeep physical'):canonical_graph(emit(cyclic))

    def test_bounds_and_non_binary_archives_reject(self):
        for raw in [b'',b'x'*65_537,plistlib.dumps({'unqualified':'XML'},fmt=plistlib.FMT_XML),self.raw[:-1]]:
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):canonical_graph(raw)

if __name__=='__main__':unittest.main()
