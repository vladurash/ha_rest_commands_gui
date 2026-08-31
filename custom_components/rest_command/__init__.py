"""The RESTful Command integration with GUI support."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import (
    CONF_AUTHENTICATION,
    CONF_HEADERS,
    CONF_METHOD,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    SERVICE_RELOAD,
)
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CONTENT_TYPE,
    CONF_INSECURE_CIPHER,
    CONF_RETURN_RESPONSE,
    CONF_SKIP_URL_ENCODING,
    CONF_SLUG,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_METHOD,
    DEFAULT_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    HISTORY_MAX_CONTENT_LENGTH,
    HISTORY_MAX_ENTRIES,
    HISTORY_STORAGE_KEY,
    HISTORY_STORAGE_VERSION,
    METHODS,
    SERVICE_CLEAR_HISTORY,
    SERVICE_GET_HISTORY,
    SERVICE_TEST_REQUEST,
)

_LOGGER = logging.getLogger(__name__)


def _history_store(hass: HomeAssistant) -> Store:
    """Return the Store used to persist request history."""
    return Store(hass, HISTORY_STORAGE_VERSION, HISTORY_STORAGE_KEY)


def command_slug(command_config: dict[str, Any], fallback: Any = None) -> str:
    """Compute the stable service slug for a command.

    GUI-managed commands store an explicit ``slug`` (generated from the
    friendly name at creation time). YAML commands use their key directly
    (already a valid slug), so they fall through unchanged.
    """
    explicit_slug = command_config.get(CONF_SLUG)
    if isinstance(explicit_slug, str) and explicit_slug:
        return explicit_slug

    source = command_config.get(CONF_NAME)
    if not isinstance(source, str) or not source.strip():
        source = fallback if isinstance(fallback, str) else None
    if not source or not source.strip():
        return "command"

    from homeassistant.util import slugify

    return slugify(source) or "command"

COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): cv.string,
        vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.All(
            vol.Lower, vol.In(METHODS)
        ),
        vol.Optional(CONF_HEADERS): vol.Schema({str: cv.string}),
        vol.Optional(CONF_PAYLOAD): cv.string,
        vol.Optional(CONF_AUTHENTICATION): vol.In(["basic", "digest", "none"]),
        vol.Optional(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
        vol.Optional(CONF_CONTENT_TYPE, default=DEFAULT_CONTENT_TYPE): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
        vol.Optional(CONF_INSECURE_CIPHER, default=False): cv.boolean,
        vol.Optional(CONF_SKIP_URL_ENCODING, default=False): cv.boolean,
        vol.Optional(CONF_RETURN_RESPONSE, default=False): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({cv.slug: COMMAND_SCHEMA})},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the RESTful Command component.

    Supports both the legacy YAML configuration and GUI-managed subentries.
    YAML commands are registered directly (backward compatible with the core
    integration). Subentries registered via the config flow are managed by
    async_setup_entry.
    """
    configured_yaml = config.get(DOMAIN, {})
    for name, command_config in configured_yaml.items():
        _register_command_config(hass, name, command_config)

    async def reload_service_handler(service: ServiceCall) -> None:
        """Reload REST commands."""
        await async_reload(hass)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RELOAD,
        reload_service_handler,
        schema=vol.Schema({}),
    )

    _register_test_request(hass)
    _register_history_services(hass)

    return True


