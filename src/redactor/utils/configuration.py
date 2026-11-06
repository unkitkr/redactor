"""Read TOML configuration without copying environment secrets into settings."""

import base64
import binascii
import hashlib
import hmac
import json
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from redactor.schemas.configuration import PipelineSettings
from redactor.utils.constants import (
    CONFIGURATION_FILENAME,
    ENVIRONMENT_FALSE,
    ENVIRONMENT_TRUE,
    JSON_SEPARATORS,
    MAPPING_KEY_ENVIRONMENT,
    MODEL_ENABLED_ENVIRONMENT,
    MODEL_NAME_ENVIRONMENT,
    MODEL_URL_ENVIRONMENT,
    PIPELINE_VERSION,
    SECRET_KEY_BYTES,
    STATE_KEY_CONTEXT,
    TEXT_ENCODING,
)
from redactor.utils.errors import ERROR_CONFIGURATION, ERROR_MAPPING_KEY


def load_settings(
    path: Path | None = None, *, environment: Mapping[str, str] | None = None
) -> PipelineSettings:
    """Explicit paths must exist; an absent default file uses validated defaults."""
    environment = os.environ if environment is None else environment
    configuration_path = path if path is not None else Path(CONFIGURATION_FILENAME)
    try:
        if path is None and not configuration_path.exists():
            settings = PipelineSettings()
        else:
            with configuration_path.open("rb") as stream:
                settings = PipelineSettings.model_validate(tomllib.load(stream))

        remote = settings.remote.model_dump()
        if MODEL_URL_ENVIRONMENT in environment:
            remote["base_url"] = environment[MODEL_URL_ENVIRONMENT]
        if MODEL_NAME_ENVIRONMENT in environment:
            remote["model"] = environment[MODEL_NAME_ENVIRONMENT]
        if MODEL_ENABLED_ENVIRONMENT in environment:
            enabled = environment[MODEL_ENABLED_ENVIRONMENT].lower()
            if enabled not in (*ENVIRONMENT_TRUE, *ENVIRONMENT_FALSE):
                raise ValueError(ERROR_CONFIGURATION)
            remote["enabled"] = enabled in ENVIRONMENT_TRUE

        values = settings.model_dump()
        values["remote"] = remote
        local = settings.local.model_dump()
        configuration_directory = configuration_path.resolve().parent
        for name in ("model_directory", "ner_directory", "ocr_directory"):
            directory = local[name]
            if directory is not None:
                local[name] = (configuration_directory / directory).resolve()
        values["local"] = local
        return PipelineSettings.model_validate(values)
    except (OSError, ValueError, ValidationError):
        # TOML and validation errors can echo supplied values, including secrets.
        raise ValueError(ERROR_CONFIGURATION) from None


def processing_fingerprint(settings: PipelineSettings) -> str:
    """Remote availability may change during recovery; processing choices may not."""
    processing = settings.model_dump(mode="json")
    del processing["remote"]["enabled"]
    payload = json.dumps(
        (PIPELINE_VERSION, processing), sort_keys=True, separators=JSON_SEPARATORS
    ).encode(TEXT_ENCODING)
    return hashlib.sha256(payload).hexdigest()


def read_mapping_key(environment: Mapping[str, str] | None = None) -> bytes:
    """Require a caller-provided base64 key; never generate a different replay key."""
    environment = os.environ if environment is None else environment
    try:
        key = base64.b64decode(environment[MAPPING_KEY_ENVIRONMENT], validate=True)
    except (KeyError, ValueError, binascii.Error):
        raise ValueError(ERROR_MAPPING_KEY) from None
    if len(key) != SECRET_KEY_BYTES:
        raise ValueError(ERROR_MAPPING_KEY)
    return key


def key_fingerprint(key: bytes) -> str:
    """Bind private state to its key without storing the secret itself."""
    if len(key) != SECRET_KEY_BYTES:
        raise ValueError(ERROR_MAPPING_KEY)
    return hmac.digest(key, STATE_KEY_CONTEXT, "sha256").hex()
