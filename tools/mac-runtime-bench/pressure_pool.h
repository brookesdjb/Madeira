// Host-only experiment. No production FEX source is changed.
#pragma once
#include <FEXCore/Utils/ThreadPoolAllocator.h>

class PressurePool final : public FEXCore::Utils::IntrusivePooledAllocator {
public:
  ~PressurePool() override { FreeAllBuffers(); }
private:
  void *Alloc(size_t size) override {
    void *result = FEXCore::Allocator::VirtualAlloc(size);
    if (result) return result;
    // ClaimBufferImpl holds AllocationMutex here. Win ownership against the
    // lock-free reown operation before touching any client-disowned buffer.
    for (auto it = ClaimedBuffers.begin(); it != ClaimedBuffers.end();) {
      auto *buffer = *it;
      ClientFlags expected = ClientFlags::FLAG_DISOWNED;
      if (buffer->CurrentClientOwnedFlag->compare_exchange_strong(expected, ClientFlags::FLAG_FREE)) {
        Free(buffer->Ptr, buffer->Size);
        delete buffer;
        it = ClaimedBuffers.erase(it);
      } else {
        ++it;
      }
    }
    // No existing free buffer fitted the request. Release small cached extents
    // too, allowing adjacent ranges to coalesce in the arena model.
    for (auto *buffer : UnclaimedBuffers) {
      Free(buffer->Ptr, buffer->Size);
      delete buffer;
    }
    UnclaimedBuffers.clear();
    // Preserve failure visibility: if no space was recovered this stays NULL,
    // and the unchanged production claim path still marks that NULL owned.
    return FEXCore::Allocator::VirtualAlloc(size);
  }
  void Free(void *ptr, size_t size) override {
    FEXCore::Allocator::VirtualFree(ptr, size);
  }
};
