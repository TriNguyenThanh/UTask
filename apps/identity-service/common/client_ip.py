"""Accept one gateway-normalized address only from an explicitly trusted peer."""

from ipaddress import ip_address, ip_network

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class TrustedProxyClientIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self.trusted_networks = tuple(
                ip_network(cidr, strict=False) for cidr in settings.IDENTITY_TRUSTED_PROXY_CIDRS
            )
        except ValueError as exc:
            raise ImproperlyConfigured(
                "IDENTITY_TRUSTED_PROXY_CIDRS contains an invalid CIDR."
            ) from exc

    def __call__(self, request):
        try:
            peer = ip_address(request.META.get("REMOTE_ADDR", ""))
        except ValueError:
            return self.get_response(request)

        if any(peer in network for network in self.trusted_networks):
            forwarded = request.META.get("HTTP_X_REAL_IP", "").strip()
            try:
                # A gateway must send one address, never a list, port or interface scope.
                if "%" in forwarded:
                    raise ValueError("Scoped addresses are not client addresses.")
                client = ip_address(forwarded)
            except ValueError:
                pass
            else:
                request.META["REMOTE_ADDR"] = str(client)

        return self.get_response(request)
