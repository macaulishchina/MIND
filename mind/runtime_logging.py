from __future__ import annotations

import logging
import sys

from mind.config.schema import LoggingConfig
from mind.ops_logger import ops

_HANDLER_MARKER = "_mind_managed_handler"


def configure_runtime_logging(log_cfg: LoggingConfig) -> None:
    """Apply runtime logging config for the ``mind`` logger subtree.

    This is the shared bootstrap for any entrypoint that executes MIND runtime
    operations directly from a resolved config, regardless of whether it goes
    through ``Memory``.
    """

    mind_logger = logging.getLogger("mind")
    level = getattr(logging, log_cfg.level.upper(), logging.INFO)
    formatter = logging.Formatter(log_cfg.format)

    mind_logger.setLevel(level)

    for handler in list(mind_logger.handlers):
        if not getattr(handler, _HANDLER_MARKER, False):
            continue
        mind_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    if log_cfg.console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        setattr(console_handler, _HANDLER_MARKER, True)
        mind_logger.addHandler(console_handler)

    if log_cfg.file:
        file_handler = logging.FileHandler(log_cfg.file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        mind_logger.addHandler(file_handler)

    ops.configure(
        ops_llm=log_cfg.ops_llm,
        ops_vector_store=log_cfg.ops_vector_store,
        ops_database=log_cfg.ops_database,
        verbose=log_cfg.verbose,
    )
