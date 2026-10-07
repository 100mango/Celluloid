"""TV-only bounded capture adapter. General capture helpers remain unchanged."""
import os
import selectors
import signal
import subprocess
import time
from owned_process_group import group_exists, stop_group

class CaptureStopped(RuntimeError):
    def __init__(self, reason, cleanup_confirmed, cancelled_signal=None):
        super().__init__(reason)
        self.cleanup_confirmed = cleanup_confirmed
        self.cancelled_signal = cancelled_signal

def require(condition, message):
    if not condition:raise ValueError(message)


def stopped_with_prefix(reason, confirmed, cancelled, output, errors):
    stopped = CaptureStopped(reason, confirmed, cancelled)
    stopped.stdout_prefix = bytes(output)
    stopped.stderr_capture = bytes(errors)
    return stopped


def capture(command, *, seconds, cap, cleanup_grace=2):
    """TV-local adapter: bounded failure prefixes with unchanged owned cleanup.

    Derived from the existing capture implementation. The only retention change
    is keeping already-read bytes, up to the same combined cap, on failure. No
    reads occur during cleanup; a failure never becomes command completion.
    """
    require(cleanup_grace in (2, 10), 'Unexpected owned cleanup reserve')
    deadline = time.monotonic() + seconds
    cancelled = [None]
    previous = {}
    process = None
    output, errors = bytearray(), bytearray()
    stopped = None
    selector = selectors.DefaultSelector()

    def interrupted(signum, frame):
        # As in the seed controller, defer further termination signals through
        # the finite owned cleanup reserve. Recording instead of raising also
        # closes the Popen-to-ownership-assignment cancellation race.
        if cancelled[0] is None:
            cancelled[0] = signum

    def check_cancelled():
        if cancelled[0] is not None:
            raise RuntimeError('interrupted-by-signal-' + str(cancelled[0]))

    try:
        # Install before spawning. Never leave an owned producer under the
        # default SIGTERM action; restore the caller's handlers after cleanup.
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupted)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        check_cancelled()
        total = 0
        for pipe in (process.stdout, process.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('duration-limit')
            for key, _ in selector.select(min(remaining, .05)):
                check_cancelled()
                data = os.read(key.fileobj.fileno(), min(4096, cap + 1 - total))
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                # Retain at most the remaining combined budget, including a
                # bounded prefix of the block that first crosses the cap.
                retained = data[:max(0, cap - total)]
                if key.fileobj is process.stdout:
                    output.extend(retained)
                else:
                    errors.extend(retained)
                total += len(data)
                if total > cap:
                    raise RuntimeError('byte-limit')
        check_cancelled()
        if time.monotonic() > deadline:
            raise RuntimeError('late-exit')
        if group_exists(process.pid):
            raise RuntimeError('descendant-exit-unconfirmed')
        result = subprocess.CompletedProcess(command, process.returncode, bytes(output), bytes(errors))
    except BaseException as error:
        if process is None:
            raise
        # Reuse the reviewed owned-group protocol and the caller's unchanged
        # reserve. Record-only handlers remain active throughout this call, so
        # even the first signal during timeout/byte-limit cleanup cannot escape.
        confirmed = stop_group(process, grace=cleanup_grace)
        reason = str(error) if type(error) is RuntimeError else type(error).__name__
        stopped = stopped_with_prefix(reason, confirmed, cancelled[0], output, errors)
        raise stopped from None
    finally:
        selector.close()
        if process is not None:
            process.stdout.close()
            process.stderr.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if cancelled[0] is not None:
            if stopped is not None:
                # Include a signal received during final pipe/selector cleanup.
                stopped.cancelled_signal = cancelled[0]
            elif process is None:
                raise stopped_with_prefix('interrupted-before-spawn', True, cancelled[0], output, errors) from None
    if cancelled[0] is not None:
        # Cancellation concurrent with a natural exit is still not successful.
        raise stopped_with_prefix('interrupted-by-signal-' + str(cancelled[0]), True, cancelled[0], output, errors)
    return result
