from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from flask import Flask
from werkzeug.serving import BaseWSGIServer, make_server

from src.utils import instance

HOST = "127.0.0.1"


@contextmanager
def _serve(app: Flask) -> Iterator[BaseWSGIServer]:
    server = make_server(HOST, 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()


def _quit_by(server_box: list[BaseWSGIServer]) -> Callable[[], str]:
    def quit_() -> str:
        def stop() -> None:
            server_box[0].shutdown()
            server_box[0].server_close()  # a real process exit frees the port

        threading.Thread(target=stop).start()
        return "bye"

    return quit_


def test_port_in_use_is_false_for_a_free_port() -> None:
    server = make_server(HOST, 0, Flask("x"))
    port = server.server_port
    server.server_close()

    assert instance.port_in_use(HOST, port) is False
    assert instance.stop_running_instance(HOST, port, timeout=0.5) is False


def test_a_current_copy_is_stopped_with_quit() -> None:
    app = Flask("current")
    box: list[BaseWSGIServer] = []
    app.add_url_rule("/ping", "ping", lambda: {"app": instance.APP_ID})
    app.add_url_rule("/quit", "quit", _quit_by(box), methods=["POST"])
    app.add_url_rule("/shutdown", "slow", lambda: "never used", methods=["POST"])

    with _serve(app) as server:
        box.append(server)
        port = server.server_port
        assert instance.port_in_use(HOST, port)

        assert instance.stop_running_instance(HOST, port) is True
        assert instance.port_in_use(HOST, port) is False


def test_an_older_copy_is_stopped_with_its_shutdown() -> None:
    app = Flask("legacy")
    box: list[BaseWSGIServer] = []
    app.add_url_rule(
        "/setup",
        "setup",
        lambda: '<a href="https://github.com/sfb1638/elAPI_Plugins/releases">v1</a>',
    )
    app.add_url_rule("/shutdown", "shutdown", _quit_by(box), methods=["POST"])

    with _serve(app) as server:
        box.append(server)
        port = server.server_port

        assert instance.stop_running_instance(HOST, port) is True
        assert instance.port_in_use(HOST, port) is False


@pytest.mark.parametrize("path", ["/", "/setup"])
def test_another_program_is_left_alone(path: str) -> None:
    app = Flask("foreign")
    hits: list[str] = []
    app.add_url_rule(path, "page", lambda: "some other program")
    for name in ("/quit", "/shutdown"):
        app.add_url_rule(
            name, name, lambda n=name: hits.append(n) or "x", methods=["POST"]
        )

    with _serve(app) as server:
        port = server.server_port

        assert instance.stop_running_instance(HOST, port, timeout=0.5) is False
        assert instance.port_in_use(HOST, port) is True
        assert hits == []  # it was never asked to stop
