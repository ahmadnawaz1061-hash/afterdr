"""Bound the entire multipart body before parsing, including chunked uploads."""
from starlette.responses import JSONResponse
from app.services.image_validation import MAX_PACKAGING_REQUEST_SIZE


class PackagingUploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path', '').rstrip('/') != '/api/verifications/analyze':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        try:
            declared = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Invalid request size'}, status_code=400)(scope, receive, send)
        if declared > MAX_PACKAGING_REQUEST_SIZE:
            return await JSONResponse({'detail': 'Total request exceeds the 12 MB limit'}, status_code=413)(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            size += len(body)
            if size > MAX_PACKAGING_REQUEST_SIZE:
                return await JSONResponse({'detail': 'Total request exceeds the 12 MB limit'}, status_code=413)(scope, receive, send)
            chunks.append(body)
            if not message.get('more_body', False):
                break
        complete = b''.join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': complete, 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)
