import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *
from authority import grant_valid, forbidden_endpoint


def check(ctx, value):
    preflight_file = getattr(ctx, 'output_dir', Path('/nonexistent')) / 'preflight.json'
    if preflight_file.is_file():
        try:
            pf = loads(preflight_file.read_bytes())
            if pf.get('unbound') or pf.get('errors') or any(d.get('check_id', '').startswith('preflight.') for d in pf.get('defects', [])):
                value['not_run'].append('rerun: preflight unbound or defective; product rerun refused')
                return
        except Exception:
            pass
    data = claims(ctx)
    config = loads(ctx.read(ctx.tool/'config/commands.json'))
    config = resolve_tokens(config, {'PROGRAMME_ROOT': str(ctx.root)})
    cited = [(c['id'], x) for c in data['claims'] for x in c['citations'] if x['type']=='command']
    if not config['enabled']:
        if cited:
            value['not_run'].append('product reruns disabled: owner command selection and grant confirmation required')
        return
    for claim_id, cite in cited:
        choices = [x for x in config['commands'] if x['argv']==cite['argv'] and x['cwd']==cite['cwd']]
        if not choices:
            value['defects'].append(ctx.defect('rerun.unselected','checks/rerun.py',cite['record'],claim_id))
            value['not_run'].append(claim_id+': cited command has no owner-selected rerun; no execution authorized')
            continue
        if len(choices)!=1:
            raise ToolError('claimed command is not uniquely owner-selected')
        selected = choices[0]
        argv = selected['argv']
        env = selected['environment']
        if forbidden_endpoint(argv):
            raise ToolError('forbidden upstream endpoint')
        if not grant_valid(ctx,config['product_grant'],argv,selected['cwd']):
            raise ToolError('no applicable unexpired product-execution grant')
        if not grant_valid(ctx,config['product_grant'],selected['smoke_argv'],selected['cwd']):
            raise ToolError('smoke command is not covered by the owner execution grant')
        expected_binary = canonical(selected['binary'])
        if argv[0] != str(expected_binary) or digest(ctx.read(expected_binary)) != selected['binary_sha256'] or env.get('GOTOOLCHAIN')!='local':
            value['defects'].append(ctx.defect('rerun.toolchain','checks/rerun.py',ctx.tool/'config/commands.json',claim_id))
            continue
        # Inputs are owner-selected and must match both before and after execution.
        for path, sha in selected['inputs'].items():
            if digest(ctx.read(path)) != sha:
                raise ToolError('rerun input differs: '+path)
        clean_env = {k:v for k,v in os.environ.items() if not k.startswith(('LD_','ANTHROPIC_')) and k not in ['GOROOT','GODEBUG','GOEXPERIMENT','CGO_CFLAGS','CGO_CPPFLAGS','CGO_CXXFLAGS','CGO_LDFLAGS']}
        clean_env.update(env)
        clean_env.update(GOTOOLCHAIN='local',GOPROXY='off',GOWORK='off',GOENV='off')
        smoke = ctx.run_command(selected['smoke_argv'],selected['cwd'],timeout=selected['smoke_timeout_seconds'],env=clean_env)
        if smoke['exit_status']:
            raise ToolError('smoke check failed; full rerun was not executed')
        execution = ctx.run_command(argv,selected['cwd'],timeout=selected['timeout_seconds'],env=clean_env)
        for path, sha in selected['inputs'].items():
            if digest(ctx.read(path)) != sha:
                raise ToolError('rerun changed an input: '+path)
        if execution['exit_status'] != cite['exit_status']:
            value['defects'].append(ctx.defect('rerun.exit','checks/rerun.py',cite['record'],claim_id))
        if execution['stdout_sha256'] != cite['stdout_sha256'] or execution['stderr_sha256'] != cite['stderr_sha256']:
            value['defects'].append(ctx.defect('rerun.output','checks/rerun.py',cite['record'],claim_id))


if __name__ == '__main__':
    sys.exit(main_check('rerun', check))
