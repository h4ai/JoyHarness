"""Single-instance lock via abstract/loopback TCP socket.

Binding a socket to a fixed loopback port is the most reliable cross-platform
way to enforce "only one process at a time": the OS releases the port the
moment the process dies (no stale lockfiles to clean up after a crash), and
it works identically on macOS, Linux, and Windows.
"""

from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)

# Arbitrary high port unlikely to collide with anything else. Loopback only,
# so it never touches the network.
_LOCK_HOST = "127.0.0.1"
_LOCK_PORT = 51842

# Module-level holder so the socket lives for the lifetime of the process.
# If this is garbage-collected the OS reclaims the port and the lock is gone.
_lock_socket: socket.socket | None = None


def acquire(host: str = _LOCK_HOST, port: int = _LOCK_PORT) -> bool:
    """Try to bind the lock socket. Returns True if we got it, False if another
    instance is already running.
    """
    global _lock_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        s.listen(1)
    except OSError as e:
        logger.info("Single-instance lock unavailable on %s:%d (%s)", host, port, e)
        s.close()
        return False
    _lock_socket = s
    logger.debug("Single-instance lock acquired on %s:%d", host, port)
    return True


def release() -> None:
    """Release the lock (rarely needed — process exit does this automatically)."""
    global _lock_socket
    if _lock_socket is not None:
        try:
            _lock_socket.close()
        except Exception:
            pass
        _lock_socket = None
