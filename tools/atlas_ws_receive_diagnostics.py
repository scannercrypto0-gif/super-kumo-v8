"""Sanitized classification of faults from the pinned #305 frame reader."""


def receive_fault_context(connection, error):
    """Expose parser progress and fault origin without inspecting payload bytes."""
    wrapped = error.__cause__
    if isinstance(error, ConnectionResetError):
        origin = "CONNECTION_RESET"
    elif type(error) is TimeoutError and str(error) == "WS_READ_TIMEOUT" and wrapped is not None:
        origin = "OUTER_FRAME_DEADLINE" if str(wrapped) == "frame deadline" else "UNDERLYING_RECEIVE_TIMEOUT"
    else:
        return {}
    # Diagnostics must never replace the original transport failure if the
    # library/socket is absent or its parser state cannot be inspected.
    try:
        buffer = getattr(connection, "frame_buffer", None)
        if buffer is None:
            return {}
        if not buffer.needs_header():
            phase = "EXTENDED_LENGTH" if buffer.needs_length() else "FRAME_PAYLOAD"
        else:
            phase = "PARTIAL_HEADER" if buffer.recv_buffer else "FRAME_BOUNDARY"
    except Exception:
        return {}
    return {"receive_phase": phase, "deadline_origin": origin}



def classify_transport_fault(error, context, stage):
    """Classify known eligible faults, never infer a frame boundary from type.

    The bounded retry budget and current quota remain caller-owned. This helper
    does not open a socket or authorize a supervisory recovery segment.
    """
    import socket
    import ssl
    from websocket import WebSocketBadStatusException, WebSocketTimeoutException

    chain, wrapped = [], error
    for _ in range(4):
        if wrapped is None or type(wrapped).__name__ in chain:
            break
        chain.append(type(wrapped).__name__)
        wrapped = wrapped.__cause__
    eligible = False
    kind = "UNCLASSIFIED_TERMINAL"
    if stage == "CONNECT":
        if isinstance(error, (TimeoutError, WebSocketTimeoutException)):
            kind, eligible = "CONNECT_TIMEOUT", True
        elif isinstance(error, (ConnectionResetError, ConnectionRefusedError)):
            kind, eligible = "CONNECT_RESET_OR_REFUSED", True
        elif isinstance(error, socket.gaierror):
            kind, eligible = "DNS_FAILURE", error.errno == socket.EAI_AGAIN
        elif isinstance(error, ssl.SSLError):
            kind = "TLS_FAILURE"
        elif isinstance(error, WebSocketBadStatusException):
            code = getattr(error, "status_code", None)
            kind = "HTTP_REJECTION"
            # Ban/rate-limit/auth/redirect/protocol rejections remain terminal.
            eligible = code in (500, 502, 503, 504)
    elif stage == "FRAME_READ":
        known = ((isinstance(error, ConnectionResetError) and
                  context.get("deadline_origin") == "CONNECTION_RESET") or
                 (type(error) is TimeoutError and
                  context.get("deadline_origin") == "UNDERLYING_RECEIVE_TIMEOUT"))
        eligible = bool(known and context.get("receive_phase") == "FRAME_BOUNDARY")
        kind = "FRAME_BOUNDARY_TRANSIENT" if eligible else "PARTIAL_OR_UNKNOWN_FRAME_TERMINAL"
    elif stage == "PONG" and type(error) is TimeoutError and str(error) == "PONG_LIVENESS_EXPIRED":
        eligible = context == dict(receive_phase="FRAME_BOUNDARY", deadline_origin="PONG_LIVENESS_EXPIRED")
        kind = "PONG_LIVENESS_EXPIRED" if eligible else "PONG_TERMINAL"
    transport_error = stage in ("CONNECT", "FRAME_READ", "PONG") and isinstance(
        error, (TimeoutError, ConnectionError, socket.gaierror, ssl.SSLError,
                WebSocketBadStatusException, WebSocketTimeoutException))
    if not transport_error:
        kind = "PROTOCOL_DATA_OR_LOCAL_TERMINAL"
    # Numeric OS cause metadata only; never persist exception text/host names.
    codes = {}
    wrapped = error
    for _ in range(4):
        if wrapped is None: break
        for name in ('errno', 'winerror'):
            value = getattr(wrapped, name, None)
            if type(value) is int and 0 <= value <= 65535:
                codes.setdefault(name, value)
        wrapped = wrapped.__cause__
    return dict(os_codes=codes, fault_stage=stage, fault_class=kind, retry_eligible=eligible,
                is_transport_fault=bool(transport_error), exception_chain=chain)


class _PingProof:
    __slots__=('connection_id','payload','observed_ns')
    def __init__(self,connection,payload,observed_ns):
        self.connection_id=id(connection);self.payload=bytes(payload);self.observed_ns=observed_ns


def clear_ping_proof(connection):
    try:delattr(connection,'_atlas_verified_ping')
    except AttributeError:pass


def remember_complete_ping(connection,frame):
    import time
    from websocket import ABNF
    clear_ping_proof(connection)
    if (not isinstance(frame,ABNF) or frame.opcode!=ABNF.OPCODE_PING or not frame.fin
        or frame.mask_value or frame.rsv1 or frame.rsv2 or frame.rsv3
        or type(frame.data) not in (bytes,bytearray) or len(frame.data)>125):return False
    try:connection._atlas_verified_ping=_PingProof(connection,frame.data,time.monotonic_ns())
    except AttributeError:return False
    return True


def consume_recent_ping(connection,payload):
    import time
    proof=getattr(connection,'_atlas_verified_ping',None)
    clear_ping_proof(connection) # one use, including rejected attempts
    if not isinstance(proof,_PingProof):return False
    buffer=getattr(connection,'frame_buffer',None)
    return (proof.connection_id==id(connection) and type(payload) in (bytes,bytearray)
        and proof.payload==bytes(payload) and 0<=time.monotonic_ns()-proof.observed_ns<=1000000000
        and buffer is not None and buffer.needs_header() and not buffer.recv_buffer)
