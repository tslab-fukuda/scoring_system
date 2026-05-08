import logging
import time
import uuid

from django.conf import settings
from django.db import connection


request_logger = logging.getLogger("scoring.request")


def _env_truthy(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class RequestTimingMiddleware:
    """Log slow/error requests with enough context to separate app and DB time."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "REQUEST_LOG_ENABLED", True):
            return self.get_response(request)

        path = request.path or ""
        excluded_prefixes = getattr(settings, "REQUEST_LOG_EXCLUDED_PATH_PREFIXES", ())
        if any(prefix and path.startswith(prefix) for prefix in excluded_prefixes):
            return self.get_response(request)

        request_id = request.META.get("HTTP_X_REQUEST_ID") or uuid.uuid4().hex[:12]
        request.request_id = request_id

        query_stats = {"count": 0, "seconds": 0.0}

        def query_wrapper(execute, sql, params, many, context):
            query_start = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                query_stats["count"] += 1
                query_stats["seconds"] += time.perf_counter() - query_start

        start = time.perf_counter()
        status_code = 500
        response = None
        exception_raised = False
        try:
            with connection.execute_wrapper(query_wrapper):
                response = self.get_response(request)
            status_code = getattr(response, "status_code", 0) or 0
            return response
        except Exception:
            exception_raised = True
            raise
        finally:
            elapsed = time.perf_counter() - start
            threshold = _safe_float(getattr(settings, "REQUEST_LOG_SLOW_THRESHOLD_SECONDS", 2.0), 2.0)
            log_all = getattr(settings, "REQUEST_LOG_ALL", False)
            should_log = log_all or exception_raised or status_code >= 500 or elapsed >= threshold

            if response is not None:
                response["X-Request-ID"] = request_id

            if should_log:
                request_logger.warning(
                    "request_timing request_id=%s method=%s path=%s status=%s "
                    "elapsed_ms=%d db_ms=%d db_queries=%d user_id=%s user=%s "
                    "role=%s view_role=%s view=%s client_ip=%s remote_addr=%s "
                    "query_keys=%s content_length=%s response_length=%s referer=%s ua=%s",
                    request_id,
                    request.method,
                    path,
                    status_code,
                    int(elapsed * 1000),
                    int(query_stats["seconds"] * 1000),
                    query_stats["count"],
                    self._user_id(request),
                    self._user_label(request),
                    self._user_role(request),
                    self._session_value(request, "view_role"),
                    self._view_name(request),
                    self._client_ip(request),
                    request.META.get("REMOTE_ADDR", ""),
                    ",".join(sorted(request.GET.keys())),
                    request.META.get("CONTENT_LENGTH", ""),
                    response.get("Content-Length", "") if response is not None else "",
                    request.META.get("HTTP_REFERER", ""),
                    (request.META.get("HTTP_USER_AGENT", "") or "")[:160],
                    exc_info=exception_raised,
                )

    @staticmethod
    def _user_id(request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return getattr(user, "id", "")
        return ""

    @staticmethod
    def _user_label(request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            return getattr(user, "email", "") or getattr(user, "username", "")
        return ""

    @staticmethod
    def _user_role(request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return ""
        profile = getattr(user, "userprofile", None)
        return getattr(profile, "role", "") if profile else ""

    @staticmethod
    def _session_value(request, key):
        session = getattr(request, "session", None)
        if session is None:
            return ""
        return session.get(key, "")

    @staticmethod
    def _view_name(request):
        match = getattr(request, "resolver_match", None)
        if not match:
            return ""
        return match.view_name or ""

    @staticmethod
    def _client_ip(request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
