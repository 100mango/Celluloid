"""Bind every current product file plus the explicit additive host controls."""
import hashlib,json,os,re,stat,subprocess,sys
from pathlib import Path
from final_mac_photos_route import HOST_ONLY,current_route,host_only_source_binding,require
ROOT=Path(__file__).resolve().parents[1]
BASE='13e9a1ed63c6e7744803419f27e429a759df1209'
TREE='f2c6d0f38c026957b0b34f22b916eb80ed5b20a8'
CONTRACT='.github/final-mac-photos-product.json'
CONFIG='.github/final-mac-photos-host.json'
ADDITIONS=set(['.github/final-mac-boundary-source.json', '.github/final-mac-photos-host.json', '.github/final-mac-photos-product.json', '.github/workflows/final-mac-photos-boundary.yml', 'Scripts/compare_owned_photos_boundary.swift', 'Scripts/final_mac_photos_gate.py', 'Scripts/final_mac_photos_lifecycle.py', 'Scripts/final_mac_photos_route.py', 'Scripts/final_mac_photos_source.py', 'Scripts/final_mac_photos_transport.py', 'Scripts/mac_photos_boundary_probe.py', 'Scripts/run_mac_photos_boundary.py', 'Scripts/test_mac_photos_boundary_source.py', 'Scripts/test_mac_photos_boundary_probe.py', 'Scripts/test_mac_photos_boundary_route.py'])

def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict_json(raw):
 def pairs(rows):
  d={}
  for k,v in rows:
   require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:require(False,'Nonfinite JSON'))
def load_contract(root=ROOT):
 c=strict_json((root/CONTRACT).read_bytes())
 require(c['schema']=='Celluloid.FinalMacPhotosSource.1' and c['product_sha']==BASE and c['product_tree']==TREE,'Wrong product binding')
 require(type(c['files']) is list and len(c['files'])==962 and len(c['git_files'])==962,'Wrong product inventory size')
 require(c['files']==sorted(c['files']) and len({r[0] for r in c['files']})==962,'Duplicate/unsorted product path')
 require(sha(json.dumps(c['files'],separators=(',',':')).encode())==c['fingerprint'],'Wrong product fingerprint')
 require([r[0] for r in c['files']]==[r[0] for r in c['git_files']],'Inconsistent product inventories')
 return c
def snapshot(root=ROOT):
 c=load_contract(root)
 for (rel,digest),(gitrel,mode,blob) in zip(c['files'],c['git_files']):
  require(type(rel) is str and rel==gitrel and not Path(rel).is_absolute() and '..' not in Path(rel).parts,'Unsafe product path')
  p=root/rel
  require(p.is_file() and not p.is_symlink() and p.stat().st_nlink==1,'Invalid product file '+rel)
  require(not any(v.is_symlink() for v in p.parents if v!=root and root in v.parents),'Product parent alias '+rel)
  raw=p.read_bytes();actual_mode='100755' if p.stat().st_mode&stat.S_IXUSR else '100644'
  require(sha(raw)==digest and actual_mode==mode,'Changed product file/mode '+rel)
  actual_blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  require(actual_blob==blob,'Changed product blob '+rel)
 return c

def validate_config(value,enabled=True):
 require(type(value) is dict and set(value)=={'enabled','product_sha','product_tree','purpose'},'Wrong control fields')
 require(type(value['enabled']) is bool and value['enabled'] is enabled,'Host control closed')
 require(value['product_sha']==BASE and value['product_tree']==TREE,'Wrong control product')
 require(value['purpose']=='Owned synthetic Photos input and intended JPEG boundary observation only; writer delivery and full lifecycle acceptance remain unproven','Changed control scope')

def commit_parents(raw):
 require(type(raw) is str and '\n\n' in raw,'Malformed HEAD commit object')
 headers=raw.split('\n\n',1)[0].splitlines()
 require(bool(headers) and re.fullmatch('tree [0-9a-f]{40}',headers[0]),'Malformed HEAD tree header')
 rows=[line for line in headers if line.startswith('parent')]
 require(all(re.fullmatch('parent [0-9a-f]{40}',line) for line in rows),'Malformed HEAD parent header')
 return [line[7:] for line in rows]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,timeout=20).strip()
def admit_sources(env=None,get_git=git,root=ROOT):
 env=os.environ if env is None else env
 route=current_route(env)
 require(env.get('GITHUB_RUN_ATTEMPT')=='1' and re.fullmatch('[1-9][0-9]*',env.get('GITHUB_RUN_ID','')),'Wrong run/attempt')
 validate_config(strict_json((root/CONFIG).read_bytes()))
 head=env['GITHUB_SHA']
 require(get_git('rev-parse','HEAD')==head,'Wrong HEAD')
 require(commit_parents(get_git('cat-file','-p','HEAD'))==[BASE],'Not a single product-parent control')
 require(get_git('rev-parse',BASE+'^{tree}')==TREE,'Wrong product tree')
 require(not get_git('status','--porcelain','--untracked-files=all'),'Dirty checkout')
 require(set(get_git('diff','--name-status',BASE,'HEAD','--').splitlines())=={'A\t'+p for p in ADDITIONS},'Unreviewed source delta')
 c=snapshot(root)
 expected='\n'.join(f'{mode} blob {blob}\t{path}' for path,mode,blob in c['git_files'])
 require(get_git('-c','core.quotepath=false','ls-tree','-r',BASE)==expected,'Manifest differs from actual product tree')
 expected_paths={p for p,_ in c['files']}|ADDITIONS
 require(set(get_git('-c','core.quotepath=false','ls-files').splitlines())==expected_paths,'Extra/missing tracked source')
 return c,{'source_sha':head,'tree':get_git('rev-parse','HEAD^{tree}'),'base_sha':BASE,'base_tree':TREE,
  'validation_route':route,'workflow_sha256':sha((root/route['workflow_path']).read_bytes()),'run_id':env['GITHUB_RUN_ID'],'run_attempt':1}
def verify_source(phase):
 require(sys.platform=='darwin' and sys.flags.optimize==0 and __debug__,'Normal Python on fresh Mac required')
 require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('DEVELOPER_DIR')=='/Applications/Xcode_27.app/Contents/Developer','Wrong native runner')
 require(phase in ('before','after'),'Wrong source phase')
 c,binding=admit_sources();temp=Path(os.environ['RUNNER_TEMP']).resolve();require(temp.is_dir() and str(temp)!='/','Invalid runner temp')
 receipt=dict(binding,phase=phase,unchanged_bound_files=962,reviewed_diagnostic_test_files={},reviewed_candidate_files={},allowed_changed_paths=sorted(ADDITIONS),complete_host_e2e=False)
 combined=dict(binding,phase=phase,file_count=962,source_fingerprint=c['fingerprint'],host_only_diagnostic=host_only_source_binding(c['files']))
 for name,value in [('mac-host-source-',receipt),('combined-source-',combined)]:
  (temp/(name+phase+'.json')).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
 print('FINAL_MAC_PHOTOS_SOURCE '+json.dumps(combined,sort_keys=True))
def main():
 require(sys.flags.optimize==0 and __debug__,'Final Mac Photos source refuses optimized Python')
 action=sys.argv[1] if len(sys.argv)==2 else ''
 require(action in ('admit','before','after'),'Wrong source action')
 verify_source('before' if action=='admit' else action)
if __name__=='__main__':main()
