"""Safe provider/agent failure categories; never expose request bodies or credentials."""
import re
import httpx
from langgraph.errors import GraphRecursionError
from openai import APIStatusError, APITimeoutError
from openrouter.errors import OpenRouterError, ResponseValidationError, NoResponseError
from .react_agent import ChatUnavailable, ThreadBusy

def chat_failure(exc):
    if isinstance(exc, ThreadBusy):
        return 409, "busy", "This conversation already has a response in progress."
    if isinstance(exc, ChatUnavailable):
        return 503, "incomplete", str(exc)
    if isinstance(exc, (TimeoutError, httpx.TimeoutException, APITimeoutError)):
        return 504, "timeout", "The assistant timed out while waiting for the model. Try a shorter request."
    if isinstance(exc, NoResponseError):
        return 502, "connection", "OpenRouter did not return a response. Please retry when the provider is available."
    if isinstance(exc, GraphRecursionError):
        return 502, "tool_loop", "The assistant reached its tool-step limit. Try a narrower request or a new conversation."
    if isinstance(exc, ResponseValidationError):
        return 502, "provider_response", "OpenRouter returned an incompatible response for the configured model. Try a new conversation."
    status = getattr(exc, "status_code", None) if isinstance(exc, (OpenRouterError, APIStatusError)) else None
    provider = isinstance(exc, (OpenRouterError, APIStatusError))
    if isinstance(exc, ValueError) and str(exc).startswith("OpenRouter API returned an error during streaming:"):
        provider = True
        match = re.search(r"\(code: (\d+)\)", str(exc))
        status = int(match.group(1)) if match else None
    if provider:
        if "Paid model training violation" in str(exc) or "Paid model training violation" in str(getattr(exc, "body", "")):
            return 503, "privacy", "OpenRouter blocks this model under your account privacy policy. Review OpenRouter privacy settings or explicitly select another model; no settings were changed."
        if status in (408, 504, 524):
            return 504, "provider_timeout", "The model provider timed out. Try a shorter request or retry later."
        messages = {
            401: ("credentials", "OpenRouter rejected the API credentials. Check OPENROUTER_API_KEY in the root .env."),
            402: ("credits", "OpenRouter reports insufficient credits for this model."),
            403: ("access", "OpenRouter denied access to the configured model. Check its account/privacy requirements."),
            404: ("model_unavailable", "The configured model is unavailable on OpenRouter."),
            429: ("rate_limit", "OpenRouter's model rate limit was reached. Wait briefly before retrying."),
        }
        if status in messages:
            code, message = messages[status]
            return 502, code, message
        if status in (400, 413, 422):
            return 502, "provider_request", "The model provider rejected this conversation's request. Try a new conversation with a shorter request."
        return 502, "provider_failure", "The configured model provider failed during the response. Try again later; no alternate model was used."
    if isinstance(exc, httpx.HTTPError):
        return 502, "connection", "The connection to OpenRouter failed. Please retry when the connection is available."
    return 502, "unexpected", "The assistant encountered an unexpected error. Try a new conversation."
