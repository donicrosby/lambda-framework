"""GitHub webhook module."""

import asyncio
import inspect
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Annotated, Any, TypeVar

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Security

if TYPE_CHECKING:
    from githubkit.versions.latest.webhooks import WebhookEvent

E = TypeVar("E", bound="WebhookEvent")

try:
    from githubkit.webhooks import parse_obj, verify
except ImportError:
    parse_obj = None
    verify = None


class GithubWebhookValidator:
    """Validate GitHub webhook signatures using HMAC-SHA256.

    This class is used as a FastAPI dependency to verify that incoming
    webhook requests are authentically from GitHub.
    """

    def __init__(self, secret: str) -> None:
        """Initialize the validator with a webhook secret.

        Args:
            secret: The GitHub webhook secret configured in the repository settings.

        """
        self.secret = secret

    def __call__(
        self,
        payload: Annotated[dict, Body(...)],
        x_hub_signature_256: Annotated[str, Header(...)],
    ) -> dict[str, Any]:
        """Validate the webhook signature and return the payload.

        Args:
            payload: The raw JSON payload from the webhook request.
            x_hub_signature_256: The signature header sent by GitHub.

        Returns:
            The validated payload dictionary.

        Raises:
            ImportError: If githubkit is not installed.
            HTTPException: If the signature is invalid (401 Unauthorized).

        """
        if verify is None:
            raise ImportError(
                "Githubkit is missing, please install the 'github' optional dependency."
            )
        if not verify(self.secret, payload, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")
        return payload


class GithubWebhookParser:
    """Parse validated GitHub webhook payloads into typed event objects.

    Uses githubkit's parse_obj to convert raw payloads into strongly-typed
    webhook event classes based on the X-GitHub-Event header.
    """

    def __init__(self, validator: GithubWebhookValidator) -> None:
        """Initialize the parser with a validator dependency.

        Args:
            validator: The validator used to verify webhook signatures.

        Raises:
            ImportError: If githubkit is not installed.

        """
        if parse_obj is None:
            raise ImportError(
                "Githubkit is missing, please install the 'github' optional dependency."
            )
        self.parse_obj = parse_obj
        self.validator: GithubWebhookValidator = validator

    def as_dependency(self, event_type: type[E] | None = None) -> Callable[..., E]:
        """Create a FastAPI dependency that parses and returns the webhook event.

        Args:
            event_type: Optional specific event type (e.g., PushEvent, CheckRunEvent).
                        Used for type hints; at runtime parse_obj returns the correct type.

        Returns:
            A dependency function that returns the parsed event with proper typing.

        """
        validator = self.validator
        parse_obj_fn = self.parse_obj

        def _parse(
            payload: Annotated[dict[str, Any], Security(validator)],
            x_github_event: Annotated[str, Header()],
        ) -> E:
            return parse_obj_fn(x_github_event, payload)  # type: ignore[return-value]

        return _parse


class GithubWebhookRouter:
    """FastAPI router for handling GitHub webhooks with automatic validation and parsing.

    Provides a decorator-based API for registering webhook handlers with
    signature validation, payload parsing, and full type safety.

    Example:
        webhook_router = GithubWebhookRouter(webhook_secret="your-secret")

        @webhook_router.add_webhook("/github")
        async def handle_push(event: PushEvent):
            print(event.commits)

        webhook_router.register(app)

    """

    def __init__(self, webhook_secret: str) -> None:
        """Initialize the webhook router.

        Args:
            webhook_secret: The GitHub webhook secret for signature validation.

        """
        self._webhook_secret = webhook_secret
        self._parser = GithubWebhookParser(GithubWebhookValidator(webhook_secret))
        self._router = APIRouter(dependencies=[Security(self._parser.as_dependency())])

    def register(self, app: FastAPI) -> None:
        """Register this webhook router with a FastAPI application.

        Args:
            app: The FastAPI application to register routes with.

        """
        app.include_router(self._router)

    def add_webhook(
        self, path: str = "/", **kwargs
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as a webhook handler.

        The decorated function's first parameter will receive the parsed WebhookEvent.
        You can use specific event types (e.g., PushEvent, CheckRunEvent) for better typing.
        Other parameters can still use FastAPI's dependency injection.

        Args:
            path: The URL path for the webhook endpoint (default: "/").
            **kwargs: Additional arguments passed to router.post() (e.g., status_code, tags).

        Returns:
            A decorator that registers the function as a POST endpoint.

        Example:
            @webhook_router.add_webhook("/github")
            async def handle_push(event: PushEvent):
                print(event.commits)

        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            if not params:
                raise ValueError(
                    "Handler must have at least one parameter for WebhookEvent"
                )

            # Get the user's event type annotation (e.g., PushEvent, CheckRunEvent)
            event_param = params[0]
            user_event_type = event_param.annotation

            # Use WebhookEvent as fallback if no annotation provided
            if user_event_type is inspect.Parameter.empty:
                annotation_type: Any = "WebhookEvent"  # Forward reference
                parser_dep = self._parser.as_dependency(None)
            else:
                annotation_type = user_event_type
                # Pass type for better typing; it's a type at runtime
                parser_dep = self._parser.as_dependency(
                    user_event_type if isinstance(user_event_type, type) else None
                )

            # Preserve user's type annotation with Depends() wrapper
            new_event_param = event_param.replace(
                annotation=Annotated[annotation_type, Depends(parser_dep)]
            )
            new_sig = sig.replace(parameters=[new_event_param] + params[1:])

            # Create async wrapper - FastAPI handles both sync and async
            @wraps(func)
            async def wrapper(*args: Any, **kw: Any) -> Any:
                result = func(*args, **kw)
                if asyncio.iscoroutine(result):
                    return await result
                return result

            # Set the modified signature - FastAPI reads this
            wrapper.__signature__ = new_sig  # type: ignore[attr-defined]

            # Register with the router
            self._router.post(path, **kwargs)(wrapper)
            return func

        return decorator