def _register_test_request(hass: HomeAssistant) -> None:
    """Register the Postman-like test_request service.

    Registered independently of YAML/entry setup so it is always available,
    and re-registered on reload (async_reload) which otherwise clears every
    non-reload service in the domain.
    """
    async def test_request_service_handler(service: ServiceCall) -> dict[str, Any]:
        """Send an arbitrary request for Postman-like testing.

        Unlike configured commands, this accepts the full request in the call
        (method, url, headers, payload, timeout...), so a dashboard card can
        craft and fire any request and read back the status, content, and
        headers without pre-configuring a command. Returns those three.
        """
        method = str(service.data.get(CONF_METHOD, DEFAULT_METHOD)).upper()
        url = service.data[CONF_URL]
        headers = dict(service.data.get(CONF_HEADERS) or {})
        payload = service.data.get(CONF_PAYLOAD)
        timeout = service.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
        verify_ssl = service.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        content_type = service.data.get(CONF_CONTENT_TYPE)
        if content_type:
            headers.setdefault("Content-Type", content_type)

        session = async_get_clientsession(hass, verify_ssl=verify_ssl)
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        try:
            response = await session.request(
                method,
                url,
                headers=headers,
                data=payload,
                timeout=client_timeout,
                skip_auto_headers=None,
            )
            response_text = await response.text()
            try:
                response_content = await response.json()
            except (aiohttp.ContentTypeError, ValueError):
                response_content = response_text
            result = {
                "content": response_content,
                "status": response.status,
                "headers": {k: v for k, v in response.headers.items()},
            }
            await _async_append_history(
                hass,
                _history_entry(
                    method=method, url=url, headers=headers, payload=payload,
                    result=result,
                ),
            )
            return result
        except asyncio.TimeoutError as err:
            await _async_append_history(
                hass,
                _history_entry(
                    method=method, url=url, headers=headers, payload=payload,
                    result=None, error=f"Timeout: {err}",
                ),
            )
            raise HomeAssistantError(
                f"Timeout when calling resource \"{url}\""
            ) from err
        except aiohttp.ClientError as err:
            await _async_append_history(
                hass,
                _history_entry(
                    method=method, url=url, headers=headers, payload=payload,
                    result=None, error=f"Client error: {err}",
                ),
            )
            raise HomeAssistantError(
                f"Client error occurred when calling resource \"{url}\""
            ) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_REQUEST,
        test_request_service_handler,
        schema=vol.Schema(
            {
                vol.Required(CONF_URL): cv.string,
                vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.All(
                    vol.Lower, vol.In(METHODS)
                ),
                vol.Optional(CONF_HEADERS): vol.Schema({str: cv.string}),
                vol.Optional(CONF_PAYLOAD): cv.string,
                vol.Optional(CONF_CONTENT_TYPE): cv.string,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=60)
                ),
                vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


def _bounded_content(value: Any) -> Any:
    """Truncate a history value so a huge body cannot bloat storage."""
    if isinstance(value, str) and len(value) > HISTORY_MAX_CONTENT_LENGTH:
        return value[:HISTORY_MAX_CONTENT_LENGTH] + "…[truncated]"
    return value


