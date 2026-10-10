#!/usr/bin/env python3
"""Rank what madeira-d3d12 refused or skipped across one or more game logs.

madeira-d3d12 names every refusal in its log instead of faking support: a
missing method, an interface or feature query it answers "no" to, a resource
or pipeline it cannot create, a command it drops. Spread over long logs from
several games that is hard to read. This tool collects those lines, decodes
the numbers in them (feature ids, DXGI formats, interface GUIDs, argument
types), groups identical gaps and ranks them by how many runs they appear in,
so the gaps that block the most games come first.

Each log file counts as one run. Lines are matched from their
"[madeira-d3d12]" tag onwards, so Wine or app prefixes do not matter.
madeira-d3d12 rate-limits most of these lines, so "lines" is how often a gap
was logged, not how often it happened; the "ml1049 skips by site" and
"bind failure" counters, which are cumulative, are reported separately.

Usage:
  tools/d3d12_gap_report.py LOG [LOG ...]                Markdown report
  tools/d3d12_gap_report.py --json LOG [LOG ...]         the same as JSON
  tools/d3d12_gap_report.py --source madeira-d3d12/src/pe/madeira_d3d12.c LOG
      also name the function behind each "skips by site" line number

Exit status: 0 when the logs were read (whatever they contain), 2 on a usage
or read error.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d3d12_gap_tables as T  # noqa: E402

TAG = '[madeira-d3d12] '

# Impact, most severe first. "startup" gaps can stop a game from starting or
# push it onto a fallback path; "rendering" gaps lose commands or draws.
IMPACTS = ('startup', 'rendering', 'other')

# Periodic statistics that mention "skipped" without being a gap themselves.
STATS = re.compile(r'^(list executed:|ml1042 last \d+ lists:|ml1049 skips by site|ml1049 bind failure x)')
SKIP_SITES = re.compile(r'^ml1049 skips by site \(cumulative\):(.*)$')
BIND_FAILURE = re.compile(r'^ml1049 bind failure x(\d+): (.*)$')
GAP_WORDS = re.compile(r'not implemented|unimplemented|refused|not supported|skipped|dropped|NOT built|'
                       r'could not be (built|converted)|is not honoured', re.I)


def name(table, value, fallback='%s'):
    try:
        v = int(value, 0)
    except (TypeError, ValueError):
        return str(value)
    return table.get(v, fallback % v)


def fmt(value):
    return name(T.DXGI_FORMAT, value, 'format %d')


def iid(guid):
    return T.INTERFACES.get(guid.lower().strip('{}'), '{%s}' % guid)


def generic_key(msg):
    """Collapse the variable parts of an unrecognised line."""
    msg = re.sub(r"'[^']*'", "'…'", msg)
    msg = re.sub(r'\{[0-9a-fA-F-]+\}', '{guid}', msg)
    msg = re.sub(r'0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b', 'X', msg)
    return re.sub(r'\d+', 'N', msg)


# (pattern, area, impact, key) where key builds the gap's name from the match.
RULES = [
    (r'^unimplemented: (\w+)::(\w+)', 'missing method', 'startup',
     lambda m: '%s::%s' % m.groups()),
    (r'^(.*?) ?QueryInterface refused: \{([^}]*?)(?:-\.\.\.)?\}', 'interface query', 'startup',
     lambda m: '%s asked for %s' % (m.group(1) or 'object', iid(m.group(2)))),
    (r'^CheckFeatureSupport\(feature (\d+), (\d+) bytes\) refused', 'feature query', 'startup',
     lambda m: 'CheckFeatureSupport(%s)' % name(T.D3D12_FEATURE, m.group(1), 'feature %d')),
    (r'^feature level (\S+) refused', 'feature query', 'startup',
     lambda m: 'feature level %s' % m.group(1)),
    (r'^resource creation REFUSED \(([^)]*)\): dim (\d+) fmt (\d+) .*?heap-type (\d+)', 'resource', 'startup',
     lambda m: '%s: %s %s (%s heap)' % (m.group(1), name(T.RESOURCE_DIMENSION, m.group(2)), fmt(m.group(3)),
                                        name(T.HEAP_TYPE, m.group(4)))),
    (r'^ml1038 Map REFUSED: (\S+)', 'resource', 'rendering',
     lambda m: 'Map of a %s' % m.group(1)),
    (r'^CreateCommandQueue: type (\d+)', 'device object', 'startup',
     lambda m: 'command queue type %s' % name(T.COMMAND_LIST_TYPE, m.group(1))),
    (r'^CreateCommandSignature refused: (\d+) argument descs', 'indirect', 'startup',
     lambda m: 'command signature with %s arguments' % m.group(1)),
    (r'^CreateDescriptorHeap: type (\d+)', 'device object', 'startup',
     lambda m: 'descriptor heap type %s' % m.group(1)),
    (r'^ExecuteIndirect: signature with (\d+) argument descs', 'indirect', 'rendering',
     lambda m: 'ExecuteIndirect with multi-argument signatures'),
    (r'^ExecuteIndirect: argument type (\d+)( before the draw)?', 'indirect', 'rendering',
     lambda m: 'ExecuteIndirect argument %s%s' % (name(T.INDIRECT_ARGUMENT, m.group(1)), m.group(2) or '')),
    (r'^ExecuteIndirect: multi-argument records in a GPU-writable heap', 'indirect', 'rendering',
     lambda m: 'ExecuteIndirect records written by the GPU'),
    (r'^ExecuteIndirect: (count buffers are not honoured|stride \d+ is smaller)', 'indirect', 'rendering',
     lambda m: 'ExecuteIndirect: ' + generic_key(m.group(1))),
    (r'^indirect draw on a geometry-shader pipeline', 'draw', 'rendering',
     lambda m: 'indirect draw with a geometry shader'),
    (r'^CreatePipelineState: mesh/amplification', 'pipeline', 'startup',
     lambda m: 'mesh/amplification shaders'),
    (r'^CreatePipelineState: view instancing', 'pipeline', 'startup',
     lambda m: 'view instancing'),
    (r'^CreatePipelineState: unknown subobject type (\d+)', 'pipeline', 'startup',
     lambda m: 'pipeline stream subobject %s' % m.group(1)),
    (r'^CreatePipelineState: stream carried no VS and no CS', 'pipeline', 'startup',
     lambda m: 'pipeline stream without a vertex or compute shader'),
    (r'^pipeline render target \d+ format (\d+) is not supported', 'pipeline', 'startup',
     lambda m: 'render target format %s' % fmt(m.group(1))),
    (r'^pipeline depth format (\d+) is not supported', 'pipeline', 'startup',
     lambda m: 'depth format %s' % fmt(m.group(1))),
    (r'^logic ops are not implemented', 'pipeline', 'rendering', lambda m: 'blend logic ops'),
    (r'^ml1011 mixed-backend pipeline \((.*?)\)', 'shader', 'startup',
     lambda m: 'mixed DXIL/DXBC pipeline (%s)' % m.group(1)),
    (r'^(?:ml\d+ )?(tessellation|geometry|DXIL tessellation|geometry-shader) pipeline', 'shader', 'rendering',
     lambda m: '%s pipeline not built' % m.group(1)),
    (r'^ml1139 compute shader could not be converted', 'shader', 'rendering',
     lambda m: 'compute shader conversion failed'),
    (r'^lazy (compute )?pipeline failed', 'shader', 'rendering',
     lambda m: 'lazy %spipeline failed at first use' % (m.group(1) or '')),
    (r'^(?:ml\d+ )?(tessellation|geometry) (?:factor mismatch|draw too large)', 'draw', 'rendering',
     lambda m: '%s draw dropped' % m.group(1)),
    (r'^DXIL tessellation draw with topology (\d+)', 'draw', 'rendering',
     lambda m: 'DXIL tessellation draw with topology %s' % m.group(1)),
    (r'^(draw without a pipeline state|Dispatch without a compute pipeline)', 'draw', 'rendering',
     lambda m: m.group(1)),
    (r'^CreateRootSignature: root signature version (\d+)', 'root signature', 'startup',
     lambda m: 'root signature version %s' % m.group(1)),
    (r'^CreateRootSignature: root parameter type (\d+)', 'root signature', 'startup',
     lambda m: 'root parameter %s' % name(T.ROOT_PARAMETER, m.group(1))),
    (r'^(D3D12Create(?:Versioned)?RootSignatureDeserializer|D3D12SerializeVersionedRootSignature|'
     r'root signature serialization)', 'root signature', 'startup', lambda m: m.group(1)),
    (r'^CopyResource between a buffer and a texture', 'copy and clear', 'rendering',
     lambda m: 'CopyResource between a buffer and a texture'),
    (r'^(CopyBufferRegion out of range|ResolveSubresource skipped|plane copy)', 'copy and clear', 'rendering',
     lambda m: m.group(1)),
    (r'^(\w+) on (?:a null view|texture .* is not supported|a texture view the runtime does not know)',
     'copy and clear', 'rendering', lambda m: generic_key(m.group(0).split(';')[0])),
    (r'^(SetColorSpace1|IDXGIDevice::GetAdapter|D3D12GetInterface|D3D12EnableExperimentalFeatures)',
     'presentation and DXGI', 'startup', lambda m: m.group(1)),
]
RULES = [(re.compile(p), area, impact, key) for p, area, impact, key in RULES]


def classify(msg):
    """(area, impact, key) for a gap line, or None for anything else."""
    if STATS.match(msg):
        return None
    for pat, area, impact, key in RULES:
        m = pat.match(msg)
        if m:
            return area, impact, key(m)
    if GAP_WORDS.search(msg):
        return 'other', 'other', generic_key(msg)
    return None


def function_at(source_lines, line):
    """The C function enclosing a 1-based source line, by scanning upwards."""
    head = re.compile(r'^(?:static\s+)?[\w\s\*]+?\b(\w+)\s*\(')
    for i in range(min(line, len(source_lines)) - 1, -1, -1):
        text = source_lines[i]
        if text and not text[0].isspace() and not text.startswith(('/', '#', '}')):
            m = head.match(text)
            if m:
                return m.group(1)
    return None


def scan(paths):
    gaps, sites, binds = {}, {}, {}
    if len({Path(p).resolve() for p in paths}) != len(paths):
        raise ValueError('each log file must identify a distinct run')
    names = [Path(p).name for p in paths]
    # Device exports commonly use the same filename in separate run folders.
    # Prefix every name if any collide, without exposing absolute private paths.
    labels = names if len(set(names)) == len(names) else [f'{i + 1}:{name}' for i, name in enumerate(names)]
    for path, run in zip(paths, labels):
        last_sites = {}
        with open(path, 'r', errors='replace') as f:
            for raw in f:
                at = raw.find(TAG)
                if at < 0:
                    continue
                msg = raw[at + len(TAG):].rstrip('\n')
                m = SKIP_SITES.match(msg)
                if m:   # cumulative: the last report of a run is its total
                    last_sites = {int(a): int(b) for a, b in re.findall(r'L(\d+)=(\d+)', m.group(1))}
                    continue
                m = BIND_FAILURE.match(msg)
                if m:
                    b = binds.setdefault(m.group(2), {})
                    b[run] = max(b.get(run, 0), int(m.group(1)))
                    continue
                c = classify(msg)
                if not c:
                    continue
                g = gaps.setdefault(c, {'runs': {}, 'example': msg})
                g['runs'][run] = g['runs'].get(run, 0) + 1
        for line, n in last_sites.items():
            sites.setdefault(line, {})[run] = n
    return gaps, sites, binds, labels


def build(paths, source=None):
    gaps, sites, binds, labels = scan(paths)
    src = Path(source).read_text(errors='replace').splitlines() if source else None
    rows = [{'area': area, 'impact': impact, 'gap': key, 'runs': sorted(g['runs']),
             'lines': sum(g['runs'].values()), 'example': g['example']}
            for (area, impact, key), g in gaps.items()]
    rows.sort(key=lambda r: (IMPACTS.index(r['impact']), -len(r['runs']), -r['lines'], r['area'], r['gap']))
    site_rows = [{'line': line, 'function': function_at(src, line) if src else None,
                  'runs': sorted(per), 'skips': sum(per.values())} for line, per in sites.items()]
    site_rows.sort(key=lambda r: (-r['skips'], r['line']))
    bind_rows = [{'failure': why, 'runs': sorted(per), 'count': sum(per.values())} for why, per in binds.items()]
    bind_rows.sort(key=lambda r: (-r['count'], r['failure']))
    return {'runs': labels, 'gaps': rows, 'skip_sites': site_rows, 'bind_failures': bind_rows}


def cell(text):
    return str(text).replace('|', '\\|')


def markdown(report):
    out = ['# madeira-d3d12 gaps', '',
           'Runs: %s' % ', '.join(report['runs']), '',
           '"Lines" counts logged lines; most are rate-limited, so it is a floor, not a frequency.', '']
    if not report['gaps']:
        out.append('No refusals or skipped commands were logged.')
    for impact in IMPACTS:
        rows = [r for r in report['gaps'] if r['impact'] == impact]
        if not rows:
            continue
        out += ['## %s' % {'startup': 'Can stop a game starting', 'rendering': 'Loses commands or draws',
                            'other': 'Other refusals'}[impact], '',
                '| Gap | Area | Runs | Lines | First line |', '|---|---|---|---|---|']
        for r in rows:
            out.append('| %s | %s | %d of %d | %d | `%s` |' % (cell(r['gap']), r['area'], len(r['runs']),
                                                            len(report['runs']), r['lines'], cell(r['example'][:120])))
        out.append('')
    if report['skip_sites']:
        out += ['## Skipped commands by source line (ml1049, cumulative)', '',
                '| Line | Function | Skips | Runs |', '|---|---|---|---|']
        for r in report['skip_sites']:
            out.append('| %d | %s | %d | %d |' % (r['line'], r['function'] or '', r['skips'], len(r['runs'])))
        out.append('')
    if report['bind_failures']:
        out += ['## Bind failures (ml1049, cumulative)', '', '| Failure | Count | Runs |', '|---|---|---|']
        for r in report['bind_failures']:
            out.append('| %s | %d | %d |' % (cell(r['failure']), r['count'], len(r['runs'])))
        out.append('')
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('logs', nargs='+', help='log files, one per run')
    ap.add_argument('--json', action='store_true', help='print JSON instead of Markdown')
    ap.add_argument('--source', help='madeira_d3d12.c, to name the functions behind skip sites')
    args = ap.parse_args(argv)
    try:
        report = build(args.logs, args.source)
    except (OSError, ValueError) as e:
        print('d3d12_gap_report: %s' % e, file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if args.json else markdown(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
