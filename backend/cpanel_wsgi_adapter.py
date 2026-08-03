"""Small ASGI-to-WSGI adapter for cPanel Passenger.

This adapter intentionally supports HTTP requests only. It is sufficient for
FastAPI JSON APIs, forms, uploads and Excel/file downloads used by this system.
Raw WebSocket upgrades are not available through WSGI/Passenger.
"""
from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any, Callable, Iterable


class ASGItoWSGI:
    def __init__(self, asgi_app: Callable[..., Any]) -> None:
        self.asgi_app = asgi_app

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        content_length_text = environ.get("CONTENT_LENGTH") or ""
        try:
            content_length = int(content_length_text)
        except (TypeError, ValueError):
            content_length = 0

        input_stream = environ.get("wsgi.input")
        if input_stream is None:
            request_body = b""
        elif content_length > 0:
            request_body = input_stream.read(content_length)
        else:
            request_body = input_stream.read() or b""

        path = environ.get("PATH_INFO") or "/"
        script_name = environ.get("SCRIPT_NAME") or ""
        # Passenger normally removes SCRIPT_NAME from PATH_INFO. Some hosting
        # configurations pass the full path, so strip it defensively.
        if script_name and path.startswith(script_name):
            path = path[len(script_name):] or "/"
        query_string = (environ.get("QUERY_STRING") or "").encode("latin-1")

        headers: list[tuple[bytes, bytes]] = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                name = key[5:].replace("_", "-").lower().encode("latin-1")
                headers.append((name, str(value).encode("latin-1")))
        if environ.get("CONTENT_TYPE"):
            headers.append((b"content-type", str(environ["CONTENT_TYPE"]).encode("latin-1")))
        if content_length_text:
            headers.append((b"content-length", str(content_length_text).encode("latin-1")))

        try:
            server_port = int(environ.get("SERVER_PORT") or 80)
        except (TypeError, ValueError):
            server_port = 80
        try:
            client_port = int(environ.get("REMOTE_PORT") or 0)
        except (TypeError, ValueError):
            client_port = 0

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": str(environ.get("SERVER_PROTOCOL", "HTTP/1.1")).replace("HTTP/", ""),
            "method": str(environ.get("REQUEST_METHOD", "GET")).upper(),
            "scheme": str(environ.get("wsgi.url_scheme", "https")),
            "path": path,
            "raw_path": path.encode("latin-1"),
            "query_string": query_string,
            "root_path": script_name,
            "headers": headers,
            "server": (str(environ.get("SERVER_NAME", "localhost")), server_port),
            "client": (str(environ.get("REMOTE_ADDR", "127.0.0.1")), client_port),
        }

        response_status = 500
        response_headers: list[tuple[str, str]] = []
        response_body: list[bytes] = []
        receive_sent = False
        disconnect_waiter: asyncio.Event | None = None

        async def receive() -> dict[str, Any]:
            nonlocal receive_sent, disconnect_waiter
            if not receive_sent:
                receive_sent = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            # A WSGI request has no asynchronous disconnect notification. Block
            # here so Starlette's StreamingResponse does not cancel its stream
            # before all Excel/file chunks have been emitted.
            if disconnect_waiter is None:
                disconnect_waiter = asyncio.Event()
            await disconnect_waiter.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_status, response_headers
            message_type = message.get("type")
            if message_type == "http.response.start":
                response_status = int(message.get("status", 500))
                response_headers = [
                    (name.decode("latin-1"), value.decode("latin-1"))
                    for name, value in message.get("headers", [])
                ]
            elif message_type == "http.response.body":
                body = message.get("body", b"")
                if body:
                    response_body.append(body)

        asyncio.run(self.asgi_app(scope, receive, send))

        body = b"".join(response_body)
        if not any(name.lower() == "content-length" for name, _ in response_headers):
            response_headers.append(("Content-Length", str(len(body))))
        try:
            reason = HTTPStatus(response_status).phrase
        except ValueError:
            reason = "Unknown"
        start_response(f"{response_status} {reason}", response_headers)
        return [body]
