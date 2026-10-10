#!/usr/bin/env python3
"""Stage the opt-in native Present hook without editing the DXMT submodule."""
import argparse
from pathlib import Path


def stage(source, output):
    text = Path(source).read_text()
    anchor = '  uint64_t n = atomic_fetch_add_explicit(&g_madeira_present_count, 1, memory_order_relaxed) + 1;'
    if text.count(anchor) != 1:
        raise ValueError('pinned Present hook anchor mismatch')
    hook = '''\n  /* Only the opted-in archive has this weak app callback. Normal archives
     retain the original source byte-for-byte. */
  extern void madeira_automation_record_present(void) __attribute__((weak_import));
  if (madeira_automation_record_present) madeira_automation_record_present();'''
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    text = text.replace(anchor, anchor + hook)
    text += '\nint madeira_automation_frame_hook_available(void) { return 1; }\n'
    Path(output).write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('output')
    args = parser.parse_args(); stage(args.source, args.output)
