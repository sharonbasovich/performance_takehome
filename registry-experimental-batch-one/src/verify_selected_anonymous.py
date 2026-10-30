"""Inactive whole-body anonymous selected-image verification; no registry writes."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time

CLIENT_SHA='3737fbbdd791e04e7a831640b681f3397a376498e80e2ad9b1b2d27296f239bc'
MAX_STDERR=1<<20
def need(ok,reason):
    if not ok:raise ValueError(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stop(child):
    if child.poll() is None:
        if os.name=='posix':
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        else:child.kill()

def download(binary,row,env,deadline,stderr_path,*,expected_raw=None):
    """Stream one exact object; retain only small metadata and bounded stderr."""
    need(0<row['bytes']<=8<<30,'bounded exact registry object')
    left=deadline-time.monotonic();need(left>0,'whole anonymous verification deadline exhausted')
    count=0;value=hashlib.sha256();retained=bytearray();reason=[];done=threading.Event();complete=False
    with Path(stderr_path).open('xb') as error:
        child=subprocess.Popen([str(binary),*row['argv']],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=error,env=env,start_new_session=os.name=='posix')
        def guard():
            while not done.wait(.1):
                if time.monotonic()>=deadline:reason.append('DEADLINE');stop(child);return
                if os.fstat(error.fileno()).st_size>MAX_STDERR:reason.append('STDERR_BOUND');stop(child);return
        thread=threading.Thread(target=guard,daemon=True);thread.start()
        try:
            while raw:=child.stdout.read(1<<20):
                # The retained prefix digest must describe exactly every byte
                # counted, including an overrun block that triggers refusal.
                count+=len(raw);value.update(raw);need(count<=row['bytes'],'object exceeded exact descriptor length')
                if expected_raw is not None:
                    need(row['bytes']<=256<<10,'only bounded metadata retained');retained.extend(raw)
            code=child.wait(timeout=max(.01,deadline-time.monotonic()))
            need(code==0 and not reason,'anonymous owned-client request incomplete')
            need(count==row['bytes'] and 'sha256:'+value.hexdigest()==row['digest'],'anonymous complete body digest/size differs')
            if expected_raw is not None:need(bytes(retained)==expected_raw,'anonymous metadata bytes differ from original graph')
            complete=True
        finally:
            stop(child);child.wait(timeout=5);child.stdout.close();done.set();thread.join(timeout=2);error.flush();os.fsync(error.fileno())
            progress={'role':row['role'],'expected_digest':row['digest'],'expected_bytes':row['bytes'],'bytes_received':count,'received_prefix_sha256':value.hexdigest(),'body_complete':complete,'stop_reasons':reason,'client_exit_code':child.returncode}
            with Path(str(stderr_path)+'.progress.json').open('x',encoding='utf-8') as stream:json.dump(progress,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    need(Path(stderr_path).stat().st_size<=MAX_STDERR,'bounded anonymous stderr')
    return {'role':row['role'],'digest':row['digest'],'bytes':count,'body_complete':True,'sha256_verified':True,'stderr_bytes':Path(stderr_path).stat().st_size,'stderr_sha256':sha(Path(stderr_path).read_bytes())}

def verify(root,out,binary,*,validation=None,download_fn=download):
    root=Path(root);out=Path(out)
    # The exact deployed publisher is already bound by the root marker. This
    # loader checks its marker pin before importing it; validate() then binds all
    # other deployment files and the independently preserved primitives.
    marker=json.loads((root/'PUBLICATION_APPROVAL.json').read_bytes());source=root/'src/publish_selected.py'
    need(sha(source.read_bytes())==marker['files']['src/publish_selected.py'],'root-pinned publisher differs')
    spec=importlib.util.spec_from_file_location('anonymous_selected_publisher',source);x=importlib.util.module_from_spec(spec);sys.modules[spec.name]=x;spec.loader.exec_module(x)
    approved=validation or x.validate(root);pub=approved['publisher'];ops=approved['operations']
    need(sha(Path(binary).read_bytes())==CLIENT_SHA,'pinned native Linux regctl required')
    need(out.is_absolute() and not out.exists() and out.parent.is_dir() and not any(p.is_symlink() for p in (out,*out.parents)),'new owned anonymous output')
    out.mkdir(mode=0o700)
    receipt={'kind':'ANONYMOUS_SELECTED_PLATFORM_GRAPH_GET_HASH_VERIFICATION','status':'IN_PROGRESS','reference':ops['immutable_reference'],'started_utc':datetime.now(timezone.utc).isoformat(),'approval_sha256':approved['approval_sha256'],'selection_sha256':ops['selection_sha256'],'local_or_account_credentials_read':False,'registry_login_used':False,'registry_mutations':False,'GPU_model_or_paid_resources':False,'layer_unpack_or_Docker_pull_executed':False,'objects':[]}
    attempt=pub.ReceiptAttempt(out/'receipt.json',receipt);code=0
    try:
        config=out/'empty-regctl.json';config.write_text('{}\n',encoding='utf-8');docker=out/'empty-docker';docker.mkdir(mode=0o700)
        env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','SSL_CERT_FILE','SSL_CERT_DIR')};env.update(REGCTL_CONFIG=str(config),DOCKER_CONFIG=str(docker))
        end=time.monotonic()+ops['anonymous_verification']['whole_seconds_maximum']
        for index,row in enumerate(ops['anonymous_verification']['objects']):
            attempt.record('OBJECT_GET_STARTED',{'role':row['role'],'digest':row['digest'],'bytes':row['bytes']})
            expected={'manifest':approved['manifest_raw'],'config':approved['config_raw']}.get(row['role'])
            result=download_fn(binary,row,env,end,out/(str(index).zfill(2)+'-'+row['role']+'.stderr.log'),expected_raw=expected)
            receipt['objects'].append(result);attempt.record('OBJECT_GET_VERIFIED',result)
        need(len(receipt['objects'])==25 and sum(row['role']=='layer' for row in receipt['objects'])==23,'complete graph only')
        need(config.read_bytes()==b'{}\n' and not any(docker.iterdir()),'empty no-login anonymous client remains empty')
        receipt.update(status='ANONYMOUS_COMPLETE_PLATFORM_GRAPH_DOWNLOADED_AND_HASHED',graph_bytes=sum(row['bytes'] for row in receipt['objects']),layers_verified=23,objects_verified=25,completed_utc=datetime.now(timezone.utc).isoformat())
    except BaseException as exc:
        receipt.update(status='INCOMPLETE_ANONYMOUS_GRAPH_VERIFICATION',error_type=type(exc).__name__,completed_objects=len(receipt['objects']));attempt.record('VERIFICATION_FAILED',receipt);code=65
    finally:
        try:attempt.finish(receipt)
        finally:attempt.close()
    return code,receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path);p.add_argument('--out',type=Path);p.add_argument('--regctl',type=Path);p.add_argument('--execute-read-only',action='store_true');a=p.parse_args()
    if not a.execute_read_only:print('{"inactive":true,"credential_reads":0,"network_actions":0}');return 0
    need(a.root and a.out and a.regctl,'exact root, new output and pinned client required')
    code,receipt=verify(a.root,a.out,a.regctl);print(json.dumps(receipt));return code
if __name__=='__main__':raise SystemExit(main())
