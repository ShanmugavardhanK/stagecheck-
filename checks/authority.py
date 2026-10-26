import sys
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bin'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *
from citations import validate_citation


def approved_remote(url, approved):
    if url == 'DISABLED':
        return True
    if url not in approved:
        return False
    if url.startswith('git@github.com:'):
        return url.split(':',1)[1].startswith('xorewa/')
    parsed = urlparse(url)
    return parsed.hostname == 'github.com' and parsed.path.startswith('/xorewa/') and parsed.scheme in ('https','ssh')


def forbidden_endpoint(argv):
    for arg in argv:
        for url in re.findall(r'https?://[^\s"\']+', arg):
            host = (urlparse(url).hostname or '').lower()
            if host in ('multiversx.com','elrond.com') or host.endswith('.multiversx.com') or host.endswith('.elrond.com'):
                return True
    return False


def grant_valid(ctx, grant, argv, cwd):
    if not grant or not isinstance(grant, dict):
        return False
    cite = grant.get('citation')
    if not cite or cite.get('path') != ctx.bind['Owner grant ledger (§9)']['path'] or validate_citation(ctx, cite):
        return False
    expiry = grant.get('expires_utc')
    if expiry:
        if datetime.fromisoformat(expiry.replace('Z','+00:00')) <= datetime.now(timezone.utc):
            return False
        if expiry not in cite['quote']:
            return False
    elif grant.get('expiry_stage') == 'SP1':
        state = loads(ctx.read(ctx.bind['Current-state pointer']['path']))
        if not state.get('status','').startswith('SP1_') or 'end of SP1' not in cite['quote']:
            return False
    else:
        return False
    return any(item.get('argv') == argv and item.get('cwd') == cwd for item in grant.get('commands', []))


def consequential(argv):
    if not argv:
        return True
    name = Path(argv[0]).name
    if name == 'git':
        words=list(argv[1:])
        while len(words)>=2 and words[0]=='-C':
            words=words[2:]
        if not words:
            return True
        sub,args=words[0],words[1:]
        if sub=='branch':
            return args not in ([],['--show-current'],['--list'])
        if sub=='remote':
            if not args:
                return False
            if args[0]=='get-url':
                rest=args[1:]
                return not (rest and not rest[-1].startswith('-') and all(x in ('--push','--all') for x in rest[:-1]))
            return True
        if sub in ('status','show','diff','rev-parse','ls-files'):
            # Read-looking git commands can write outputs or invoke helpers.
            return any(x in ('--ext-diff','--textconv','--output') or x.startswith('--output=') for x in args)
        return True
    if name=='rg':
        return any(x=='--pre' or x.startswith('--pre=') for x in argv[1:])
    if name in ('cat','sha256sum','realpath'):
        return False
    if name == 'go' and argv[1:] in [['version'],['env']]:
        return False
    return True


def check(ctx, value):
    data = claims(ctx)
    remote_config = loads(ctx.read(ctx.tool / 'config/remotes.json'))
    config = loads(ctx.read(ctx.tool / 'config/commands.json'))
    config = resolve_tokens(config, {'PROGRAMME_ROOT': str(ctx.root)})
    if not ctx.run.get('response'):
        repo = canonical(ctx.run['repo'])
        names = ctx.run_command(['git','-C',str(repo),'remote'], repo)
        if names['exit_status']:
            raise ToolError('cannot inspect effective git remotes')
        for name in names['stdout'].splitlines():
            urls = ctx.run_command(['git','-C',str(repo),'remote','get-url','--push','--all',name], repo)
            if urls['exit_status']:
                raise ToolError('cannot resolve push URL')
            for url in urls['stdout'].splitlines():
                if not approved_remote(url, remote_config['approved_push_urls']):
                    value['defects'].append(ctx.defect('authority.remote','checks/authority.py',ctx.run['claims'],evidence_key=[name,url]))
    records = set(ctx.run.get('operation_records', []))
    records.update(cite['record'] for c in data['claims'] for cite in c['citations'] if cite['type']=='command')
    for record in sorted(records):
        retained = loads(ctx.read(record))
        argv, cwd = retained['argv'], retained['cwd']
        if forbidden_endpoint(argv):
            value['defects'].append(ctx.defect('authority.upstream_endpoint','checks/authority.py',record))
        # Generator records are subjects, never the source of execution authority.
        grant = config.get('product_grant')
        if consequential(argv) and not grant_valid(ctx, grant, argv, cwd):
            value['defects'].append(ctx.defect('authority.grant','checks/authority.py',record))


if __name__ == '__main__':
    sys.exit(main_check('authority', check))
