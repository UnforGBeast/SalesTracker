from django.shortcuts import redirect
from .models import SiteConfig

# Paths that must always work, even before the instance has been branded --
# otherwise you could never reach the wizard, the admin (to fix things), or
# any static/media asset the wizard page itself needs to render.
EXEMPT_PREFIXES = ('/setup/', '/admin/', '/static/', '/media/', '/manifest.webmanifest', '/sw.js')


class SetupWizardMiddleware:
    """Redirects every request to /setup/ until the first-run branding wizard
    has been completed -- the "launch window" that appears the first time the
    app is started on a fresh instance."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        if not SiteConfig.load().is_setup_complete:
            return redirect('setup_wizard')

        return self.get_response(request)
