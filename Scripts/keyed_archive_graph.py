"""Bounded test-only archive equivalence; preserve types, aliases and raw bytes."""
import base64
import hashlib
import json
import math
import plistlib

MAX_BYTES=65_536
MAX_OBJECTS=256

def require(value,message):
    if not value:raise ValueError(message)

def _unique_binary_dictionary_keys(raw):
    # plistlib's public loader overwrites duplicate physical plist keys. Check
    # those keys before decoding, in addition to archived NSDictionary keys.
    require(raw[:8]==b'bplist00' and len(raw)>=40,'Expected bounded binary plist')
    trailer=raw[-32:];ow,rw=trailer[6:8]
    count=int.from_bytes(trailer[8:16],'big');top=int.from_bytes(trailer[16:24],'big');table=int.from_bytes(trailer[24:32],'big')
    require(trailer[:6]==b'\0'*6 and ow in (1,2,4,8) and rw in (1,2,4,8),'Invalid plist trailer')
    require(0<count<=4096 and top<count and 8<=table and table+count*ow==len(raw)-32,'Invalid plist offset table')
    offsets=[int.from_bytes(raw[table+i*ow:table+(i+1)*ow],'big') for i in range(count)]
    require(len(set(offsets))==count and all(8<=x<table for x in offsets),'Invalid/aliased physical plist object')
    def sized(offset):
        marker=raw[offset];size=marker&15;start=offset+1
        if size==15:
            require(start<table and raw[start]>>4==1 and raw[start]&15<=3,'Invalid extended plist count')
            width=1<<(raw[start]&15);start+=1
            require(start+width<=table,'Truncated plist count')
            size=int.from_bytes(raw[start:start+width],'big');start+=width
        return marker>>4,size,start
    def key(reference):
        require(reference<count,'Dangling physical plist key')
        kind,size,start=sized(offsets[reference]);require(kind in (5,6) and size<=16_384,'Non-string/oversized plist key')
        end=start+size*(2 if kind==6 else 1);require(end<=table,'Truncated plist key')
        return raw[start:end].decode('utf-16be' if kind==6 else 'ascii')
    for offset in offsets:
        if raw[offset]>>4!=13:continue
        _,size,start=sized(offset);require(size<=256 and start+2*size*rw<=table,'Oversized/truncated plist dictionary')
        keys=[key(int.from_bytes(raw[start+i*rw:start+(i+1)*rw],'big')) for i in range(size)]
        require(len(keys)==len(set(keys)),'Duplicate physical plist dictionary key')
    # Validate the entire physical plist as well: ignored/unreachable data must
    # not disappear when the public loader builds its root object.
    edges={};ends={}
    for index,offset in enumerate(offsets):
        marker=raw[offset];kind=marker>>4;low=marker&15;start=offset+1;refs=[]
        if kind in (4,5,6,10,13):
            _,size,start=sized(offset)
            if kind in (10,13):
                require(size<=256,'Oversized physical collection');length=size*(2 if kind==13 else 1)
                finish=start+length*rw;require(finish<=table,'Truncated physical references')
                refs=[int.from_bytes(raw[start+n*rw:start+(n+1)*rw],'big') for n in range(length)]
                require(all(v<count for v in refs),'Dangling physical reference')
            else:
                finish=start+size*(2 if kind==6 else 1);require(finish<=table,'Truncated physical value')
        elif kind==0:
            require(low in (0,8,9),'Unsupported plist singleton');finish=start
        elif kind==1:
            require(low<=4,'Oversized physical integer');finish=start+(1<<low)
        elif kind==2:
            require(low in (2,3),'Invalid physical real');finish=start+(1<<low)
        elif kind==8:finish=start+low+1
        else:raise ValueError('Unsupported physical plist type')
        require(finish<=table,'Truncated physical scalar');edges[index]=refs;ends[offset]=finish
    ordered=sorted(offsets)
    require(ordered[0]==8 and all(ends[a]==b for a,b in zip(ordered,ordered[1:]+[table])),'Overlapping or unbound physical plist bytes')
    reached=set();pending=set()
    def walk(index,depth):
        require(depth<=64 and index not in pending,'Cyclic/overdeep physical plist')
        if index in reached:return
        reached.add(index);pending.add(index)
        for child in edges[index]:walk(child,depth+1)
        pending.remove(index)
    walk(top,0)
    detached=[]
    for index in sorted(set(range(count))-reached):
        # Apple's retained archives contain duplicate physical UID records that
        # are not referenced by the outer plist. Preserve their complete target
        # multiset after archive-reference renumbering; never discard payloads.
        offset=offsets[index];require(raw[offset]>>4==8,'Unreachable physical plist payload')
        detached.append(int.from_bytes(raw[offset+1:ends[offset]],'big'))
    return detached

