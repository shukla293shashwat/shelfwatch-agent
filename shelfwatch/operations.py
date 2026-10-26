"""Request limits, optional demo access control, and structured operational logs."""
import hmac
import json
import os
import time
import uuid
from collections import Counter, deque

MAX_REQUEST_BYTES = 26 * 1024 * 1024
COUNTERS = Counter()


class Guardrails:
    def __init__(self, app):
        self.app = app
        self.requests_by_client = {}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        path = scope.get('path', '/')
        headers = dict(scope.get('headers', []))
        protected = path.startswith(('/analyze', '/demo', '/approve', '/orders', '/metrics'))
        status = 500

        async def send_response(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-request-id', request_id.encode()),
                    (b'x-content-type-options', b'nosniff'),
                    (b'x-frame-options', b'DENY'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'content-security-policy', b"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"),
                ]
            await send(message)

        async def reject(code, detail):
            body = json.dumps({'detail': detail}).encode()
            await send_response({'type': 'http.response.start', 'status': code, 'headers': [(b'content-type', b'application/json')]})
            await send_response({'type': 'http.response.body', 'body': body})

        try:
            token = os.getenv('SHELFWATCH_TOKEN', '')
            if protected and token:
                supplied = headers.get(b'authorization', b'')
                if not hmac.compare_digest(supplied, ('Bearer ' + token).encode('utf-8')):
                    return await reject(401, 'Enter the demo access code to continue.')
            if protected and scope['method'] == 'POST':
                client = (scope.get('client') or ('unknown', 0))[0]
                now = time.monotonic()
                if client not in self.requests_by_client and len(self.requests_by_client) >= 1024:
                    return await reject(429, 'The demo is busy. Please try again later.')
                recent = self.requests_by_client.setdefault(client, deque())
                while recent and now - recent[0] > 60:
                    recent.popleft()
                if len(recent) >= 20:
                    return await reject(429, 'Please wait a minute before making more requests.')
                recent.append(now)

            replay = receive
            if scope['method'] == 'POST':
                try:
                    length = int(headers.get(b'content-length', b'0'))
                except ValueError:
                    return await reject(400, 'Invalid request length.')
                if length > MAX_REQUEST_BYTES:
                    return await reject(413, 'The combined upload is too large.')
                chunks, size = [], 0
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    size += len(chunk)
                    if size > MAX_REQUEST_BYTES:
                        return await reject(413, 'The combined upload is too large.')
                    chunks.append(chunk)
                    if not message.get('more_body', False):
                        break
                remaining = b''.join(chunks)
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {'type': 'http.request', 'body': remaining, 'more_body': False}
                    return await receive()
            await self.app(scope, replay, send_response)
        finally:
            COUNTERS['requests'] += 1
            COUNTERS[f'http_{status}'] += 1
            print(json.dumps({'event': 'request', 'request_id': request_id, 'path': path,
                              'status': status, 'duration_ms': round((time.perf_counter() - started) * 1000, 1)}), flush=True)
