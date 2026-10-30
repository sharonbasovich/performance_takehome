"""Inactive outside explicit execution on the dedicated GitHub-hosted Linux job."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, shutil, subprocess

SDK_PATHS = (Path('/usr/local/lib/android'), Path('/opt/ghc'), Path('/usr/share/dotnet'))
MINIMUM = 26 << 30

def need(ok, reason):
    if not ok: raise ValueError(reason)

def context(environ, out):
    need(environ.get('GITHUB_ACTIONS') == 'true'
         and environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
         and environ.get('RUNNER_OS') == 'Linux'
         and os.name == 'posix', 'dedicated GitHub-hosted Linux job required')
    workspace = Path(environ['GITHUB_WORKSPACE']).resolve(strict=True)
    need(out.is_absolute() and out.name == 'docker-capacity.json'
         and out.parent.resolve(strict=True) == workspace and not out.exists()
         and not out.is_symlink(), 'new exact workspace capacity receipt required')
    return workspace

def checked_sdk(target, workspace):
    need(target in SDK_PATHS and target.is_absolute(), 'fixed SDK allowlist only')
    need(not target.is_symlink() and target.resolve(strict=True) == target and target.is_dir(),
         'SDK must be original regular directory without path redirection')
    need(not workspace.is_relative_to(target) and not target.is_relative_to(workspace),
         'never remove workspace or artifact paths')
    return target

def execute(out):
    workspace = context(os.environ, out)
    receipt = {'kind': 'DEDICATED_GITHUB_HOSTED_DOCKER_CAPACITY', 'status': 'STARTED',
        'started_utc': datetime.now(timezone.utc).isoformat(), 'minimum_free_bytes': MINIMUM,
        'fixed_sdk_allowlist': [str(path) for path in SDK_PATHS], 'sdk_actions': [],
        'workspace_artifact_Docker_runtime_paths_removed': False}
    def save():
        with out.open('w') as stream:
            stream.write(json.dumps(receipt, indent=2)+'\n'); stream.flush(); os.fsync(stream.fileno())
    with out.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2)+'\n'); stream.flush(); os.fsync(stream.fileno())
    try:
        for target in SDK_PATHS:
            action = {'path': str(target), 'status': 'ABSENT'}
            if os.path.lexists(target):
                checked_sdk(target, workspace)
                action['status'] = 'REMOVAL_STARTED'; receipt['sdk_actions'].append(action); save()
                subprocess.run(['/usr/bin/sudo', '--', '/usr/bin/rm', '-rf', '--', str(target)],
                    stdin=subprocess.DEVNULL, check=True, timeout=180)
                need(not os.path.lexists(target), 'fixed SDK removal incomplete')
                action['status'] = 'REMOVED'
            else: receipt['sdk_actions'].append(action)
            save()
        free = {'host_root': shutil.disk_usage('/').free,
                'Docker_root': shutil.disk_usage('/var/lib/docker').free}
        if Path('/var/lib/containerd').is_dir():
            free['containerd_root'] = shutil.disk_usage('/var/lib/containerd').free
        receipt['free_bytes_before_pull'] = free
        need(all(value >= MINIMUM for value in free.values()), '26GiB host/Docker capacity required')
        receipt.update(status='CAPACITY_PASS_BEFORE_ANONYMOUS_PULL',
            finished_utc=datetime.now(timezone.utc).isoformat()); save()
    except BaseException as error:
        receipt.update(status='CAPACITY_FAILED_BEFORE_PULL', error_type=type(error).__name__)
        save(); raise
    return receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-cleanup', action='store_true'); parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if not args.execute_cleanup:
        print('{"inactive":true,"filesystem_mutations":0}'); return
    need(args.out is not None, 'explicit receipt required')
    print(json.dumps(execute(args.out)))

if __name__ == '__main__': main()
