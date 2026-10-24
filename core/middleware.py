from .models import AuditEvent


class AuditSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        protected_paths = ('/documents', '/audit', '/admin/users')
        if request.path.startswith(protected_paths) and response.status_code in (302, 403, 404):
            if not request.user.is_authenticated:
                AuditEvent.objects.create(
                    actor=None,
                    action='DENIED_ACCESS',
                    target=request.path,
                    outcome='DENIED',
                    details='Unauthenticated request blocked by security middleware.',
                    request_path=request.path,
                    request_method=request.method,
                )
        return response
