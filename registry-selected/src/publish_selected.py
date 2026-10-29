"""Inactive exact selected-image publisher draft; requires actual root-pinned input.

Uses only the preserved RegctlClient and ReceiptAttempt primitives. The historical
publisher's baseline-only publish/selection functions are deliberately not called.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
PRIMITIVE_SHA='3853995b1490789579b532df3b0e237d42c4102d0c4503b100d124f9e4b9a531'
GENERATOR_SHA='5ef0db8491b912a25ebea9a3af174939d8af0d2c27af121db7d754b38de66c9a'
BASE_CONFIG_SHA='0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f'
AUTH_SHA='0dd09f93651f373fccb10aa4a46b8d532459350b365474097a138be8221b7211'
DEST='ghcr.io/sharonbasovich/performance_takehome-task2-llmd'

def need(ok,reason):
    if not ok:raise ValueError(reason)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def read(path,cap=2<<20):
    path=Path(path)
    need(path.is_file() and not any(x.is_symlink() for x in (path,*path.parents)) and 0<path.stat().st_size<=cap,'bounded regular pinned input')
    raw=path.read_bytes();need(0<len(raw)<=cap,'complete bounded input');return raw
def load_module(name,path,pin):
    need(digest(read(path))==pin,'reviewed primitive source differs')
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value
def primitives(root):return load_module('selected_publication_primitives',root/'src/preserved_primitives.py',PRIMITIVE_SHA)
def semantics(root):return load_module('selected_publication_semantics',root/'src/generation_semantics.py',GENERATOR_SHA)

def validate(root,*,fixture=False):
    root=Path(root).resolve();pub=primitives(root);gen=semantics(root)
    marker=pub.strict_json(read(root/'PUBLICATION_APPROVAL.json'))
    need(set(marker)=={'version','kind','decision','existing_human_authorization_sha256','generation_receipt_sha256','immutable_reference','files'},'exact root marker fields')
    need(marker['version']==1 and marker['kind']=='ROOT_REVIEWED_ACTUAL_SELECTED_TASK2_PUBLICATION' and marker['decision']=='APPROVED_ONE_EXACT_PUBLICATION_AND_ANONYMOUS_PROOF','separate root approval required')
    need(marker['existing_human_authorization_sha256']==AUTH_SHA and re.fullmatch('[0-9a-f]{64}',marker['generation_receipt_sha256'] or ''),'existing authorization and actual generator receipt pin')
    files=marker['files'];need(isinstance(files,dict) and 6<=len(files)<=100,'complete reviewed small-file deployment')
    required={'operations.json'}
    for group in ('src','public','workflow'):
        directory=root/group;need(directory.is_dir(),'complete exact deployment layout')
        for path in directory.rglob('*'):
            need(not path.is_symlink(),'redirected deployment refused')
            if path.is_file():required.add(path.relative_to(root).as_posix())
    need(set(files)==required,'root marker must bind every deployed source/public/workflow byte')
    for name,pin in files.items():
        need(isinstance(name,str) and not Path(name).is_absolute() and '..' not in Path(name).parts and re.fullmatch('[0-9a-f]{64}',pin or ''),'safe reviewed file identity')
        need(digest(read(root/name))==pin,'reviewed file bytes differ')
    need(files.get('src/publish_selected.py')==digest(read(Path(__file__))), 'actual loaded publisher must be the reviewed deployment source')
    selection=pub.strict_json(read(root/'public/evidence/selection.json'))
    need(selection['kind']=='ACTUAL_SELECTED_PLATFORM_PUBLICATION_HANDOFF' and selection['status']=='MEASURED_SETTLED_LAST_GOOD_PENDING_PUBLICATION' and (fixture or selection['fixture'] is False),'actual settled selection only; fixture promotion refused')
    need(selection['publication_state']=='NOT_EXECUTED_BY_GENERATOR' and selection['source']['original_selected_context_file'] is True and selection['source']['reconstructed'] is False,'actual original selected source required')
    need(selection['fresh_revalidation']['raw_report_retained'] is True and selection['fresh_revalidation']['traces_retained'] is True and selection['fresh_revalidation']['requests']==30 and selection['fresh_revalidation']['official_grade'] is False,'fresh retained30 evidence requirement')
    need(selection['optimized_gain_claimed'] is False and selection['weights_in_image'] is False,'publication cannot manufacture optimization claims or contain weights')
    cfg=selection['image']['config'];md=selection['image']['platform_manifest']
    need(all(re.fullmatch('sha256:[0-9a-f]{64}',x) for x in (cfg,md)),'exact actual platform/config digests')
    config_raw=read(root/'public/delivery/metadata/blobs/sha256'/cfg[7:],256<<10)
    manifest_raw=read(root/'public/delivery/metadata/blobs/sha256'/md[7:],256<<10)
    config,manifest=(pub.strict_json(x) for x in (config_raw,manifest_raw))
    need('sha256:'+digest(config_raw)==cfg and 'sha256:'+digest(manifest_raw)==md,'exact raw graph identities')
    need(config['os']=='linux' and config['architecture']=='amd64' and config['rootfs']['type']=='layers','selected linux/amd64 image')
    need(manifest['mediaType']==pub.MT_MANIFEST and manifest['config']['mediaType']==pub.MT_CONFIG and manifest['config']['digest']==cfg and manifest['config']['size']==len(config_raw),'actual config descriptor agrees')
    base_raw=read(root/'public/delivery/base-manifest.json',256<<10);base=pub.strict_json(base_raw)
    descriptors=lambda rows:[(x['digest'],x['size'],x['mediaType']) for x in rows]
    need(digest(base_raw)==gen.BASE_SHA and len(manifest['layers'])==23 and descriptors(manifest['layers'])==descriptors(base['layers']),'exact inherited public23 descriptors only')
    baseline_raw=read(root/'src/baseline-config.json',256<<10)
    need(digest(baseline_raw)==BASE_CONFIG_SHA,'historically verified baseline config bytes')
    prior=pub.strict_json(baseline_raw)
    need(config['rootfs']==prior['rootfs'],'same exact23 inherited diffIDs')
    dockerfile=read(root/'public/delivery/selected.Dockerfile',64<<10)
    need(digest(dockerfile)==selection['source']['dockerfile_sha256'],'exact selected Dockerfile')
    gen.dockerfile_runtime(dockerfile,config,prior)
    operations=pub.strict_json(read(root/'operations.json'))
    expected=gen.plan_operations(manifest,config_raw,manifest_raw,False)
    expected.update(selection_sha256=digest(read(root/'public/evidence/selection.json')),source_generator_sha256=GENERATOR_SHA)
    need(operations==expected,'exact generated operations only; arbitrary argv refused')
    need(marker['immutable_reference']==DEST+'@'+md==operations['immutable_reference']==selection['destination']['by_digest'],'one approved immutable identity')
    need(selection['destination']['registry']==DEST and selection['destination']['mutable_tag']==operations['mutable_tag'],'fixed public destination/convenience tag')
    return {'publisher':pub,'operations':operations,'selection':selection,'manifest':manifest,'config_raw':config_raw,'manifest_raw':manifest_raw,'config_digest':cfg,'manifest_digest':md,'approval_sha256':digest(read(root/'PUBLICATION_APPROVAL.json'))}

def publish(root,out,binary,*,client_factory=None,token=None,actor=None,fixture=False):
    approved=validate(root,fixture=fixture);pub=approved['publisher'];ops=approved['operations'];root=Path(root);out=Path(out)
    receipt={'kind':'EXACT_SELECTED_PLATFORM_PUBLICATION','status':'IN_PROGRESS','started_utc':utc(),'reference':ops['immutable_reference'],'approval_sha256':approved['approval_sha256'],'selection_sha256':ops['selection_sha256'],'registry_login_scope':'existing job ephemeral token only','original_index_published':False,'tag_is_mutable':True,'steps':[],'anonymous_access_verified':False,'optimization_claimed':False}
    attempt=pub.ReceiptAttempt(out,receipt);client=None;login_attempted=False;exit_code=0
    try:
        attempt.record('CLIENT_CONSTRUCTION_STARTED',{'reference':ops['immutable_reference']})
        client=(client_factory or pub.RegctlClient)(Path(binary))
        need(token and actor,'existing ephemeral job token and actor required')
        need(re.fullmatch('[A-Za-z0-9-]{1,100}',actor) is not None,'ordinary GitHub actor identity')
        attempt.record('EPHEMERAL_LOGIN_STARTED',{'token_retained':False})
        login_attempted=True
        client._run('registry','login','ghcr.io','--user',actor,'--pass-stdin',stdin=token.encode())
        attempt.record('EPHEMERAL_LOGIN_COMPLETED',{'token_retained':False})
        for row in approved['manifest']['layers']:
            descriptor={'kind':'inherited_layer','digest':row['digest'],'bytes':row['size']};attempt.record('LAYER_STARTED',descriptor)
            need(client.blob_exists(DEST,row['digest']),'inherited public blob missing; metadata-only publication refuses layer copy')
            receipt['steps'].append(descriptor);attempt.record('LAYER_CONFIRMED',descriptor)
        for event,operation in [('CONFIG_PUT',lambda:client.put_blob(DEST,approved['config_raw'],approved['config_digest'])),('PLATFORM_PUT',lambda:client.put_manifest(DEST,approved['manifest_raw'],approved['manifest']['mediaType'],approved['manifest_digest'])),('TAG_PUT',lambda:client.put_manifest(DEST,approved['manifest_raw'],approved['manifest']['mediaType'],ops['mutable_tag']))]:
            attempt.record(event+'_STARTED',{'reference':ops['immutable_reference']});operation();attempt.record(event+'_COMPLETED',{'reference':ops['immutable_reference']})
        actual=client.head_manifest(DEST,approved['manifest_digest']);tag=client.head_manifest(DEST,ops['mutable_tag'])
        need(actual==tag==approved['manifest_digest'],'exact authenticated manifest/tag readback')
        receipt.update(status='SELECTED_PLATFORM_PUBLISHED_AND_AUTHENTICATED_READBACK',readback_manifest_digest=actual,readback_tag_digest=tag,completed_utc=utc())
    except BaseException as exc:
        receipt.update(status='INCOMPLETE_RECONCILE_ATTEMPT_BEFORE_RETRY',error_type=type(exc).__name__,failed_utc=utc());attempt.record('PUBLICATION_FAILED',receipt);exit_code=65
    finally:
        if client is not None and login_attempted:
            try:client._run('registry','logout','ghcr.io');receipt['ephemeral_logout_completed']=True
            except BaseException as exc:receipt.update(status='INCOMPLETE_RECONCILE_ATTEMPT_BEFORE_RETRY',ephemeral_logout_completed=False,logout_error_type=type(exc).__name__);exit_code=65
        try:attempt.finish(receipt)
        finally:attempt.close()
    return exit_code,receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path);parser.add_argument('--out',type=Path);parser.add_argument('--regctl',type=Path)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--check-only',action='store_true');mode.add_argument('--publish',action='store_true');args=parser.parse_args()
    if not(args.check_only or args.publish):print('{"inactive":true,"credential_reads":0,"registry_actions":0}');return 0
    need(args.root is not None,'exact reviewed deployment root required')
    if args.check_only:
        result=validate(args.root);print(json.dumps({'status':'ROOT_MARKER_AND_ACTUAL_SELECTED_INPUTS_VERIFIED','reference':result['operations']['immutable_reference'],'approval_sha256':result['approval_sha256'],'registry_actions':0}));return 0
    need(args.out is not None and args.regctl is not None,'exclusive receipt and pinned client required')
    code,receipt=publish(args.root,args.out,args.regctl,token=os.environ.get('GHCR_TOKEN'),actor=os.environ.get('GITHUB_ACTOR'))
    print(json.dumps(receipt));return code
if __name__=='__main__':raise SystemExit(main())
