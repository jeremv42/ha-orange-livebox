# Orange Livebox — Home Assistant custom integration

Domain `orange_livebox`, code in `custom_components/orange_livebox/`.

- `api.py` is the Livebox sysbus client and must stay free of `homeassistant`
  imports (it is loaded standalone by `scripts/probe.py`).
- All data is fetched in one `LiveboxClient.async_fetch_all()` call per refresh
  (sequential on purpose, the box is slow) into a `LiveboxData` dataclass.
  Model-specific calls go through `_optional()`, which returns `None` and
  stops calling a method once the box rejects it.
- Entities are created only when their data exists (`exists_fn`).
- New entity names go in `strings.json`, then copy it to `translations/en.json`
  and update `translations/fr.json`.
- The client needs a cookie jar with `unsafe=True` (cookies from an IP host).

Commands: `.venv/bin/pytest`, `scripts/lint`, `scripts/develop`.
The HA version follows `pytest-homeassistant-custom-component` (needs Python 3.14).