async def _async_load_history(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Load the persisted request history (newest first)."""
    stored = await _history_store(hass).async_load()
    if not isinstance(stored, list):
        return []
    return [entry for entry in stored if isinstance(entry, dict)]


async def _async_append_history(
    hass: HomeAssistant, entry: dict[str, Any]
) -> None:
    """Prepend a history entry, cap the list, and persist it."""
    entries = await _async_load_history(hass)
    entries.insert(0, entry)
    del entries[HISTORY_MAX_ENTRIES:]
    await _history_store(hass).async_save(entries)


async def _async_clear_history(hass: HomeAssistant) -> None:
    """Remove all persisted history entries."""
    await _history_store(hass).async_save([])


def _history_entry(
    *, method: str, url: str, headers: dict[str, Any],
    payload: str | None, result: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a history entry from a request and its outcome."""
    from homeassistant.util import dt as dt_util

    return {
        "timestamp": dt_util.utcnow().isoformat(),
        "method": method,
        "url": url,
        "headers": headers,
        "payload": _bounded_content(payload) if payload else None,
        "status": (result or {}).get("status") if not error else None,
        "content": (
            _bounded_content((result or {}).get("content"))
            if not error and result is not None
            else None
        ),
        "response_headers": (result or {}).get("headers") if not error else None,
        "error": error,
    }


def _register_history_services(hass: HomeAssistant) -> None:
    """Register the get_history and clear_history services."""
    async def get_history_handler(service: ServiceCall) -> dict[str, Any]:
        """Return the persisted request history (newest first)."""
        limit = service.data.get("limit", HISTORY_MAX_ENTRIES)
        entries = await _async_load_history(hass)
        return {"history": entries[:limit]}

    async def clear_history_handler(service: ServiceCall) -> None:
        """Clear the persisted request history."""
        await _async_clear_history(hass)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        get_history_handler,
        schema=vol.Schema(
            {
                vol.Optional("limit", default=HISTORY_MAX_ENTRIES): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=HISTORY_MAX_ENTRIES)
                )
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_HISTORY,
        clear_history_handler,
        schema=vol.Schema({}),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up REST commands from a config entry (GUI-managed)."""
    for subentry in entry.subentries.values():
        _register_command_config(
            hass, command_slug(subentry.data, subentry.title), subentry.data
        )

    _register_test_request(hass)
    _register_history_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    for subentry in entry.subentries.values():
        _unregister_command_config(
            hass, command_slug(subentry.data, subentry.title)
        )
    return True


async def async_reload(hass: HomeAssistant) -> None:
    """Reload REST commands from YAML and re-register GUI subentries."""
    config = await async_integration_yaml_config(hass, DOMAIN)

    # Unregister all services this integration owns (except reload,
    # test_request and the history services, which are re-registered below).
    preserved = {SERVICE_RELOAD, SERVICE_TEST_REQUEST,
                 SERVICE_GET_HISTORY, SERVICE_CLEAR_HISTORY}
    for service in list(hass.services.async_services_for_domain(DOMAIN)):
        if service not in preserved:
            hass.services.async_remove(DOMAIN, service)

    if config is None:
        return

    _register_test_request(hass)
    _register_history_services(hass)

    registered: set[str] = set()

    # Re-register GUI subentries first so YAML cannot silently collide.
    for entry in hass.config_entries.async_entries(DOMAIN):
        for subentry in entry.subentries.values():
            slug = command_slug(subentry.data, subentry.title)
            if slug not in registered:
                _register_command_config(hass, slug, subentry.data)
                registered.add(slug)

    # Register YAML commands not already provided by a subentry.
    configured_yaml = config.get(DOMAIN, {})
    for name, command_config in configured_yaml.items():
        if name not in registered:
            _register_command_config(hass, name, command_config)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle subentry changes."""
    for subentry in entry.subentries.values():
        _unregister_command_config(
            hass, command_slug(subentry.data, subentry.title)
        )
    for subentry in entry.subentries.values():
        _register_command_config(hass, command_slug(subentry.data, subentry.title), subentry.data)


@callback
def _register_command_config(
    hass: HomeAssistant, name: str, command_config: dict[str, Any]
) -> None:
    """Register a REST command as a service from a config mapping."""
    url = command_config[CONF_URL]
    method = str(command_config.get(CONF_METHOD, DEFAULT_METHOD)).upper()
    headers = command_config.get(CONF_HEADERS)
    payload = command_config.get(CONF_PAYLOAD)
    authentication = command_config.get(CONF_AUTHENTICATION)
    username = command_config.get(CONF_USERNAME)
    password = command_config.get(CONF_PASSWORD)
    timeout = command_config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
    content_type = command_config.get(CONF_CONTENT_TYPE, DEFAULT_CONTENT_TYPE)
    verify_ssl = command_config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    skip_url_encoding = command_config.get(CONF_SKIP_URL_ENCODING, False)
    return_response = command_config.get(CONF_RETURN_RESPONSE, False)

    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    auth = None
    if authentication in ("basic", "digest") and username:
        auth = aiohttp.BasicAuth(username, password or "")

    url_template: Template = Template(url, hass)
    payload_template: Template | None = Template(payload, hass) if payload else None
    header_templates: dict[str, Template] = {}
    if headers:
        for key, value in headers.items():
            header_templates[key] = Template(value, hass)

    async def async_service_handler(service: ServiceCall) -> dict[str, Any] | None:
        """Handle a REST command service call."""
        variables = service.data

        request_url = url_template.async_render(variables=variables, parse_result=False)
        request_payload = (
            payload_template.async_render(variables=variables, parse_result=False)
            if payload_template
            else None
        )
        rendered_headers: dict[str, Any] = {}
        for key, template in header_templates.items():
            rendered_headers[key] = template.async_render(
                variables=variables, parse_result=False
            )
        if content_type:
            rendered_headers["Content-Type"] = content_type

        kwargs: dict[str, Any] = {}
        if auth is not None:
            kwargs["auth"] = auth

        try:
            response = await session.request(
                method,
                request_url,
                headers=rendered_headers,
                data=request_payload,
                timeout=client_timeout,
                skip_auto_headers=None,
                **kwargs,
            )
            response.raise_for_status()

            if return_response:
                response_text = await response.text()
                response_headers = {k: v for k, v in response.headers.items()}
                try:
                    response_content = await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    response_content = response_text
                result = {
                    "content": response_content,
                    "status": response.status,
                    "headers": response_headers,
                }
                await _async_append_history(
                    hass,
                    _history_entry(
                        method=method, url=request_url, headers=rendered_headers,
                        payload=request_payload, result=result,
                    ),
                )
                return result

            await response.release()
            return None

        except asyncio.TimeoutError as err:
            if return_response:
                await _async_append_history(
                    hass,
                    _history_entry(
                        method=method, url=request_url, headers=rendered_headers,
                        payload=request_payload, result=None, error=f"Timeout: {err}",
                    ),
                )
            raise HomeAssistantError(
                f"Timeout when calling resource \"{request_url}\""
            ) from err
        except aiohttp.ClientError as err:
            if return_response:
                await _async_append_history(
                    hass,
                    _history_entry(
                        method=method, url=request_url, headers=rendered_headers,
                        payload=request_payload, result=None,
                        error=f"Client error: {err}",
                    ),
                )
            raise HomeAssistantError(
                f"Client error occurred when calling resource \"{request_url}\""
            ) from err

    hass.services.async_register(
        DOMAIN,
        name,
        async_service_handler,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _unregister_command_config(hass: HomeAssistant, name: str) -> None:
    """Unregister a REST command service."""
    hass.services.async_remove(DOMAIN, name)
