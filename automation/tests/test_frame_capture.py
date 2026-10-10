from pathlib import Path
import importlib.util
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_production_ring_bounds_concurrent_writers_and_restart(tmp_path):
    source = tmp_path / 'ring.c'
    source.write_text('''
#define MADEIRA_FRAME_CAPACITY 32
#include "automation_frame_ring.h"
#include <assert.h>
#include <pthread.h>
static void *produce(void *p) { for(int i=0;i<10000;i++) madeira_frame_record(); return 0; }
int main(void) {
 madeira_frame_record(); assert(madeira_frame_count==0);
 assert(madeira_frame_begin()); assert(!madeira_frame_begin());
 pthread_t threads[4]; for(int i=0;i<4;i++) pthread_create(&threads[i],0,produce,0);
 for(int i=0;i<4;i++) pthread_join(threads[i],0);
 madeira_frame_end();
 assert(madeira_frame_count==32); assert(madeira_frame_count+atomic_load(&madeira_frame_dropped)==40000);
 for(int i=1;i<32;i++) {assert(madeira_frames[i].timestamp_ns>madeira_frames[i-1].timestamp_ns);assert(madeira_frames[i].sequence==i+1);}
 madeira_frame_record(); assert(madeira_frame_count==32);
 assert(madeira_frame_begin()); assert(madeira_frame_count==0); assert(atomic_load(&madeira_frame_dropped)==0);
 madeira_frame_record(); madeira_frame_end(); assert(madeira_frame_count==1);
}
''')
    exe = tmp_path/'ring'
    subprocess.run(['clang','-O2','-fsanitize=address,undefined','-pthread','-I'+str(ROOT/'app/Madeira'),str(source),'-o',str(exe)], check=True)
    subprocess.run([str(exe)],check=True,timeout=10)


def test_hook_stages_copy_and_fails_closed_for_changed_source(tmp_path):
    path = ROOT/'build/dxmt-ios/stage-frame-capture.py'
    spec=importlib.util.spec_from_file_location('stage',path); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'source.c';dest=tmp_path/'stage.c'
    anchor='  uint64_t n = atomic_fetch_add_explicit(&g_madeira_present_count, 1, memory_order_relaxed) + 1;'
    source.write_text(anchor+'\n/* quiet gate */')
    module.stage(source,dest)
    assert 'record_present' not in source.read_text()
    assert dest.read_text().index('record_present();') < dest.read_text().index('quiet gate')
    assert 'frame_hook_available' in dest.read_text()
    source.write_text('different source')
    import pytest
    with pytest.raises(ValueError):module.stage(source,dest)
