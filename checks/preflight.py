import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
from common import *
from agents import validate_instruction


def manifest_entries(tool):
    entries = {}
    for line in (tool / 'MANIFEST.sha256').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match or match[2] in entries or '\\' in match[2]:
            raise ToolError('ambiguous manifest row')
        entries[match[2]] = match[1]
    return entries


def check(ctx, value):
    source = 'checks/preflight.py'
    def bad(cid, path, escalation=False, key=None):
        value['defects'].append(ctx.defect(cid, source, path, evidence_key=key))
        value['escalate'] |= escalation
    for role, identity in ctx.bind.items():
        if not isinstance(identity, dict):
            continue
        path = Path(identity['path'])
        if symlink_component(path):
            bad('preflight.symlink', ctx.contract, True, role)
            continue
        if not path.is_file():
            raise ToolError('missing control file: ' + str(path))
        actual = digest(ctx.read(path))
        if role != 'Current-state pointer' and actual != identity['sha256']:
            bad('preflight.bound_hash', ctx.contract, True, role)
    contract_hash = digest(ctx.read(ctx.contract))
    tokens = {
        'PROGRAMME_ROOT': str(ctx.root),
        'STAGECHECK_HOME': os.environ.get('STAGECHECK_HOME', str(Path.home())),
    }
    for name in ctx.paths['instruction_copies']:
        resolved_name = resolve_tokens(name, tokens)
        path = Path(resolved_name).expanduser()
        if not path.is_absolute():
            if (ctx.root / path).is_file():
                path = ctx.root / path
            else:
                path = ctx.root.parent.parent / path
        if not path.is_file():
            continue
        if digest(ctx.read(path)) != contract_hash:
            bad('preflight.instructions_differ', ctx.contract, key=name)
    entries = manifest_entries(ctx.tool)
    if 'tools/verify_manifest.py' in entries:
        reused = {'verify_manifest': 'tools/verify_manifest.py',
                  'verify_state_chain': 'tools/verify_state_chain.py',
                  'capture': 'tools/capture_sp1_evidence.py'}
    else:
        reused = {'verify_manifest': '../evidence/claude_audits/tools/verify_manifest.py',
                  'verify_state_chain': '../evidence/claude_audits/tools/verify_state_chain.py',
                  'capture': '../qualification/reviews/capture_sp1_evidence.py'}
    reused_set = set(reused.values())
    allowed_external = {r for r in reused_set if r.startswith('..')}
    for rel, expected in sorted(entries.items()):
        path = ctx.tool / rel
        if not below(path.resolve(), ctx.tool) and rel not in allowed_external:
            raise ToolError('unapproved manifest tool: ' + rel)
        if symlink_component(path):
            bad('preflight.symlink', ctx.tool / 'MANIFEST.sha256', key=rel)
        elif not path.is_file() or digest(ctx.read(path)) != expected:
            bad('preflight.reused_hash' if rel in reused_set else 'preflight.bound_hash',
                ctx.tool / 'MANIFEST.sha256', rel not in reused_set, rel)
    for path in sorted(ctx.tool.rglob('*')):
        if path.is_symlink():
            bad('preflight.symlink', ctx.tool / 'MANIFEST.sha256', key=str(path))
        elif path.is_file() and path.name != 'MANIFEST.sha256' and str(path.relative_to(ctx.tool)) not in entries:
            bad('preflight.unlisted_file', ctx.tool / 'MANIFEST.sha256', key=str(path))
    descriptor = ctx.root / 'controls/STAGECHECK_ROOT.json'
    if descriptor.exists():
        binding = loads(ctx.read(descriptor))
        if set(binding) != {'root', 'manifest_sha256'} or canonical(binding['root']) != ctx.tool:
            raise ToolError('ambiguous STAGECHECK_ROOT descriptor')
        value['unbound'] = binding['manifest_sha256'] != digest(ctx.read(ctx.tool / 'MANIFEST.sha256'))
        if value['unbound']:
            bad('preflight.binding_mismatch', descriptor)
    else:
        value['unbound'] = True
    # Required descriptor target directories, not just descriptor bytes.
    for role in ['Evidence root','Product repositories','Qualification tree (§11)']:
        bound=ctx.bind[role]
        if digest(Path(bound['path']).read_bytes())!=bound['sha256']:
            continue
        for key,target in loads(ctx.read(bound['path'])).items():
            if key=='root' or key.endswith('_root'):
                if not Path(target).is_absolute() or not Path(target).is_dir() or symlink_component(target):
                    raise ToolError('invalid descriptor target: '+str(target))
    agent_config = loads(ctx.read(ctx.tool / 'config/agents.json'))
    declared = [a['instruction'] for a in agent_config['agents']] + [agent_config['orchestrator_instruction']]
    actual = {p.name for p in (ctx.tool / 'agent_instructions').glob('*.md')} - {'00_common.md'}
    if set(declared) != actual or len(declared) != len(set(declared)):
        bad('preflight.agent_mapping', ctx.tool / 'config/agents.json')
    else:
        try:
            validate_instruction(ctx,'common','00_common.md')
            validate_instruction(ctx,'orchestrator',agent_config['orchestrator_instruction'])
            for agent in agent_config['agents']:
                validate_instruction(ctx,agent['id'],agent['instruction'])
        except ToolError:
            bad('preflight.agent_mapping',ctx.tool/'config/agents.json')
    # Never execute a reused tool whose bytes failed the identity check.
    if any(d['check_id'] in ('preflight.reused_hash', 'preflight.symlink', 'preflight.bound_hash') for d in value['defects']):
        value['not_run'].append('reused verifiers: identity/path check failed')
        return
    for rel in reused.values():
        if rel not in entries:
            raise ToolError('reused tool absent from manifest: ' + rel)
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    start = ctx.root / 'RWA/start'
    calls = [
        [sys.executable, str(ctx.tool / reused['verify_manifest']), str(start),
         digest(ctx.read(start / 'START_MANIFEST.md')), ctx.bind['architecture']['path'],
         ctx.bind['architecture']['sha256']],
        [sys.executable, str(ctx.tool / reused['verify_state_chain']), str(ctx.root),
         ctx.bind['protected_sha256'], ctx.bind['Current-state pointer']['sha256']]
    ]
    for i, argv in enumerate(calls):
        execution = ctx.run_command(argv, ctx.tool, env=env)
        if execution['exit_status']:
            bad('preflight.state_history' if i else 'preflight.bound_hash', ctx.contract, True)
    # The reused chain verifier checks linkage/snapshots. Cover its documented
    # gap: protected identity and declared factual changes in EVERY snapshot.
    writable = {'status','source_lock','current_task','completed_tasks','evidence_references','open_prerequisites'}
    protected = {'schema_version','programme','architecture','execution_plan','authority','evidence_root','qualification_root','note'}
    for record in sorted((ctx.root / 'evidence/state_updates').glob('[0-9][0-9][0-9][0-9].json')):
        r = loads(ctx.read(record))
        seq = record.stem
        before = loads(ctx.read(record.with_name(seq + '.before.json')))
        after = loads(ctx.read(record.with_name(seq + '.after.json')))
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        declared_fields = {re.split(r'[.\[]', x)[0] for x in r.get('changed_fields', [])}
        valid = set(before) == set(after) == writable | protected and changed == declared_fields and changed <= writable
        for state in (before, after):
            protected_hash = digest(json.dumps({k: state[k] for k in sorted(protected)},
                                             sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())
            valid &= protected_hash == ctx.bind['protected_sha256']
        valid &= all(r.get(k) for k in ['actor','reason','supporting_evidence'])
        if not valid:
            bad('preflight.state_history', record, True)


if __name__ == '__main__':
    sys.exit(main_check('preflight', check))
