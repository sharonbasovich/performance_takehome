"""Inactive offline handoff for a real selected Task2 immutable platform image.

Reads only small retained proofs/config graph/source and fresh report. Emits raw
public metadata plus exact publication/anonymous-pull operation inputs. It never
logs in, invokes a registry/Docker client, writes Git, approves or publishes.
"""
from pathlib import Path
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
import shlex
import sys

ROOT=Path(__file__).resolve().parent
DEST='ghcr.io/sharonbasovich/performance_takehome-task2-llmd'
SOURCE='docker.io/zmlai/llmd'
BASE_SHA='0a2cd01a2e53c78934a8cfef66f8668da7666be4954a5d18b72df089c54ea34f'
META_SHA='8fe6a2120bcdaa74deee00088633f0805149358c8d2e69f3410e0031d4bd7bc1'
HELPER_SHA='0f5b6bebc940b5bb547c89168c75e92c147cd0c5fe1cebc362ec0ca8cc86a67d'
HARNESS='99c006dfeb1fae2c2e33f3c066927ee43bf056ec'
CLIENT_SHA='3737fbbdd791e04e7a831640b681f3397a376498e80e2ad9b1b2d27296f239bc'
MODEL={'repository':'Qwen/Qwen3.6-27B','revision':'6a9e13bd6fc8f0983b9b99948120bc37f49c13e9'}


def need(ok,reason):
    if not ok:raise ValueError(reason)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def encoded(value):return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def read(path,cap=16<<20):
    path=Path(path);need(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)) and 0<path.stat().st_size<=cap,'bounded regular retained source/proof')
    raw=path.read_bytes();need(0<len(raw)<=cap,'complete retained source/proof bound');return raw


def checked(row,cap=16<<20):
    need(set(row)=={'path','sha256'},'independently pinned proof descriptor');raw=read(row['path'],cap);need(digest(raw)==row['sha256'],'retained proof SHA differs');return raw


def module(name,path,pin):
    need(digest(read(path,2<<20))==pin,'frozen semantic validator source')
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value


def keep(path,raw):
    path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    need(not any(p.is_symlink() for p in (path,*path.parents)),'new nonredirected packet file')
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600),'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return {'bytes':len(raw),'sha256':digest(raw)}


