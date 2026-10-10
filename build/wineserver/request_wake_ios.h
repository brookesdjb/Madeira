/* Copyright 2026 125hz. GPL-3.0-or-later with the Madeira Converter Exception. */
#ifndef MADEIRA_REQUEST_WAKE_IOS_H
#define MADEIRA_REQUEST_WAKE_IOS_H

/* Clients publish requests before marking pending. The server clears pending
 * BEFORE scanning all descriptors, never after: a post-scan request must leave
 * a wake for the next pass. The kernel semaphore retains signals until waited. */
struct ios_request_wake_state
{
    unsigned int pending;
};

static inline int ios_request_wake_mark( struct ios_request_wake_state *state )
{
    return !__atomic_exchange_n( &state->pending, 1, __ATOMIC_SEQ_CST );
}

static inline void ios_request_wake_begin_scan( struct ios_request_wake_state *state )
{
    __atomic_store_n( &state->pending, 0, __ATOMIC_SEQ_CST );
}

#endif
