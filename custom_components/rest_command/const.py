"""Constants for the RESTful Command integration."""

DOMAIN = "rest_command"

CONF_URL = "url"
CONF_SLUG = "slug"
CONF_METHOD = "method"
CONF_HEADERS = "headers"
CONF_PAYLOAD = "payload"
CONF_AUTHENTICATION = "authentication"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TIMEOUT = "timeout"
CONF_CONTENT_TYPE = "content_type"
CONF_VERIFY_SSL = "verify_ssl"
CONF_INSECURE_CIPHER = "insecure_cipher"
CONF_SKIP_URL_ENCODING = "skip_url_encoding"
CONF_RETURN_RESPONSE = "return_response"

DEFAULT_METHOD = "get"
DEFAULT_TIMEOUT = 10
DEFAULT_VERIFY_SSL = True
DEFAULT_CONTENT_TYPE = "application/json"

METHODS = ["get", "post", "put", "patch", "delete"]
AUTHENTICATION_TYPES = ["none", "basic", "digest"]

SERVICE_RELOAD = "reload"
SERVICE_TEST_REQUEST = "test_request"
SERVICE_GET_HISTORY = "get_history"
SERVICE_CLEAR_HISTORY = "clear_history"

HISTORY_STORAGE_KEY = f"{DOMAIN}.history"
HISTORY_STORAGE_VERSION = 1
HISTORY_MAX_ENTRIES = 100
HISTORY_MAX_CONTENT_LENGTH = 8192
