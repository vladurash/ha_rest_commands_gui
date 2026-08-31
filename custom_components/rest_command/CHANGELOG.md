# Changelog

## 1.1.0 — Request history + dashboard card

- Add `rest_command.test_request` — fire an arbitrary HTTP request (method, URL, headers, payload, timeout, SSL) and return `{status, content, headers}`.
- Add `rest_command.get_history` — read back recorded requests (newest first).
- Add `rest_command.clear_history` — clear recorded requests.
- Record every `test_request` and every returning command call (newest first, capped at 100 entries).
- Add the `custom:rest-command-card` Lovelace card (request editor + response viewer + clickable history).
- Fix: `test_request` schema used an invalid `vol.boolean`; now `cv.boolean`.

## 1.0.0 — Initial release

- GUI-managed `rest_command` overrides the built-in integration (same domain).
- Add/edit/delete commands from the UI via subentry config flows.
- Backward compatible with YAML `rest_command:` blocks.
- Full options: method, headers, payload, content type, basic/digest auth, SSL, timeout.
- Hot reload via `rest_command.reload`.
