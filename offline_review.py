"""Block network sockets in the research test process after pinned Git staging."""
import socket


def deny(*_args, **_kwargs):
    raise AssertionError("OFFLINE_REVIEW_NETWORK_DISABLED")


def pytest_configure(config):
    import tools

    # Pytest can change sys.path after fixture setup starts. Retain the
    # candidate's namespace entries so the pinned fixture overlay can append.
    tools.__path__ = list(tools.__path__)
    socket.create_connection = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny


def pytest_sessionfinish(session, exitstatus):
    if session.testscollected and session.config.pluginmanager.get_plugin("terminalreporter"):
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal.stats.get("skipped"):
            session.exitstatus = 1
