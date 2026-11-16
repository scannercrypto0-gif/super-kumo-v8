"""Saved-only classification of timeouts from the pinned #305 frame reader."""


def receive_timeout_context(connection, error):
    """Expose parser progress and deadline origin without inspecting payload bytes."""
    wrapped = error.__cause__
    if type(error) is not TimeoutError or str(error) != "WS_READ_TIMEOUT" or wrapped is None:
        return {}
    buffer = connection.frame_buffer
    if not buffer.needs_header():
        phase = "EXTENDED_LENGTH" if buffer.needs_length() else "FRAME_PAYLOAD"
    else:
        phase = "PARTIAL_HEADER" if buffer.recv_buffer else "FRAME_BOUNDARY"
    origin = "OUTER_FRAME_DEADLINE" if str(wrapped) == "frame deadline" else "UNDERLYING_RECEIVE_TIMEOUT"
    return {"receive_phase": phase, "deadline_origin": origin}
