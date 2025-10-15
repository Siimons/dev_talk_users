import time
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from prometheus_client import (
    Histogram,
    Gauge,
    Counter,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

from app.core.settings import settings
from app.core.logging import logger

# Application Metrics

APPLICATION_INFO = Gauge(
    "application_info",
    "Application version and environment information",
    ["version", "environment", "service_name"]
)

# HTTP Metrics

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code", "status_class"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["method", "endpoint", "status_class"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 
             5.0, 10.0, 30.0)
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Current number of HTTP requests being processed",
    ["method", "endpoint"]
)

HTTP_EXCEPTIONS_TOTAL = Counter(
    "http_exceptions_total",
    "Total number of HTTP exceptions by type",
    ["method", "endpoint", "exception_type", "status_code"]
)


# Middleware Implementation

class MonitoringMiddleware:
    """Middleware для комплексного мониторинга запросов."""

    EXCLUDED_PATHS = {"/metrics", "/health", "/favicon.ico"}

    STATUS_CODE_TO_EXCEPTION = {
        400: "BadRequestError",
        401: "UnauthorizedError",
        403: "ForbiddenError",
        404: "NotFoundError",
        409: "ConflictError",
        422: "ValidationError",
        429: "RateLimitError",
        500: "InternalServerError",
        502: "BadGatewayError",
        503: "ServiceUnavailableError",
        504: "GatewayTimeoutError"
    }

    def __init__(self, app: FastAPI):
        """Инициализирует monitoring middleware."""
        self.app = app

    def _get_status_class(self, status_code: int) -> str:
        """Конвертирует HTTP статус-код в класс статуса."""
        if 100 <= status_code < 200:
            return "1xx"
        elif 200 <= status_code < 300:
            return "2xx"
        elif 300 <= status_code < 400:
            return "3xx"
        elif 400 <= status_code < 500:
            return "4xx"
        else:
            return "5xx"

    def _get_exception_type(self, status_code: int, exception: Optional[Exception] = None) -> str:
        """Определяет тип исключения на основе статус-кода или реального исключения."""
        if exception:
            return type(exception).__name__
        return self.STATUS_CODE_TO_EXCEPTION.get(status_code, f"HTTP_{status_code}")

    async def __call__(self, scope, receive, send) -> None:
        """Обрабатывает запрос и собирает метрики."""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        method = request.method
        endpoint = request.url.path

        if endpoint in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()

        start_time = time.perf_counter()
        status_code = 500
        exception = None

        try:
            async def send_wrapper(message):
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                await send(message)

            await self.app(scope, receive, send_wrapper)

        except Exception as e:
            exception = e
            status_code = getattr(e, "status_code", 500)
            logger.error(
                "Ошибка обработки запроса",
                extra={
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "exception_type": type(e).__name__,
                    "exception_message": str(e)
                }
            )
            raise

        finally:
            duration = time.perf_counter() - start_time
            status_class = self._get_status_class(status_code)
            exception_type = self._get_exception_type(status_code, exception)

            HTTP_REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()

            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                status_class=status_class
            ).inc()

            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
                status_class=status_class
            ).observe(duration)

            if status_class in ["4xx", "5xx"]:
                HTTP_EXCEPTIONS_TOTAL.labels(
                    method=method,
                    endpoint=endpoint,
                    exception_type=exception_type,
                    status_code=status_code
                ).inc()

            if duration > 1.0:
                logger.warning(
                    "Обнаружен медленный запрос",
                    extra={
                        "method": method,
                        "endpoint": endpoint,
                        "duration_seconds": round(duration, 3),
                        "status_code": status_code
                    }
                )


# Metrics Exposition

def create_metrics_router(app: FastAPI) -> None:
    """
    Регистрирует эндпоинты для метрик и проверки состояния приложения.

    Данная функция регистрирует специальные эндпоинты, которые используются
    системами мониторинга для сбора метрик и проверки работоспособности приложения.

    Args:
        app: Экземпляр FastAPI приложения для регистрации эндпоинтов.
    """

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """
        Предоставляет метрики приложения в формате Prometheus.

        Данный эндпоинт используется системами мониторинга для сбора метрик
        о работе приложения, таких как количество запросов, время ответа
        и другие показатели производительности.

        Returns:
            Response: Ответ с метриками в текстовом формате, понятном Prometheus.
        """
        return Response(
            content=generate_latest(REGISTRY),
            media_type=CONTENT_TYPE_LATEST,
            headers={"Cache-Control": "no-cache"}
        )

    @app.get("/health", include_in_schema=False)
    async def health_check() -> JSONResponse:
        """
        Проверяет состояние работоспособности приложения.

        Используется балансировщиками нагрузки и системами мониторинга
        для определения доступности сервиса и принятия решений о маршрутизации.

        Returns:
            JSONResponse: Ответ с информацией о состоянии приложения
                         и метаданными версии.
        """
        health_info = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT
        }

        return JSONResponse(content=health_info, status_code=200)


# Initialization

def setup_application_metrics(app: FastAPI) -> None:
    """
    Настраивает базовые метрики приложения.

    Инициализирует статические метрики, которые содержат информацию
    о версии приложения, окружении и названии сервиса.
    Эти метрики сохраняются на протяжении всего времени работы приложения.

    Args:
        app: Экземпляр FastAPI приложения для извлечения метаданных.
    """
    APPLICATION_INFO.labels(
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        service_name=app.title
    ).set(1)


def setup_monitoring(app: FastAPI) -> None:
    """
    Настраивает комплексную систему мониторинга для FastAPI приложения.

    Выполняет последовательную инициализацию всех компонентов мониторинга:
    - Настраивает метрики приложения
    - Регистрирует эндпоинты для метрик и проверки здоровья
    - Добавляет middleware для отслеживания HTTP-запросов

    Args:
        app: Экземпляр FastAPI приложения для настройки мониторинга.
    """
    setup_application_metrics(app)
    create_metrics_router(app)
    app.add_middleware(MonitoringMiddleware)

    logger.info(
        "Система мониторинга инициализирована",
        extra={
            "service": app.title,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT
        }
    )
