# Copyright (c) Microsoft. All rights reserved.

"""Compatibility imports for the canonical :mod:`tools.mail_monitoring` module."""

from .tools.mail_monitoring import (
    MAIL_FILTER_VERSION,
    MAX_FILTER_CONDITIONS,
    AzureBlobMailMonitoringStore,
    LocalFileMailMonitoringStore,
    MailFilterValidationError,
    MailMonitoringStorageError,
    describe_filter,
    matches_filter,
    normalize_filter,
)

__all__ = [
    "MAIL_FILTER_VERSION",
    "MAX_FILTER_CONDITIONS",
    "AzureBlobMailMonitoringStore",
    "LocalFileMailMonitoringStore",
    "MailFilterValidationError",
    "MailMonitoringStorageError",
    "describe_filter",
    "matches_filter",
    "normalize_filter",
]
