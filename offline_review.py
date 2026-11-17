"""Block network sockets in the research test process after pinned Git staging."""
import socket


def deny(*_args, **_kwargs):
    raise AssertionError("OFFLINE_REVIEW_NETWORK_DISABLED")


def pytest_configure(config):
    socket.create_connection = deny
    socket.socket.connect = deny
    socket.socket.connect_ex = deny


def pytest_sessionfinish(session, exitstatus):
    if session.testscollected and session.config.pluginmanager.get_plugin("terminalreporter"):
        terminal = session.config.pluginmanager.get_plugin("terminalreporter")
        if terminal.stats.get("skipped"):
            session.exitstatus = 1
