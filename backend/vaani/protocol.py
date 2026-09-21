"""WebSocket message protocol for Vaani — the single home for message types.

Every message that flows across the client/server WebSocket connection will be
defined here and NOWHERE else. Centralising the wire format in one module means
there is exactly one place to look when asking "what can the client send?" or
"what can the server send back?", and one place to change when the protocol
evolves.

Nothing is defined yet. The WebSocket endpoint is out of scope for Day 1; this
module exists now so the boundary is fixed before any message type is written.
"""
