import asyncio
import logging
import os
import time

import uvicorn

from fastapi import FastAPI

from app.cors import configure_cors
from app.exception_handlers import register_exception_handlers
from app.middleware.maintenance_mode import MaintenanceModeMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.observability.logging import LoggingSettings, configure_logging
from app.observability.sentry import initialize_sentry
from app.security.rate_limiter import configure_slowapi_limiter

from app.config import (
    AWS_REGION,
    CLOUDWATCH_LOG_GROUP,
    CLOUDWATCH_LOG_RETENTION_DAYS,
    CLOUDWATCH_LOG_STREAM,
    CLOUDWATCH_LOGGING_ENABLED,
    LOG_ENVIRONMENT,
    LOG_EXCLUDED_PATHS,
    LOG_FORMAT,
    LOG_LEVEL,
    SERVICE_NAME,
    engine,
    AsyncSessionLocal,
)
from app.model.authentication.mapper_bootstrap import (
    bootstrap_mappers,
)

from app.migration import run_pending_migrations
from app.service.authentication.auth_service import generate_role
from app.service.subscription.subscription_bootstrap_service import (
    SubscriptionBootstrapService,
)
from app.jobs.job_alert_digest_scheduler import (
    shutdown_job_alert_digest_scheduler,
    start_job_alert_digest_scheduler,
)
from app.jobs.payment_reconciliation_scheduler import (
    shutdown_payment_reconciliation_scheduler,
    start_payment_reconciliation_scheduler,
)


db = None

logger = logging.getLogger(__name__)
STARTUP_STEP_TIMEOUT_SECONDS = int(
    os.getenv("STARTUP_STEP_TIMEOUT_SECONDS", "120")
)


