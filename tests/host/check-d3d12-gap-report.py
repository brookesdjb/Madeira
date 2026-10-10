#!/usr/bin/env python3
"""Host test for tools/d3d12_gap_report.py.

1. A synthetic two-run log is decoded and ranked as expected: feature ids,
   DXGI formats and interface GUIDs are named, statistics lines are not
   gaps, cumulative counters take each run's last value.
2. Every refusal or skip line madeira_d3d12.c can log is recognised by a
   specific rule rather than falling through to "other", so a new refusal in
   the runtime fails this check until the tool learns it.
"""
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import d3d12_gap_report as G  # noqa: E402

fails = 0


def check(cond, what):
    global fails
    print(('ok   ' if cond else 'FAIL ') + what)
    if not cond:
        fails += 1


RUN_A = """\
0024:err:d3d12: [madeira-d3d12] CheckFeatureSupport(feature 7, 4 bytes) refused: not implemented
0024:err:d3d12: [madeira-d3d12] device QueryInterface refused: {77acce80-638e-4e65-8895-c1f23386863e}
[madeira-d3d12] resource creation REFUSED (texture format has no Metal mapping): dim 3 fmt 98 1024x1024x1 mips 11 samples 1 flags 0x0 heap-type 1
[madeira-d3d12] unimplemented: ID3D12Device10::CreateSamplerFeedbackUnorderedAccessView
[madeira-d3d12] ExecuteIndirect: argument type 10 is not implemented; skipped
[madeira-d3d12] list executed: 40 commands, 12 draws, 3 skipped
[madeira-d3d12] ml1049 skips by site (cumulative): L3773=2
[madeira-d3d12] ml1049 skips by site (cumulative): L3773=5 L4575=1
[madeira-d3d12] ml1049 bind failure x3: root CBV unresolved
[madeira-d3d12] ml1049 bind failure x9: root CBV unresolved
[madeira-d3d12] something else entirely was refused (code 12)
"""
RUN_B = """\
[madeira-d3d12] CheckFeatureSupport(feature 7, 4 bytes) refused: not implemented
[madeira-d3d12] CheckFeatureSupport(feature 7, 4 bytes) refused: not implemented
[madeira-d3d12] CreatePipelineState: mesh/amplification shader stages are not implemented
[madeira-d3d12] ml1049 skips by site (cumulative): L3773=1
"""

with tempfile.TemporaryDirectory() as d:
    a, b = Path(d) / 'game-a.log', Path(d) / 'game-b.log'
    a.write_text(RUN_A)
    b.write_text(RUN_B)
    r = G.build([str(a), str(b)])
    gaps = {g['gap']: g for g in r['gaps']}
    check(r['gaps'][0]['gap'] == 'CheckFeatureSupport(SHADER_MODEL)', 'the gap in both runs ranks first, feature 7 named')
    check(gaps.get('CheckFeatureSupport(SHADER_MODEL)', {}).get('lines') == 3, 'lines are counted across runs')
    check('device asked for ID3D12Device1' in gaps, 'interface GUID named')
    check('texture format has no Metal mapping: TEXTURE2D BC7_UNORM (DEFAULT heap)' in gaps,
          'resource refusal decodes dimension, format and heap')
    check('ID3D12Device10::CreateSamplerFeedbackUnorderedAccessView' in gaps, 'missing method named')
    check('ExecuteIndirect argument DISPATCH_MESH' in gaps, 'indirect argument type named')
    check('mesh/amplification shaders' in gaps, 'mesh shader pipelines recognised')
    check(not any('list executed' in g['example'] for g in r['gaps']), 'statistics lines are not gaps')
    other = [g for g in r['gaps'] if g['impact'] == 'other']
    check(len(other) == 1 and other[0]['gap'] == 'something else entirely was refused (code N)',
          'an unknown refusal is kept under "other" with its numbers collapsed')
    sites = {s['line']: s['skips'] for s in r['skip_sites']}
    check(sites == {3773: 6, 4575: 1}, 'skip sites take each run\'s last cumulative report (%s)' % sites)
    check(r['bind_failures'] == [{'failure': 'root CBV unresolved', 'runs': ['game-a.log'], 'count': 9}],
          'bind failures take the largest cumulative count')
    src = ROOT / 'madeira-d3d12/src/pe/madeira_d3d12.c'
    r2 = G.build([str(a)], str(src))
    fn = {s['line']: s['function'] for s in r2['skip_sites']}
    check(all(fn.values()), 'skip sites are named from the source (%s)' % fn)
    md = G.markdown(r)
    check(md.startswith('# madeira-d3d12 gaps') and '## Can stop a game starting' in md, 'Markdown report renders')

# 2. Every gap line the runtime can print is known to a rule.
SPEC = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?(ll|l|h|z)?([diouxXsfcp%])')


def sample(m):
    conv, alt = m.group(2), '#' in m.group(0)
    if conv == '%':
        return '%'
    if conv == 's':
        return 'name'
    if conv in 'xX':
        width = re.search(r'0(\d+)', m.group(0))
        v = '1f'.rjust(int(width.group(1)), '0') if width else '1f'
        return ('0x' if alt else '') + v
    if conv == 'f':
        return '1.0'
    if conv == 'c':
        return 'c'
    if conv == 'p':
        return '0x1'
    return '7'


text = (ROOT / 'madeira-d3d12/src/pe/madeira_d3d12.c').read_text(errors='replace')
lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
messages = []
for call in re.finditer(r'\bd3d12_log\((.*?)\);', text, re.S):
    # Adjacent literals are one message; a ternary gives one message per branch.
    groups, cur, pos = [], [], 0
    for m in lit.finditer(call.group(1)):
        if cur and call.group(1)[pos:m.start()].strip():
            groups.append(''.join(cur))
            cur = []
        cur.append(m.group(1))
        pos = m.end()
    if cur:
        groups.append(''.join(cur))
    messages += groups

unknown = []
for raw in messages:
    if not raw.startswith('[madeira-d3d12] '):
        continue
    msg = SPEC.sub(sample, raw[len('[madeira-d3d12] '):]).replace('\\n', '')
    if not G.GAP_WORDS.search(msg) or G.STATS.match(msg):
        continue
    c = G.classify(msg)
    if c is None or c[0] == 'other':
        unknown.append(msg)
check(len(messages) > 100, 'read %d log messages from madeira_d3d12.c' % len(messages))
check(not unknown, 'every refusal/skip message has a rule' + ''.join('\n       no rule: ' + u for u in unknown))

print('PASS' if not fails else 'FAILED')
sys.exit(1 if fails else 0)
