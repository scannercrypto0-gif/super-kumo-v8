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
    buffer = connection.frame_buffer
    if not buffer.needs_header():
        phase = "EXTENDED_LENGTH" if buffer.needs_length() else "FRAME_PAYLOAD"
    else:
        phase = "PARTIAL_HEADER" if buffer.recv_buffer else "FRAME_BOUNDARY"
    return {"receive_phase": phase, "deadline_origin": origin}