def dockerfile_runtime(raw,config,prior_config):
    """Exact copied source must explain the actual raw runtime configuration."""
    need(0<len(raw)<=64<<10,'bounded selected Dockerfile')
    instructions={};env={}
    for line in raw.decode('utf-8').splitlines():
        line=line.strip()
        # Conservative pilot grammar: reserved directive-looking comments anywhere.
        need(re.match(r'#\s*(?:syntax|escape|check)\s*=',line,re.IGNORECASE) is None,'reserved Dockerfile parser directives forbidden')
        if not line or line.startswith('#'):continue
        head,sep,body=line.partition(' ');head=head.upper();need(sep and head in {'ARG','FROM','ENTRYPOINT','CMD','ENV'},'only reviewed configuration-only Dockerfile instructions')
        if head=='ENV':
            values=shlex.split(body);need(len(values)==1 and '=' in values[0],'one exact empty telemetry ENV per instruction')
            key,value=values[0].split('=',1);need(key in {'LLMD_USAGE_STATS_ENDPOINT','LLMD_POSTHOG_TOKEN'} and value=='' and key not in env,'only existing telemetry variables may be blanked');env[key]=value
        else:
            need(head not in instructions,'one original ARG/FROM/ENTRYPOINT/CMD');instructions[head]=body
    need(set(instructions)=={'ARG','FROM','ENTRYPOINT','CMD'} and instructions['ARG']=='BASE_IMAGE='+SOURCE+'@sha256:'+BASE_SHA and instructions['FROM']=='${BASE_IMAGE}','pinned original public FROM unchanged')
    entry,cmd=(json.loads(instructions[key]) for key in ('ENTRYPOINT','CMD'))
    need(entry==['/llmd/llmd']==config['config']['Entrypoint'] and cmd==config['config']['Cmd'],'copied selected source and exact config ENTRYPOINT/CMD agree')
    # Per-attempt one-knob attribution belongs before each build. This final
    # image may contain multiple independently kept knobs. Accept only the
    # explicitly reviewed LLMD configuration family, never arbitrary argv.
    def documented_flags(values):
        need(isinstance(values,list) and 2<=len(values)<=11 and all(isinstance(x,str) and 0<len(x)<=128 for x in values),'bounded documented LLMD flag vector')
        integer={'--batch-size','--token-batch-size','--prefill-chunk-size','--page-chunk-size','--speculative-draft-count'}
        fraction={'--gpu-memory-fraction','--cache-memory-fraction'}
        fixed={'--io-impl':'zio','--max-context-len':'128000'}
        allowed=integer|fraction|set(fixed)|{'--backend','--speculative-drafter-model'}
        parsed={}
        for argument in values:
            key,separator,value=argument.partition('=')
            need(separator and key in allowed and key not in parsed,'unique reviewed flag names only')
            if key in fixed:need(value==fixed[key],'model/context/io contract unchanged')
            elif key in integer:need(re.fullmatch(r'[1-9][0-9]{0,19}',value) is not None and int(value)<2**64,'positive bounded integer tuning value')
            elif key in fraction:
                from decimal import Decimal
                need(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',value) is not None and len(value)<=64,'finite numeric memory fraction')
                amount=Decimal(value);need(amount.is_finite() and 0<amount<=1,'memory fraction must be in (0,1]')
            elif key=='--backend':need(value in {'auto','triton'},'only reviewed non-CUDA/non-TPU backend values')
            else:need(value=='native','only built-in speculative drafter, no external model/path')
            parsed[key]=value
        need(all(parsed.get(key)==value for key,value in fixed.items()),'fixed io/context flags required')
        return parsed
    documented_flags(prior_config['config']['Cmd'])
    documented_flags(cmd)
    old=copy.deepcopy(prior_config['config']);new=copy.deepcopy(config['config'])
    old_env=old.pop('Env');new_env=new.pop('Env');old.pop('Cmd');new.pop('Cmd')
    need(config.get("os")==prior_config.get("os")=="linux" and config.get("architecture")==prior_config.get("architecture")=="amd64" and config.get("rootfs")==prior_config.get("rootfs"),"same exact Linux/amd64 inherited rootfs required")
    # OCI image-spec: ArgsEscaped is deprecated Windows-only compatibility.
    # Preserve both raw configs; normalize only the reviewed Linux exec-array
    # view where the historical true flag is omitted/false in a new builder.
    for view in (old,new):
        value=view.get("ArgsEscaped")
        need(value is None or value is True or value is False,"ArgsEscaped must be optional boolean")
    if old.get("ArgsEscaped") is True and (new.get("ArgsEscaped") is None or new.get("ArgsEscaped") is False):
        old.pop("ArgsEscaped",None);new.pop("ArgsEscaped",None)
    old={k:v for k,v in old.items() if v not in (None,'',[],{},False)};new={k:v for k,v in new.items() if v not in (None,'',[],{},False)}
    need(old==new,'all other nonempty actual image runtime semantics unchanged')
    need([x.split('=',1)[0] for x in old_env]==[x.split('=',1)[0] for x in new_env],'same original ordered ENV keys')
    for old_value,new_value in zip(old_env,new_env):
        key,prior=old_value.split('=',1);actual_key,actual=new_value.split('=',1)
        need(actual_key==key and actual==env.get(key,prior),'actual runtime ENV follows exact selected Dockerfile')
    return {'entrypoint':entry,'cmd':cmd,'blanked_telemetry':sorted(env),'filesystem_layer_instructions':0}


def plan_operations(manifest,config_raw,manifest_raw,fixture):
    md='sha256:'+digest(manifest_raw);cfg='sha256:'+digest(config_raw);tag='runc-'+md[7:19]
    steps=[]
    for row in manifest['layers']:
        steps.append({'kind':'ensure_existing_public_blob','head_argv':['blob','head',DEST,row['digest']],'if_missing':'FAIL_NO_LAYER_COPY_ALLOWED','expected_bytes':row['size'],'expected_digest':row['digest']})
    steps.extend([
        {'kind':'put_actual_raw_config','argv':['blob','put','--digest',cfg,DEST],'stdin_file':'public/delivery/metadata/blobs/sha256/'+cfg[7:]},
        {'kind':'put_actual_raw_platform','argv':['manifest','put','--content-type',manifest['mediaType'],DEST+'@'+md],'stdin_file':'public/delivery/metadata/blobs/sha256/'+md[7:]},
        {'kind':'put_mutable_convenience_tag','argv':['manifest','put','--content-type',manifest['mediaType'],DEST+':'+tag],'stdin_file':'public/delivery/metadata/blobs/sha256/'+md[7:]},
        {'kind':'verify_authenticated_digest','argv':['manifest','head','--format','{{.GetDescriptor.Digest}}',DEST+'@'+md],'expected_stdout':md},
        {'kind':'verify_authenticated_tag','argv':['manifest','head','--format','{{.GetDescriptor.Digest}}',DEST+':'+tag],'expected_stdout':md}])
    objects=[{'role':'manifest','digest':md,'bytes':len(manifest_raw),'argv':['manifest','get',DEST+'@'+md,'--format','raw-body']},
        {'role':'config','digest':cfg,'bytes':len(config_raw),'argv':['blob','get',DEST,cfg]}]
    objects += [{'role':'layer','digest':row['digest'],'bytes':row['size'],'argv':['blob','get',DEST,row['digest']]} for row in manifest['layers']]
    return {'version':1,'kind':'UNAPPROVED_EXACT_SELECTED_PLATFORM_OPERATIONS','fixture':fixture,'execute':False,'root_approval_supplied':False,'destination':DEST,'immutable_reference':DEST+'@'+md,'mutable_tag':tag,'tag_is_identity':False,'client':{'name':'regctl-linux-amd64','version':'v0.11.7','sha256':CLIENT_SHA,'pin_attestation':'self-computed historical pin, not official signature'},'publication_steps':steps,'whole_publication_seconds_maximum':1200,
        'anonymous_verification':{'credentials':'new empty REGCTL_CONFIG and DOCKER_CONFIG, no login/account credentials','objects':objects,'objects_expected':25,'layers_expected':23,'body_rule':'every complete body SHA/size must match, with owned-client timeout and retained stderr/partial receipts','whole_seconds_maximum':1200,'no_body_download_performed_here':True},
        'docker_proof':{'immutable_reference':DEST+'@'+md,'platform':'linux/amd64','empty_docker_config_required':True,'physical_and_Docker_free_bytes_minimum':26<<30,'operations':['bounded anonymous docker pull','actual inspect runtime/config/23diffIDs comparison','CPU --help in a fresh exact labelled owned container; no GPU/model mounts','exact owned-container removal/absence receipt'],'proof_performed_here':False},
        'requires_before_any_login_or_upload':['separately reviewed exact generated selection/operations/publisher/checker/workflow SHA marker','explicit approved deployment layout/job using existing ephemeral package-write token','exclusive receipt+append-only attempt journal before client construction','reconcile any uncertain prior attempt; never infer zero writes from missing final receipt'],
        'old_baseline_publisher_compatible':False,'compatibility_reason':'Old baseline09f/0c06/7db constants and BASELINE_FALLBACK/retention-gap selection are historical; do not relabel them for fresh results.'}


def build(bundle,graph,source_proof,full_report,offhost,prior_config,*,fixture):
    state=json.loads(base64.b64decode(bundle['state_base64']));receipt=json.loads(base64.b64decode(bundle['receipt_base64']))
    need(fixture or (state.get('fixture') is not True and state.get('source_commit')==HARNESS),'actual canonical policy-selected state, no fixture promotion')
    need(fixture or state.get('delivery_policy')=='llmd-config-v1','actual persisted configuration delivery policy required')
    image=receipt['image_id'];state_sha=digest(base64.b64decode(bundle['state_base64']))
    need(source_proof['kind']=='actual-selected-context-Dockerfile-copy-v1' and source_proof['reconstructed'] is False and source_proof['image_id']==image and source_proof['accepted_state_sha256']==state_sha,'actual selected-context source copy belongs to exact image/state')
    dockerfile=base64.b64decode(source_proof['source_base64'],validate=True);need(len(dockerfile)==source_proof['source_bytes'] and digest(dockerfile)==source_proof['source_sha256'],'complete exact raw selected source')
    need(offhost['status']=='FRESH_SELECTED_THIRTY_TRACE_REPORT_OFFHOST_REPLAYED' and offhost['image_id']==image and offhost['trace_count']==30 and offhost['full_report']['sha256']==digest(encoded(full_report)),'actual retained offhost thirty-trace validation')
    need(full_report['status']=='COMPLETE_PENDING_OFFHOST_VERIFICATION' and (fixture or full_report['fixture'] is False) and full_report['image_id']==image and full_report['selected_state_sha256']==state_sha and len(full_report['measurement']['traces'])==30 and full_report['cleanup']['confirmed_absent'] is True and full_report['master_sha256']==source_proof['master_sha256'] and full_report['packet_sha256']==source_proof['packet_sha256'],'full report/trace master/packet/selection identity and owned cleanup')
    need(full_report['measurement']['gates_passed'] is True and full_report['replayed_gates']==offhost['gates'] and len(offhost['gates'])==6 and {row['name'] for row in offhost['gates']}=={'all_requests_succeeded','valid_finish_reason','complete_output','token_count_matches_usage','greedy_self_consistency','golden_output_match'} and all(row['passed'] is True for row in offhost['gates']),'actual same six replayed correctness gates, not just a trace count')
    cfg=graph['config_digest'];md=graph['platform_manifest_digest'];raws={name:base64.b64decode(row['base64'],validate=True) for name,row in bundle['files'].items()}
    config_raw,manifest_raw=(raws['blobs/sha256/'+d[7:]] for d in (cfg,md));config,manifest=map(json.loads,(config_raw,manifest_raw))
    need(max(len(config_raw),len(manifest_raw))<=256<<10,'compatible bounded registry raw stdin')
    runtime=dockerfile_runtime(dockerfile,config,prior_config)
    need(all(not re.search(rb'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|dop_v1_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY',raw) for raw in raws.values()),'secret-like bytes refuse public metadata')
    selection={'schema_version':1,'kind':'ACTUAL_SELECTED_PLATFORM_PUBLICATION_HANDOFF','fixture':fixture,'status':'MEASURED_SETTLED_LAST_GOOD_PENDING_PUBLICATION','image':{'source_image_id':image,'config':cfg,'platform_manifest':md,'original_index_digests':graph['original_index_digests'],'inherited_public_layers':23,'original_diff_ids':23,'runtime_spec_sha256':graph['runtime_spec_sha256'],'public_base':SOURCE+'@sha256:'+BASE_SHA},'destination':{'registry':DEST,'by_digest':DEST+'@'+md,'mutable_tag':'runc-'+md[7:19]},'source':{'harness_commit':HARNESS,'dockerfile_sha256':digest(dockerfile),'original_selected_context_file':True,'reconstructed':False,'selected_report_sha256':source_proof['selected_report_sha256']},'model':MODEL,'fresh_revalidation':{'raw_report_retained':True,'traces_retained':True,'requests':30,'report_sha256':digest(encoded(full_report)),'official_grade':False},'selected_state_sha256':state_sha,'optimized_gain_claimed':False,'publication_state':'NOT_EXECUTED_BY_GENERATOR','original_export_archive':{'sha256':receipt['identity']['archive_sha256'],'bytes':receipt['identity']['archive_bytes'],'full_archive_retained_offhost':False,'full_archive_hash_recomputed_here':False},'weights_in_image':False,'license_and_provenance':'Upstream LLMD provenance remains inherited from organizer-held engine/public base; whole image is not relabelled Apache-2.0.'}
    selection['source']['delivery_policy']=state.get('delivery_policy','none')
    selection['pi_evidence']={'selected_last_good_has_patch':bool(state['last_good'].get('patch')),'genuine_propose_build_measure_cycle_verified_here':False,'review_requirement':'Read actual retained Pi transcript, build, control/candidate reports and keep-or-revert decision. Publication packaging is not a claim that the optimization task succeeded.'}
    return selection,plan_operations(manifest,config_raw,manifest_raw,fixture),raws,dockerfile,runtime


def prepare(pipeline_desc,source_desc,output,*,fixture=False):
    m=module('publication_metadata_semantics',ROOT.parent/'task2-image-metadata-operator-20261027/task2_image_metadata.py',META_SHA)
    f=module('publication_image_semantics',ROOT.parent/'task1-runc-candidate-20261028/staging/runtime/full_image_export.py',HELPER_SHA)
    pipeline=m.strict(checked(pipeline_desc));need(pipeline['status']=='TASK2_PIPELINE_RETURNED_REQUIRES_OFFHOST_GRADING','actual completed retained pipeline facts')
    results=pipeline['results'];metadata_result=results['image-metadata'];op=m.strict(read(Path(pipeline_desc['path']).parent/'metadata-operation.json'))
    metadata_root=Path(op['output']);bundle=m.strict(read(metadata_root/'stdout.json'))
    need(m.strict(read(metadata_root/'receipt.json'))==metadata_result,'actual metadata operation receipt exactly equals retained pipeline result')
    public=ROOT.parents[2]/'abstract-image-delivery/delivery/llmd-baseline-20261026'
    base=read(public/'base-manifest.json');original=read(public/'original-receipt.json');proof=read(ROOT.parent/'approved-finish-20261027/cloud-anonymous-result/EXTRACTED/receipt.json')
    selection={'accepted_image_id':metadata_result['selected_image_id'],'accepted_state_sha256':metadata_result['accepted_state_sha256'],'image_receipt_sha256':metadata_result['export_receipt_sha256']}
    graph=m.validate_graph(bundle,base,original,proof,f,selection)
    source=m.strict(checked(source_desc));need(source['master_sha256']==metadata_result['master_sha256'] and source['packet_sha256']==metadata_result['packet_sha256'],'same actual source-copy master/packet')
    need(checked(source['source_file'],64<<10)==base64.b64decode(source['source_base64'],validate=True),'actual source-copy file bytes retained')
    offhost=results['offhost-revalidation'];full_raw=checked(offhost['full_report'],128<<20);full=m.strict(full_raw)
    # Keep the exact raw report SHA; parse/re-encoding equality is a producer
    # contract here (the accepted private emitter writes this canonical form).
    need(encoded(full)==full_raw,'exact original full-report canonical bytes')
    prior=json.loads(read(public/'metadata/000-0c06ab372a7e347dd84145cdcdc6570c123e585f5740508d665987601e3fac6f.bin'))
    selected,operations,raws,dockerfile,runtime=build(bundle,graph,source,full,offhost,prior,fixture=fixture)
    out=Path(output);need(out.is_absolute() and out.resolve()==out and out.parent.is_dir() and not out.exists() and not any(p.is_symlink() for p in (out,*out.parents)),'new exclusive offline publication candidate');out.mkdir(mode=0o700)
    files={}
    for name,raw in raws.items():files['public/delivery/metadata/'+name]=keep(out/'public/delivery/metadata'/name,raw)
    files['public/delivery/selected.Dockerfile']=keep(out/'public/delivery/selected.Dockerfile',dockerfile)
    files['public/delivery/base-manifest.json']=keep(out/'public/delivery/base-manifest.json',base)
    files['public/evidence/selection.json']=keep(out/'public/evidence/selection.json',encoded(selected))
    files['public/.gitattributes']=keep(out/'public/.gitattributes',b'delivery/metadata/** -text\ndelivery/selected.Dockerfile -text\ndelivery/base-manifest.json -text\nevidence/selection.json -text\n')
    operations['selection_sha256']=files['public/evidence/selection.json']['sha256'];operations['source_generator_sha256']=digest(Path(__file__).read_bytes())
    files['operations.json']=keep(out/'operations.json',encoded(operations));keep(out/'runtime-expectation.json',encoded(runtime))
    receipt={'status':'OFFLINE_EXACT_SELECTED_PUBLICATION_HANDOFF_READY','fixture':fixture,'inputs':{'pipeline':pipeline_desc,'selected_source':source_desc},'files':files,'immutable_reference':selected['destination']['by_digest'],'config_graph_and_public23layers_verified':True,'original_large_tar_retained_offhost':False,'root_approval_supplied':False,'registry_or_Docker_client_invocations':0,'registry_publication_or_anonymous_pull_verified':False,'old_baseline_evidence_modified':False}
    keep(out/'receipt.json',encoded(receipt));return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pipeline-result');p.add_argument('--pipeline-result-sha256');p.add_argument('--source-proof');p.add_argument('--source-proof-sha256');p.add_argument('--out');p.add_argument('--prepare',action='store_true');args=p.parse_args()
    if not args.prepare:print('{"inactive":true,"network_Docker_Git_credential_actions":0}');return
    need(all((args.pipeline_result,args.pipeline_result_sha256,args.source_proof,args.source_proof_sha256,args.out)),'all exact independently retained proof inputs')
    print(json.dumps(prepare({'path':args.pipeline_result,'sha256':args.pipeline_result_sha256},{'path':args.source_proof,'sha256':args.source_proof_sha256},args.out),sort_keys=True))


if __name__=='__main__':main()