async def _run_startup_step(name: str, awaitable):
    started = time.monotonic()
    logger.info(
        "Startup step started",
        extra={"event": "startup_step_started", "startup_step": name},
    )
    try:
        result = await asyncio.wait_for(
            awaitable,
            timeout=STARTUP_STEP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        elapsed = time.monotonic() - started
        logger.error(
            "Startup step timed out",
            extra={
                "event": "startup_step_timed_out",
                "startup_step": name,
                "duration_seconds": round(elapsed, 2),
            },
        )
        raise RuntimeError(
            f"Startup step timed out after {STARTUP_STEP_TIMEOUT_SECONDS} "
            f"seconds: {name}"
        ) from exc
    except Exception:
        elapsed = time.monotonic() - started
        logger.exception(
            "Startup step failed",
            extra={
                "event": "startup_step_failed",
                "startup_step": name,
                "duration_seconds": round(elapsed, 2),
            },
        )
        raise

    elapsed = time.monotonic() - started
    logger.info(
        "Startup step completed",
        extra={
            "event": "startup_step_completed",
            "startup_step": name,
            "duration_seconds": round(elapsed, 2),
        },
    )
    return result




def init_app():

    configure_logging(
        LoggingSettings(
            service_name=SERVICE_NAME,
            environment=LOG_ENVIRONMENT,
            log_level=LOG_LEVEL,
            json_logs=LOG_FORMAT == "json",
            cloudwatch_enabled=CLOUDWATCH_LOGGING_ENABLED,
            cloudwatch_log_group=CLOUDWATCH_LOG_GROUP,
            cloudwatch_log_stream=CLOUDWATCH_LOG_STREAM,
            cloudwatch_retention_days=CLOUDWATCH_LOG_RETENTION_DAYS,
            aws_region=AWS_REGION,
        )
    )
    initialize_sentry()

    app = FastAPI(
        title="FastAPI",
        description="Authentication API",
        version="1",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.openapi_schema = None

    security_scheme = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter: Bearer <your-jwt-token>",
        }
    }

    def custom_openapi():

        if app.openapi_schema:
            return app.openapi_schema

        from fastapi.openapi.utils import get_openapi
        from app.repository.authentication.auth_repo import JWTBearer

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )

        if "components" not in openapi_schema:
            openapi_schema["components"] = {}

        openapi_schema["components"]["securitySchemes"] = security_scheme

        def _is_secured(dependant) -> bool:
            """Recursively walk FastAPI dependencies to find JWT protection."""
            for dep in getattr(dependant, "dependencies", []):
                call = getattr(dep, "call", None)
                if (
                    getattr(call, "__name__", "") == "get_jwt_payload_401"
                    or isinstance(call, JWTBearer)
                ):
                    return True
                if _is_secured(dep):
                    return True
            return False

        def _iter_routes(routes, prefix: str = ""):
            """Yield concrete routes from both eager and lazy FastAPI routers."""
            for route in routes:
                original_router = getattr(route, "original_router", None)

                if original_router is not None:
                    include_context = getattr(route, "include_context", None)
                    include_prefix = getattr(include_context, "prefix", "")
                    yield from _iter_routes(
                        original_router.routes,
                        f"{prefix}{include_prefix}",
                    )
                    continue

                yield route, f"{prefix}{getattr(route, 'path', '')}"

        for route, route_path in _iter_routes(app.routes):

            if not hasattr(route, "dependant"):
                continue

            dependant = route.dependant

            if not dependant:
                continue

            if not _is_secured(dependant):
                continue

            methods = getattr(route, "methods", [])

            for method in methods:

                if route_path not in openapi_schema["paths"]:
                    continue

                method_key = method.lower()

                if method_key not in openapi_schema["paths"][route_path]:
                    continue

                openapi_schema["paths"][route_path][method_key][
                    "security"
                ] = [{"bearerAuth": []}]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    register_exception_handlers(app)
    configure_slowapi_limiter(app)

    configure_cors(app)
    app.add_middleware(MaintenanceModeMiddleware)

    @app.middleware("http")
    async def no_store_authenticated_responses(request, call_next):
        response = await call_next(request)
        if request.headers.get("authorization"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    app.add_middleware(
        RequestLoggingMiddleware,
        excluded_paths=LOG_EXCLUDED_PATHS,
    )

    @app.on_event("startup")
    async def startup():

        logger.info(
            "Application startup started",
            extra={"event": "application_startup_started"},
        )
        await _run_startup_step(
            "bootstrap SQLAlchemy mappers",
            asyncio.to_thread(bootstrap_mappers),
        )

        await _run_startup_step(
            "run pending Alembic migrations",
            run_pending_migrations(),
        )
    
        async with AsyncSessionLocal() as session:
            await _run_startup_step(
                "seed default roles",
                generate_role(session),
            )
            await _run_startup_step(
                "bootstrap default subscriptions",
                SubscriptionBootstrapService.bootstrap_defaults_and_assignments(
                    session=session,
                    app=app,
                ),
            )

        try:
            start_job_alert_digest_scheduler(app)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to start Job Alert digest scheduler."
            )
        try:
            start_payment_reconciliation_scheduler(app)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Failed to start payment reconciliation scheduler."
            )
        logger.info(
            "Application startup completed",
            extra={"event": "application_startup_completed"},
        )
    
    @app.on_event("shutdown")
    async def shutdown():
        await shutdown_payment_reconciliation_scheduler(app)
        await shutdown_job_alert_digest_scheduler(app)
        await engine.dispose()

    # Routers
    from app.controller.authentication import (
        authentication as authentication_controller,
    )

    from app.controller.authentication import (
        users as users_controller,
    )
    from app.controller.employer_controller import dashboard as employer_dashboard_controller
    from app.controller.employer_controller import job as job_controller
    from app.controller.candidate_controller import (
        candidate as candidate_controller,
    )

    from app.controller.candidate_controller.candidate_jobs import (
        router as candidate_jobs_router,
    )

    from app.controller.candidate_controller.candidate_ai_profile_writer import (
        router as candidate_ai_profile_writer_router,
    )

    from app.controller.candidate_controller.candidate_ai_text_assist import (
        router as candidate_ai_text_assist_router,
    )

    from app.controller.candidate_controller.candidate_ats_resume_analysis import (
        router as candidate_ats_resume_analysis_router,
    )

    from app.controller.candidate_controller.candidate_ai_cover_letter import (
        router as candidate_ai_cover_letter_router,
    )

    from app.controller.candidate_controller.candidate_ai_interview_answer_evaluation import (
        router as candidate_ai_interview_answer_evaluation_router,
    )


    from app.controller.candidate_controller.candidate_list import (
        router as candidate_list_router,
    )
    from app.controller.employer_controller.candidate_details import (
        router as candidate_details_router,
    )

    from app.controller import (
        job_application as job_application_controller,
    )
    from app.controller.employer_controller.job_applicants import (
        applications_router as employer_applications_router,
        router as job_applicants_router,
    )
    from app.controller.employer_controller.shortlisted_candidates import (
        rejected_router,
        router as shortlisted_candidates_router,
    )
    from app.controller.employer_controller.interview import (
        router as interview_router,
    )
    from app.controller.employer_controller.interviewers import (
        router as interviewers_router,
    )
    from app.controller.employer_controller.candidates_search import (
        router as employer_candidates_search_router,
    )
    from app.controller.employer_controller.candidates_invite import (
        router as employer_candidates_invite_router,
    )
    from app.controller.employer_controller.employer_invitations import (
        router as employer_invitations_router,
    )
    from app.controller.employer_controller.notifications import (
        router as employer_notifications_router,
    )
    from app.controller.employer_controller.jobs_active import (
        router as employer_jobs_active_router,
    )
    from app.controller.employer_controller.candidate_public_profile import (
        router as employer_candidate_public_profile_router,
    )
    from app.controller.employer_controller.ai_candidate_matching import (
        router as employer_ai_candidate_matching_router,
    )
    from app.controller.employer_controller.ai_message_drafting import (
        router as employer_ai_message_drafting_router,
    )
    from app.controller.employer_controller.ai_interview_questions import (
        router as employer_ai_interview_questions_router,
    )
    from app.controller.employer_controller.candidate_ai_insights import (
        router as employer_candidate_ai_insights_router,
    )
    from app.controller.candidate_controller.candidate_invitations import (
        router as candidate_invitations_router,
    )
    from app.controller.candidate_controller.candidate_followings import (
        router as candidate_followings_router,
    )
    from app.controller.candidate_controller.candidate_messages import (
        router as candidate_messages_router,
    )
    from app.controller import (
        contact_us_controller,
    )
    from app.controller import (
        master_data_controller,
    )
    from app.controller import (
        notification_controller,
    )
    from app.controller.profile_images import (
        router as profile_images_router,
    )
    from app.controller.employer_controller.ai_job_description import (
        router as employer_ai_job_description_router,
    )
    from app.controller.health import (
        router as health_router,
    )
    from app.controller import (
        payment as payment_controller,
    )
    from app.controller.super_admin.dashboard import (
        router as super_admin_dashboard_router,
    )
    from app.controller.super_admin.dashboard_api import (
        router as super_admin_dashboard_api_router,
    )
    from app.controller.super_admin.company_approval import (
        router as super_admin_company_approval_router,
    )
    from app.controller.super_admin.analytics import (
        router as super_admin_analytics_router,
    )
    from app.controller.super_admin.settings import (
        router as super_admin_settings_router,
    )
    from app.controller.super_admin.employer import (
        router as super_admin_employer_router,
    )
    from app.controller.super_admin.candidate import (
        router as super_admin_candidate_router,
    )
    from app.controller.subscription import (
        subscription as subscription_controller,
    )
    from app.controller.subscription.user_subscription import (
        router as user_subscription_router,
    )
    from app.controller.subscription.user_subscription import (
        self_router as self_subscription_router,
    )
    from app.controller.super_admin.auth import (
        router as super_admin_auth_router,
    )
    from app.controller.super_admin.notifications import (
        router as super_admin_notifications_router,
    )

    
    from app.controller import company
    from app.controller import profile


    app.include_router(authentication_controller.router)
    app.include_router(users_controller.router)
    app.include_router(job_controller.router)
    app.include_router(job_controller.employer_router)
    app.include_router(employer_dashboard_controller.router)
    app.include_router(candidate_controller.router)
    app.include_router(candidate_controller.public_router)
    app.include_router(candidate_jobs_router)
    app.include_router(candidate_ai_profile_writer_router)
    app.include_router(candidate_ai_text_assist_router)
    app.include_router(candidate_ats_resume_analysis_router)
    app.include_router(candidate_ai_cover_letter_router)
    app.include_router(candidate_ai_interview_answer_evaluation_router)
    app.include_router(job_application_controller.router)
    app.include_router(job_application_controller.template_router)
    app.include_router(company.router)
    app.include_router(profile.company_profile_router)
    app.include_router(profile.employer_profile_router)
    app.include_router(profile.companies_router)
    app.include_router(candidate_list_router)
    app.include_router(candidate_details_router)
    app.include_router(employer_applications_router)
    app.include_router(job_applicants_router)
    app.include_router(shortlisted_candidates_router)
    app.include_router(rejected_router)
    app.include_router(interview_router)
    app.include_router(interviewers_router)

    app.include_router(employer_candidates_search_router)
    app.include_router(employer_candidates_invite_router)
    app.include_router(employer_invitations_router)
    app.include_router(employer_notifications_router)
    app.include_router(employer_jobs_active_router)
    app.include_router(employer_candidate_public_profile_router)
    app.include_router(employer_ai_candidate_matching_router)
    app.include_router(employer_ai_message_drafting_router)
    app.include_router(employer_ai_interview_questions_router)
    app.include_router(employer_candidate_ai_insights_router)

    app.include_router(candidate_invitations_router)
    app.include_router(candidate_followings_router)
    app.include_router(candidate_messages_router)


    app.include_router(contact_us_controller.router)
    app.include_router(health_router)
    app.include_router(master_data_controller.router)
    app.include_router(master_data_controller.masters_router)
    app.include_router(notification_controller.router)
    app.include_router(profile_images_router)
    app.include_router(employer_ai_job_description_router)
    app.include_router(payment_controller.router)
    app.include_router(super_admin_dashboard_router)
    app.include_router(super_admin_dashboard_api_router)
    app.include_router(super_admin_company_approval_router)
    app.include_router(super_admin_analytics_router)
    app.include_router(super_admin_settings_router)
    app.include_router(super_admin_employer_router)
    app.include_router(super_admin_candidate_router)
    app.include_router(subscription_controller.router)
    app.include_router(subscription_controller.catalogue_router)
    app.include_router(user_subscription_router)
    app.include_router(self_subscription_router)
    app.include_router(super_admin_auth_router)
    app.include_router(super_admin_notifications_router)


    return app




app = init_app()


def start():

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
