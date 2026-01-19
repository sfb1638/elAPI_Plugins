import os

from elapi.api import FixedEndpoint

_ENDPOINT_MAP = {
    "resources": "items",
    "categories": "items_types",
    "experiments": "experiments",
}


def get_fixed(name: str) -> FixedEndpoint:
    """Return a FixedEndpoint for one of: resource, category, experiments."""
    # Sanitize ELN host env vars that the elapi client uses; stray spaces cause DNS errors.
    for env_key in ("ELABFTW_HOST", "ELAB_API_URL", "ELABFTW_URL"):
        val = os.environ.get(env_key)
        if val:
            cleaned = val.strip().replace(" ", "")
            if cleaned != val:
                os.environ[env_key] = cleaned

    try:
        path = _ENDPOINT_MAP[name]
    except KeyError as exc:
        raise ValueError(f"No endpoint configured for '{name}'") from exc
    return FixedEndpoint(path)
