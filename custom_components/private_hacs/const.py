"""Constants for the Private HACS integration."""
from __future__ import annotations

DOMAIN = "private_hacs"

CONF_GITHUB_TOKEN = "github_token"

# Per-repo config keys
CONF_FULL_NAME = "full_name"
CONF_REF_TYPE = "ref_type"
CONF_REF = "ref"
CONF_INTEGRATION_NAME = "integration_name"

REF_TYPE_RELEASE = "release"
REF_TYPE_TAG = "tag"
REF_TYPE_BRANCH = "branch"
REF_TYPE_COMMIT = "commit"

VALID_REF_TYPES = (
    REF_TYPE_RELEASE,
    REF_TYPE_TAG,
    REF_TYPE_BRANCH,
    REF_TYPE_COMMIT,
)

STORAGE_KEY = f"{DOMAIN}.repositories"
STORAGE_VERSION = 1

GITHUB_API_BASE = "https://api.github.com"
USER_AGENT = "private-hacs"

SERVICE_ADD_REPOSITORY = "add_repository"
SERVICE_REMOVE_REPOSITORY = "remove_repository"
SERVICE_INSTALL = "install"
SERVICE_UPDATE = "update"
