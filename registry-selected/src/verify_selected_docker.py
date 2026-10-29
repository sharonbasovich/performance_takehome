"""Inactive empty-config anonymous Docker pull/inspect/owned CPU-help proof."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

MAX_LOG=4<<20
def need(ok,reason):
    if not ok:raise ValueError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def inspect(raw):
    value=json.loads(raw);need(isinstance(value,list) and len(value)==1,'one exact Docker object');return value[0]
def missing(row,err):return row['exit_code']==1 and row['stop_reason'] is None and b'No such container:' in err
def image_matches(actual,config,ref,config_digest):
    # Classic Docker exposes the config digest as Id; the containerd image store
    # can expose the pulled platform-manifest digest. Bind either observed view
    # to the already hash-verified graph, never to a guessed or unrelated ID.
    need(re.fullmatch('sha256:[0-9a-f]{64}',config_digest or ''),'exact raw selected config digest required')
    bound_ids={config_digest}
    platform_digest=ref.rsplit('@',1)[-1]
    if re.fullmatch('sha256:[0-9a-f]{64}',platform_digest):bound_ids.add(platform_digest)
    need(actual['Id'] in bound_ids,'actual Docker image ID is neither exact config nor bound platform digest')
    need(actual['Architecture']=='amd64' and actual['Os']=='linux' and actual['RootFS']['Type']=='layers' and actual['RootFS']['Layers']==config['rootfs']['diff_ids'] and ref in actual.get('RepoDigests',[]),'actual immutable platform and23diffIDs agree')
    legacy=None
    for key,value in config['config'].items():
        observed=actual['Config'].get(key)
        if key=='ArgsEscaped' and value is True and observed is False:
            legacy={'canonical_raw':True,'Docker_Linux_view':False,'scope':'legacy Windows-only escaping view; raw canonical config independently hash-verified'};continue
        need(observed==value,'actual config differs: '+key)
    return legacy
def owned_help(obj,ref,name,labels):
    need(obj['Name']=='/'+name and obj['Config']['Image']==ref and all(obj['Config']['Labels'].get(k)==v for k,v in labels.items()) and re.fullmatch('[0-9a-f]{64}',obj['Id']),'exact ownership before removal')
    return obj['Id']
def verify(root,out,anonymous,anonymous_sha):
    root=Path(root);out=Path(out)
    marker=json.loads((root/'PUBLICATION_APPROVAL.json').read_bytes());source=root/'src/publish_selected.py'
    need(sha(source.read_bytes())==marker['files']['src/publish_selected.py'],'root-pinned publisher differs')
    spec=importlib.util.spec_from_file_location('docker_selected_publisher',source);x=importlib.util.module_from_spec(spec);sys.modules[spec.name]=x;spec.loader.exec_module(x);approved=x.validate(root);pub=approved['publisher'];ops=approved['operations'];ref=ops['immutable_reference']
    need(os.name=='posix','native Linux Docker environment required')
    anonymous_raw=x.read(anonymous,1<<20);need(sha(anonymous_raw)==anonymous_sha,'independent full anonymous receipt pin')
    proof=pub.strict_json(anonymous_raw)
    need(proof['status']=='ANONYMOUS_COMPLETE_PLATFORM_GRAPH_DOWNLOADED_AND_HASHED' and proof['reference']==ref and proof['layers_verified']==23 and proof['objects_verified']==25 and proof['local_or_account_credentials_read'] is False and proof['registry_login_used'] is False and proof['registry_mutations'] is False,'complete exact anonymous graph proof required')
    expected=[(row['role'],row['digest'],row['bytes']) for row in ops['anonymous_verification']['objects']]
    need([(row['role'],row['digest'],row['bytes']) for row in proof['objects']]==expected and all(row['body_complete'] is True and row['sha256_verified'] is True for row in proof['objects']),'every complete object identity required')
    config=pub.strict_json(approved['config_raw'])
    need(out.is_absolute() and not out.exists() and out.parent.is_dir() and not any(p.is_symlink() for p in (out,*out.parents)),'new owned Docker output');out.mkdir(mode=0o700)
    empty=out/'empty-docker-config';empty.mkdir(mode=0o700);(empty/'config.json').write_text('{}\n',encoding='utf-8')
    env={'PATH':'/usr/bin:/bin','DOCKER_HOST':'unix:///var/run/docker.sock','DOCKER_CONFIG':str(empty)};docker=['/usr/bin/docker','--config',str(empty)]
    nonce=uuid4().hex;name='abstract-selected-help-'+nonce;labels={'abstract.takehome.proof.kind':'anonymous-selected-cpu-help','abstract.takehome.proof.run_id':nonce};help_started=False
    receipt={'kind':'ANONYMOUS_SELECTED_DOCKER_CPU_PROOF','status':'IN_PROGRESS','started_utc':utc(),'reference':ref,'anonymous_receipt_sha256':anonymous_sha,'account_credentials_read':False,'registry_login_used':False,'GPU_or_model_mounts':False,'container_name':name,'container_labels':labels,'phases':[],'cleanup':{'status':'NO_CONTAINER_CREATED_BY_ATTEMPT'}}
    attempt=pub.ReceiptAttempt(out/'receipt.json',receipt);code=0
    def phase(role,args,timeout):
        row={'phase':role,'argv':args,'started_utc':utc(),'timeout_seconds':timeout};attempt.record('PHASE_STARTED',row);reason=None;start=time.monotonic()
        stdout=out/(role+'.stdout.log');stderr=out/(role+'.stderr.log')
        with stdout.open('xb') as so,stderr.open('xb') as se:
            child=subprocess.Popen(docker+args,stdin=subprocess.DEVNULL,stdout=so,stderr=se,env=env,start_new_session=True)
            try:
                while child.poll() is None:
                    if time.monotonic()-start>=timeout:reason='OWNED_CLIENT_TIMEOUT'
                    if max(os.fstat(so.fileno()).st_size,os.fstat(se.fileno()).st_size)>MAX_LOG:reason='LOG_BOUND'
                    if reason:os.killpg(child.pid,signal.SIGKILL);break
                    time.sleep(.2)
                row.update(exit_code=child.wait(timeout=5),stop_reason=reason,elapsed_seconds=time.monotonic()-start,finished_utc=utc())
            finally:
                if child.poll() is None:
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait(timeout=5)
                so.flush();os.fsync(so.fileno());se.flush();os.fsync(se.fileno())
        raw=stdout.read_bytes();err=stderr.read_bytes();need(max(len(raw),len(err))<=MAX_LOG,'bounded owned Docker output');row.update(stdout_sha256=sha(raw),stderr_sha256=sha(err));receipt['phases'].append(row);attempt.record('PHASE_FINISHED',row);return row,raw,err
    try:
        usage=shutil.disk_usage('/var/lib/docker');host=shutil.disk_usage('/');need(min(usage.free,host.free)>=26<<30,'26GiB Docker and host free-space requirement');receipt['docker_free_bytes_before']=usage.free;receipt['host_free_bytes_before']=host.free;receipt['minimum_free_bytes']=26<<30
        row,_,_=phase('anonymous-pull',['pull','--platform','linux/amd64',ref],1800);need(row['exit_code']==0 and row['stop_reason'] is None,'bounded anonymous Docker pull incomplete')
        row,raw,_=phase('pulled-image-inspect',['image','inspect',ref],30);need(row['exit_code']==0 and row['stop_reason'] is None,'exact image inspect failed');actual=inspect(raw)
        legacy=image_matches(actual,config,ref,approved['config_digest'])
        if legacy:receipt['legacy_Windows_ArgsEscaped_view']=legacy
        receipt['actual_image_id']=actual['Id']
        receipt['actual_image_id_kind']='raw-config-digest' if actual['Id']==approved['config_digest'] else 'selected-platform-manifest-digest'
        receipt['verified_identity_linkage']={'raw_config_digest':approved['config_digest'],'platform_manifest_digest':approved['manifest_digest'],'immutable_repository_reference':ref}
        row,_,err=phase('help-name-before',['container','inspect',name],15);need(missing(row,err),'fresh exact owned help name not absent')
        args=['run','--pull=never','--rm','--name',name,'--cidfile',str(out/'help.cid'),'--network=none','--cap-drop=ALL','--security-opt=no-new-privileges']
        for key,value in labels.items():args+=['--label',key+'='+value]
        help_started=True;row,raw,err=phase('cpu-help',args+[ref,'--help'],60);need(row['exit_code']==0 and row['stop_reason'] is None and b'--model' in raw+err,'bounded CPU help failed')
        receipt.update(status='ANONYMOUS_IMMUTABLE_DOCKER_PULL_INSPECT_CPU_HELP_PASS',completed_utc=utc())
    except BaseException as exc:
        receipt.update(status='INCOMPLETE_DOCKER_CPU_PROOF',error_type=type(exc).__name__);attempt.record('PROOF_FAILED',receipt);code=65
    finally:
        if help_started:
            try:
                row,raw,err=phase('help-cleanup-inspect',['container','inspect',name],15)
                if missing(row,err):receipt['cleanup']={'status':'EXACT_OWNED_HELP_NAME_ABSENT','observed_utc':utc()}
                else:
                    need(row['exit_code']==0 and row['stop_reason'] is None,'owned help inspect inconclusive');obj=inspect(raw)
                    cid=owned_help(obj,ref,name,labels)
                    row,_,_=phase('help-owned-remove',['container','rm','--force',cid],15);need(row['exit_code']==0 and row['stop_reason'] is None,'owned cleanup failed')
                    row,_,err=phase('help-owned-absence',['container','inspect',cid],15);need(missing(row,err),'exact owned CID absence unconfirmed');receipt['cleanup']={'status':'EXACT_LABEL_AUTHENTICATED_HELP_CID_REMOVED_AND_ABSENT','cid':cid,'observed_utc':utc()}
            except BaseException as exc:receipt.update(status='INCOMPLETE_DOCKER_CPU_PROOF',cleanup={'status':'CLEANUP_UNCONFIRMED','error_type':type(exc).__name__});code=65
        if (empty/'config.json').read_bytes()!=b'{}\n':receipt['status']='INCOMPLETE_DOCKER_CPU_PROOF';code=65
        try:attempt.finish(receipt)
        finally:attempt.close()
    return code,receipt
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path);p.add_argument('--out',type=Path);p.add_argument('--anonymous-receipt',type=Path);p.add_argument('--anonymous-receipt-sha256');p.add_argument('--execute-read-only',action='store_true');a=p.parse_args()
    if not a.execute_read_only:print('{"inactive":true,"credential_reads":0,"network_or_Docker_actions":0}');return 0
    need(a.root and a.out and a.anonymous_receipt and re.fullmatch('[0-9a-f]{64}',a.anonymous_receipt_sha256 or ''),'exact root and independent full anonymous receipt pin required')
    code,receipt=verify(a.root,a.out,a.anonymous_receipt,a.anonymous_receipt_sha256);print(json.dumps(receipt));return code
if __name__=='__main__':raise SystemExit(main())
