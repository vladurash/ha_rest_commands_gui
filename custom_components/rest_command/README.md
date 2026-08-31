# RESTful Command (GUI)

A drop-in, GUI-enabled replacement for Home Assistant's built-in **RESTful Command** (`rest_command`) integration.

Configure REST API calls entirely from the **Settings → Devices & Services** UI instead of YAML. Each command becomes a `rest_command.<name>` service you can call from automations, scripts, or your dashboard.

## Features

- **Fully GUI-managed** — add, edit, and delete REST commands from the UI (subentry flows)
- **Backward compatible** — existing YAML `rest_command:` blocks still work unchanged
- **Template support** — Jinja2 in `url`, `payload`, and header values
- **Response support** — returns `content`, `status`, and `headers` via `response_variable`
- **All options covered** — method, headers, payload, content type, basic/digest auth, SSL, timeout
- **Hot reload** — `rest_command.reload` and subentry edits apply without a restart
- **Same domain** — uses `rest_command` so your existing automations keep working
- **Postman-like `test_request` service** — fire any raw request (method, url, headers, payload, timeout…) on the fly and read back `{status, content, headers}`
- **Built-in request history** — `test_request` and returning commands are recorded; read them back with `rest_command.get_history` and clear with `rest_command.clear_history`
- **Dashboard card** — a `custom:rest-command-card` Lovelace card with a request editor, response viewer, and a clickable history list

## Installation (HACS)

1. Add this repository to HACS as a Custom Repository.
2. Search for **RESTful Command (GUI)** and download it.
3. Restart Home Assistant.

## Manual Installation

Copy the `custom_components/rest_command/` folder into your HA `custom_components/` directory and restart.

## Usage

1. Go to **Settings → Devices & Services → Add Integration** → **RESTful Command**.
2. Once added, open the entry and use **Add command** (subentry) to define each REST call.
3. Call the resulting `rest_command.<name>` service from automations or scripts.

Example call:
```yaml
action: rest_command.turn_on_light
data:
  brightness: 200
```

Response capture:
```yaml
action: rest_command.check_status
response_variable: result
```

## YAML Compatibility

Commands defined in YAML (e.g. in `packages/`) are still registered as services and coexist with UI-managed commands. The UI is the intended way to add new commands; YAML remains supported so existing configurations keep working.

## Arbitrary Requests (`test_request`)

Fire any request without pre-configuring a command:

```yaml
action: rest_command.test_request
response_variable: result
data:
  url: "https://api.example.com/data"
  method: post
  headers:
    Accept: application/json
  payload: '{"value": 42}'
```

Returns `result.response` as `{status, content, headers}` (content is JSON when the endpoint returns JSON, otherwise raw text).

## Request History

Every `test_request` call, and every command call whose command has **return_response** enabled, is recorded (newest first, capped at 100 entries).

Read the history:
```yaml
action: rest_command.get_history
response_variable: history
data:
  limit: 20
# -> history.response = { "history": [ ... ] }
```

Clear the history:
```yaml
action: rest_command.clear_history
```

## Dashboard Card

The optional `custom:rest-command-card` card gives you a Postman-like UI: edit method/url/headers/payload, send, view the status badge + response headers/body, and click any history row to reload that request.

1. Copy `www/rest-command-card.js` to your `/config/www/` folder.
2. Add it as a Lovelace resource: `/local/rest-command-card.js`, type **JavaScript Module**.
3. Add a `custom:rest-command-card` card to any dashboard.

## License

MIT