def canonical_graph(raw):
    require(type(raw) is bytes and 0<len(raw)<=MAX_BYTES,'Archive byte bound')
    detached=_unique_binary_dictionary_keys(raw)
    archive=plistlib.loads(raw)
    require(type(archive) is dict and set(archive)=={'$version','$archiver','$top','$objects'},'Unknown/missing archive root field')
    require(type(archive['$version']) is int and archive['$version']==100000 and archive['$archiver']=='NSKeyedArchiver','Unknown archive version/type')
    require(type(archive['$top']) is dict and set(archive['$top'])=={'root'},'Unknown/missing archive root reference')
    objects=archive['$objects'];require(type(objects) is list and 1<len(objects)<=MAX_OBJECTS and objects[0]=='$null','Invalid archive object table')
    mapping={0:0};nodes=[['string','$null']];active=set();visits=0
    def reference(value,depth):
        require(type(value) is plistlib.UID and type(value.data) is int and 0<=value.data<len(objects),'Dangling/malformed archive reference')
        index=value.data;require(index not in active,'Cyclic archive graph')
        if index not in mapping:
            mapping[index]=len(nodes);nodes.append(None);active.add(index)
            nodes[mapping[index]]=normalize(objects[index],depth+1)
            active.remove(index)
        return ['reference',mapping[index]]
    def normalize(value,depth):
        nonlocal visits
        visits+=1;require(depth<=32 and visits<=4096,'Archive graph traversal bound')
        if type(value) is plistlib.UID:return reference(value,depth)
        if value is None:return ['null']
        if type(value) is bool:return ['boolean',value]
        if type(value) is int:
            require(-(1<<63)<=value<(1<<64),'Oversized archive integer');return ['integer',str(value)]
        if type(value) is float:
            require(math.isfinite(value),'Nonfinite archive real');return ['real',value.hex()]
        if type(value) is str:
            require(len(value.encode('utf-8'))<=16_384,'Oversized archive string');return ['string',value]
        if type(value) is bytes:
            require(len(value)<=MAX_BYTES,'Oversized archive resource');return ['data',base64.b64encode(value).decode('ascii')]
        if type(value) is list:
            require(len(value)<=256,'Oversized archive array');return ['array',[normalize(x,depth+1) for x in value]]
        require(type(value) is dict and len(value)<=256 and all(type(k) is str for k in value),'Unknown archive value type')
        if '$classname' in value:
            require(set(value)=={'$classname','$classes'} and value['$classname'] in {'NSDictionary','NSArray','NSValue'},'Unknown/malformed archive class')
        if 'NS.keys' in value:
            require(set(value)=={'NS.keys','NS.objects','$class'},'Unknown/missing archived dictionary field')
            keys,values=value['NS.keys'],value['NS.objects']
            require(type(keys) is list and type(values) is list and len(keys)==len(values)<=256,'Invalid archived dictionary pairs')
            pairs=[]
            for k,v in zip(keys,values):
                require(type(k) is plistlib.UID and 0<=k.data<len(objects) and type(objects[k.data]) is str,'Invalid archived dictionary key reference')
                pairs.append((objects[k.data],k,v))
            require(len({name for name,_,_ in pairs})==len(pairs),'Duplicate archived dictionary key')
            # Visit paired key/value references in semantic key order. Keep the
            # references themselves, so sharing/alias changes remain visible.
            cls=normalize(value['$class'],depth+1)
            return ['dictionary',cls,[[reference(k,depth+1),normalize(v,depth+1)] for _,k,v in sorted(pairs,key=lambda p:p[0])]]
        return ['fields',[[k,normalize(value[k],depth+1)] for k in sorted(value)]]
    root=reference(archive['$top']['root'],0)
    require(set(mapping)==set(range(len(objects))),'Unreachable archive object')
    require(all(value in mapping for value in detached),'Dangling detached physical UID')
    return {'archiver':'NSKeyedArchiver','version':100000,'root':root,'objects':nodes,
            'detachedPhysicalReferences':sorted(mapping[value] for value in detached)}

def prove_equivalent(candidate,control):
    left,right=canonical_graph(candidate),canonical_graph(control)
    require(left==right,'Archive semantic graph changed')
    canonical=json.dumps(left,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    digest=lambda data:hashlib.sha256(data).hexdigest()
    return {'schema':'Celluloid.ArchiveGraph.1','candidate_raw_sha256':digest(candidate),'control_raw_sha256':digest(control),
            'canonical_graph_sha256':digest(canonical),'object_count':len(left['objects']),'raw_bytes_equal':candidate==control,
            'normalization':'Dictionary pair/field order and reference renumbering only; types, values, classes, array order, aliases and data bytes preserved'}
