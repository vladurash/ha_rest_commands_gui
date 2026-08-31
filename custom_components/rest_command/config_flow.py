"""Config flow for the RESTful Command integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PAYLOAD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback

from .const import (
    AUTHENTICATION_TYPES,
    CONF_AUTHENTICATION,
    CONF_CONTENT_TYPE,
    CONF_HEADERS,
    CONF_INSECURE_CIPHER,
    CONF_METHOD,
    CONF_RETURN_RESPONSE,
    CONF_SKIP_URL_ENCODING,
    CONF_SLUG,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_METHOD,
    DEFAULT_TIMEOUT,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    METHODS,
)

COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_URL): str,
        vol.Optional(CONF_METHOD, default=DEFAULT_METHOD): vol.In(METHODS),
        vol.Optional(CONF_HEADERS, default=""): str,
        vol.Optional(CONF_PAYLOAD, default=""): str,
        vol.Optional(
            CONF_CONTENT_TYPE, default=DEFAULT_CONTENT_TYPE
        ): str,
        vol.Optional(CONF_AUTHENTICATION, default="none"): vol.In(
            AUTHENTICATION_TYPES
        ),
        vol.Optional(CONF_USERNAME, default=""): str,
        vol.Optional(CONF_PASSWORD, default=""): str,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
        vol.Optional(CONF_INSECURE_CIPHER, default=False): bool,
        vol.Optional(CONF_SKIP_URL_ENCODING, default=False): bool,
        vol.Optional(CONF_RETURN_RESPONSE, default=False): bool,
    }
)


def _process_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalize form input into stored config."""
    data = dict(user_input)
    # Optional free-text fields -> None when empty
    for key in (CONF_HEADERS, CONF_PAYLOAD, CONF_USERNAME, CONF_PASSWORD):
        value = data.get(key)
        if isinstance(value, str) and not value.strip():
            data[key] = None

    # Parse headers free-text (one "Key: Value" per line)
    headers_raw = data.get(CONF_HEADERS) or ""
    if headers_raw:
        parsed_headers: dict[str, str] = {}
        for line in headers_raw.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            parsed_headers[key.strip()] = value.strip()
        data[CONF_HEADERS] = parsed_headers or None
    else:
        data[CONF_HEADERS] = None

    if data.get(CONF_AUTHENTICATION) == "none":
        data[CONF_USERNAME] = None
        data[CONF_PASSWORD] = None

    # Derive a stable service slug from the friendly name so that a name like
    # "demo google form" becomes the valid service key rest_command.demo_google_form.
    # The slug is fixed once created; renaming the friendly title later keeps the
    # same service key so existing automations do not break.
    if CONF_SLUG not in data or not data.get(CONF_SLUG):
        from homeassistant.util import slugify

        data[CONF_SLUG] = slugify(data.get(CONF_NAME) or "command") or "command"

    return data


class RestCommandConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RESTful Command."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentry flows supported by this integration."""
        return {"command": RestCommandSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="RESTful Command",
                data={},
            )

        return self.async_show_form(step_id="user")

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import from YAML configuration.

        YAML configuration is still fully supported by this integration and
        registers services directly, so there is nothing to import into a
        config entry. This step exists only to satisfy the SOURCE_IMPORT path;
        it guides the user to manage commands from the UI instead.
        """
        return self.async_abort(reason="already_configured")


class RestCommandSubentryFlow(ConfigSubentryFlow):
    """Handle a config subentry flow for a REST command."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle a user-flow for adding a command."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_URL].strip():
                errors[CONF_URL] = "invalid_url"
            if not user_input[CONF_NAME].strip():
                errors[CONF_NAME] = "invalid_name"
            if not errors:
                data = _process_input(user_input)
                return self.async_create_entry(
                    title=data[CONF_NAME],
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=COMMAND_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle a reconfiguration flow for an existing command."""
        errors: dict[str, str] = {}
        current = self._get_reconfigure_subentry().data

        schema = _prefill_schema(current)

        if user_input is not None:
            if not user_input[CONF_URL].strip():
                errors[CONF_URL] = "invalid_url"
            if not user_input[CONF_NAME].strip():
                errors[CONF_NAME] = "invalid_name"
            if not errors:
                data = _process_input(user_input)
                return self.async_update_and_abort(
                    entry=self._get_entry(),
                    subentry=self._get_reconfigure_subentry(),
                    title=data[CONF_NAME],
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )


def _prefill_schema(current: dict[str, Any]) -> vol.Schema:
    """Build a schema pre-filled with current subentry data."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get(CONF_NAME, "")): str,
            vol.Required(CONF_URL, default=current.get(CONF_URL, "")): str,
            vol.Optional(
                CONF_METHOD, default=current.get(CONF_METHOD, DEFAULT_METHOD)
            ): vol.In(METHODS),
            vol.Optional(CONF_HEADERS, default=_headers_to_text(current)): str,
            vol.Optional(CONF_PAYLOAD, default=current.get(CONF_PAYLOAD) or ""): str,
            vol.Optional(
                CONF_CONTENT_TYPE,
                default=current.get(CONF_CONTENT_TYPE, DEFAULT_CONTENT_TYPE),
            ): str,
            vol.Optional(
                CONF_AUTHENTICATION,
                default=current.get(CONF_AUTHENTICATION, "none"),
            ): vol.In(AUTHENTICATION_TYPES),
            vol.Optional(
                CONF_USERNAME, default=current.get(CONF_USERNAME) or ""
            ): str,
            vol.Optional(
                CONF_PASSWORD, default=current.get(CONF_PASSWORD) or ""
            ): str,
            vol.Optional(
                CONF_TIMEOUT, default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            vol.Optional(
                CONF_VERIFY_SSL, default=current.get(CONF_VERIFY_SSL, True)
            ): bool,
            vol.Optional(
                CONF_INSECURE_CIPHER, default=current.get(CONF_INSECURE_CIPHER, False)
            ): bool,
            vol.Optional(
                CONF_SKIP_URL_ENCODING,
                default=current.get(CONF_SKIP_URL_ENCODING, False),
            ): bool,
            vol.Optional(
                CONF_RETURN_RESPONSE, default=current.get(CONF_RETURN_RESPONSE, False)
            ): bool,
        }
    )


def _headers_to_text(current: dict[str, Any]) -> str:
    headers = current.get(CONF_HEADERS) or {}
    if not headers:
        return ""
    return "\n".join(f"{k}: {v}" for k, v in headers.items())
