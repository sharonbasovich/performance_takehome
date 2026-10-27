"""Verify every public baseline image byte anonymously; no login, upload or Docker unpack."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

PUBLISHER_SHA='3853995b1490789579b532df3b0e237d42c4102d0c4503b100d124f9e4b9a531'
CLIENT_SHA='3737fbbdd791e04e7a831640b681f3397a376498e80e2ad9b1b2d27296f239bc'
TARGET='ghcr.io/sharonbasovich/performance_takehome-task2-llmd'
MANIFEST='sha256:7db01160c57479b9d608b7c2e6fc4e6b5d438e53eb4d44dc9f3ab0441d1bb20d'
MAX_STDERR=65536
WHOLE_SECONDS=1200

def need(ok,message):
    if not ok: raise ValueError(message)
def utc(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024**2): result.update(chunk)
    return result.hexdigest()
def publisher(root):
    path=root/'src/publish_baseline_config_only.py'
    need(path.is_file() and not path.is_symlink() and sha(path)==PUBLISHER_SHA,'pinned public publisher required')
    spec=importlib.util.spec_from_file_location('accepted_public_publisher',path)
    result=importlib.util.module_from_spec(spec);sys.modules[spec.name]=result;spec.loader.exec_module(result)
    return result

class ObjectFailure(Exception):
    def __init__(self,row):
        self.row=row
        super().__init__(row.get('reason','anonymous object GET failed'))

def get_object(client,argv,descriptor,env,deadline,stderr_path,keep=False):
    """Stream only stdout bytes, retain complete bounded stderr and truthful partial hashes."""
    need(0<=descriptor['bytes']<=8*1024**3,'bounded exact descriptor required')
    need(time.monotonic()<deadline,'whole anonymous verification deadline exhausted')
    row={**descriptor,'started_utc':utc(),'body_complete':False,'sha256_verified':False}
    digest=hashlib.sha256();count=0;retained=bytearray();reason=None
    stop_event=threading.Event();stop_lock=threading.Lock();stop_reason=[None]
    with stderr_path.open('xb') as stderr:
        child=subprocess.Popen([str(client),*argv],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                               stderr=stderr,env=env,start_new_session=True)
        def cancel(why):
            with stop_lock:
                if stop_reason[0] is None: stop_reason[0]=why
                if child.poll() is None:
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
        def monitor():
            while not stop_event.wait(.05):
                if child.poll() is not None: return
                if time.monotonic()>=deadline: cancel('WHOLE_1200_SECOND_DEADLINE');return
                if os.fstat(stderr.fileno()).st_size>MAX_STDERR: cancel('STDERR_BOUND_EXCEEDED');return
        watcher=threading.Thread(target=monitor,name='owned-anonymous-get-monitor',daemon=True)
        watcher.start()
        try:
            while chunk:=child.stdout.read(1024**2):
                count+=len(chunk);digest.update(chunk)
                if count>descriptor['bytes']: raise ValueError('body exceeds exact descriptor')
                if keep: retained.extend(chunk)
            code=child.wait(timeout=max(.01,min(5,deadline-time.monotonic())))
            if stop_reason[0]: raise ValueError(stop_reason[0])
            need(code==0,'anonymous registry client exited nonzero')
            need(os.fstat(stderr.fileno()).st_size<=MAX_STDERR,'stderr bound exceeded after client exit')
            need(count==descriptor['bytes'] and 'sha256:'+digest.hexdigest()==descriptor['digest'],
                 'anonymous object byte count or digest mismatch')
            row.update(body_complete=True,sha256_verified=True)
        except Exception as exc:
            reason=type(exc).__name__+': '+str(exc)
        finally:
            if child.poll() is None: cancel('OWNED_CLIENT_STOP_ON_INCOMPLETE_GET')
            try: code=child.wait(timeout=5)
            finally:
                stop_event.set();watcher.join(timeout=2)
                child.stdout.close();stderr.flush();os.fsync(stderr.fileno())
        row.update(finished_utc=utc(),received_bytes=count,received_sha256=digest.hexdigest(),
                   exit_code=code,stop_reason=stop_reason[0],
                   stderr={'path':str(stderr_path),'bytes':stderr_path.stat().st_size,'sha256':sha(stderr_path)})
        if reason:
            row['reason']=reason
            raise ObjectFailure(row)
    return row,bytes(retained) if keep else None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--publisher-root',type=Path,default=Path('registry-publisher'))
    p.add_argument('--regctl',type=Path)
    p.add_argument('--out',type=Path,required=True)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--inspect-only',action='store_true')
    modes.add_argument('--execute-read-only',action='store_true')
    args=p.parse_args()
    if not(args.inspect_only or args.execute_read_only):
        print(json.dumps({'inactive':True,'network_calls':0,'credential_reads':0}));return 0
    root=args.publisher_root.resolve()
    pub=publisher(root)
    bundle=pub.load_bundle(root/'delivery/metadata',root/'delivery/base-manifest.json',
                          root/'delivery/selected.Dockerfile',root/'evidence/selection.json')
    validation=pub.validate_bundle(bundle)
    need(pub.DESTINATION==TARGET and pub.EXPECTED_MANIFEST==MANIFEST,'exact approved image required')
    manifest=json.loads(bundle.manifest)
    need(len(manifest['layers'])==23 and sum(row['size'] for row in manifest['layers'])==5923157643,
         'exact accepted23-layer graph required')
    if args.inspect_only:
        print(json.dumps({'status':'PASS_OFFLINE_PUBLIC_METADATA_INSPECTION','publisher_sha256':PUBLISHER_SHA,
                          'validation':validation,'network_calls':0,'credential_reads':0,
                          'objects':25,'graph_bytes':5923157643+len(bundle.config)+len(bundle.manifest)}));return 0
    need(os.name=='posix' and args.regctl is not None,'native Linux pinned client required')
    client=args.regctl.resolve()
    need(client.is_file() and not client.is_symlink() and sha(client)==CLIENT_SHA,'pinned official Linux regctl required')
    args.out=args.out.resolve();args.out.mkdir(mode=0o700,exist_ok=False)
    stderr_root=args.out/'stderr';stderr_root.mkdir(mode=0o700)
    receipt={'kind':'ANONYMOUS_CURRENT_SCHEMA_PLATFORM_GRAPH_GET_HASH_VERIFICATION',
             'status':'IN_PROGRESS','started_utc':utc(),'reference':TARGET+'@'+MANIFEST,
             'destination':TARGET,'publisher_sha256':PUBLISHER_SHA,'client_sha256':CLIENT_SHA,
             'metadata_validation':validation,'local_or_account_credentials_read':False,
             'registry_login_used':False,'registry_mutations':False,'GPU_model_or_paid_resources':False,
             'layer_unpack_or_Docker_pull_executed':False,'whole_deadline_seconds':WHOLE_SECONDS,'objects':[]}
    attempt=pub.ReceiptAttempt(args.out/'receipt.json',receipt)
    begun=time.monotonic();deadline=begun+WHOLE_SECONDS;exit_code=0
    try:
        with tempfile.TemporaryDirectory(prefix='anonymous-client-',dir=args.out) as anon:
            config=Path(anon)/'regctl.json';config.write_text('{}\n',encoding='utf-8')
            docker=Path(anon)/'docker';docker.mkdir(mode=0o700)
            env={'PATH':'/usr/bin:/bin','REGCTL_CONFIG':str(config),'DOCKER_CONFIG':str(docker),
                 'SSL_CERT_FILE':'/etc/ssl/certs/ca-certificates.crt'}
            objects=[('manifest',MANIFEST,len(bundle.manifest),
                      ['manifest','get',TARGET+'@'+MANIFEST,'--format','raw-body'],bundle.manifest),
                     ('config',pub.EXPECTED_CONFIG,len(bundle.config),
                      ['blob','get',TARGET,pub.EXPECTED_CONFIG],bundle.config)]
            objects += [('layer',row['digest'],row['size'],['blob','get',TARGET,row['digest']],None)
                        for row in manifest['layers']]
            for number,(role,digest,size,argv,expected) in enumerate(objects):
                descriptor={'role':role,'digest':digest,'bytes':size}
                attempt.record('OBJECT_GET_STARTED',descriptor)
                log=stderr_root/(str(number).zfill(2)+'-'+role+'-'+digest[7:]+'.log')
                try: row,raw=get_object(client,argv,descriptor,env,deadline,log,expected is not None)
                except ObjectFailure as exc:
                    receipt['failed_object']=exc.row;attempt.record('OBJECT_GET_INCOMPLETE',exc.row);raise
                if expected is not None:
                    need(raw==expected,'raw anonymous metadata differs from accepted bytes')
                    with (args.out/(role+'.raw.json')).open('xb') as stream: stream.write(raw)
                receipt['objects'].append({**descriptor,'body_complete':True,'sha256_verified':True,
                                           'received_bytes':row['received_bytes'],'received_sha256':row['received_sha256'],
                                           'exit_code':row['exit_code'],'stderr':row['stderr']})
                attempt.record('OBJECT_GET_VERIFIED',receipt['objects'][-1])
            need(config.read_bytes()==b'{}\n' and not any(docker.iterdir()),'empty anonymous client config changed')
            receipt.update(status='ANONYMOUS_COMPLETE_PLATFORM_GRAPH_DOWNLOADED_AND_HASHED',
                           completed_utc=utc(),objects_verified=25,layers_verified=23,
                           graph_bytes=sum(row['bytes'] for row in receipt['objects']),
                           elapsed_seconds=time.monotonic()-begun)
    except Exception as exc:
        receipt.update(status='INCOMPLETE_ANONYMOUS_GRAPH_VERIFICATION',failed_utc=utc(),
                       error_type=type(exc).__name__,error=str(exc),completed_objects=len(receipt['objects']),
                       elapsed_seconds=time.monotonic()-begun)
        attempt.record('VERIFICATION_FAILED',receipt);exit_code=65
    finally:
        try: attempt.finish(receipt)
        finally: attempt.close()
    print(json.dumps({'status':receipt['status'],'completed_objects':len(receipt['objects']),
                      'receipt_sha256':sha(args.out/'receipt.json'),'elapsed_seconds':receipt['elapsed_seconds']}))
    return exit_code

if __name__=='__main__':raise SystemExit(main())
