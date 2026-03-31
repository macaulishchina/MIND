"""Centralised operations logger for MIND.

All emoji-formatted operational logging lives here — one file,
one configuration surface, zero Shotgun Surgery.

Usage (in any module)::

    from mind.ops_logger import ops

    ops.llm_call(provider, model, n_msgs, in_tok, out_tok, elapsed)
    ops.llm_error(provider, model, n_msgs, in_tok, elapsed)

    ops.emb_call(provider, model, text_len, dim, elapsed)
    ops.emb_error(provider, model, text_len, elapsed)

    ops.vec_op("INSERT", collection, url, elapsed, id=mid)
    ops.vec_error("INSERT", collection, url, elapsed, id=mid)

    ops.db_op("INSERT", table, db_path, elapsed, detail="mem=xxx")
    ops.db_error("INSERT", table, db_path, elapsed, detail="mem=xxx")

    # verbose-only details (only printed when verbose=True)
    ops.verbose_detail("prompt → ...", "response → ...")

Configuration::

    [logging]
    ops_llm          = true
    ops_vector_store = true
    ops_database     = true
    verbose          = false      # show raw I/O under each summary line
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Sequence

logger = logging.getLogger("mind.ops")

# Thread-local context tag (e.g. "[fact:2/4]") for concurrent tracing
_ctx = threading.local()

# ── Default truncation for verbose content ──
_VERBOSE_MAX_LEN = 500


@dataclass
class _Switches:
    """Runtime toggle state — set once by ``OpsLogger.configure()``."""
    llm: bool = True
    vector_store: bool = True
    database: bool = True
    verbose: bool = False


class OpsLogger:
    """Singleton-style operations logger.

    Call ``configure()`` once (typically from ``Memory.__init__``).
    All subsequent calls use the cached switches — zero per-call overhead
    beyond a simple ``if`` check.
    """

    def __init__(self) -> None:
        self._sw = _Switches()

    # ------------------------------------------------------------------
    # Context tag (for concurrent fact tracing)
    # ------------------------------------------------------------------

    @staticmethod
    def set_context(tag: str) -> None:
        """Set a thread-local context tag that prefixes all log lines.

        Example::

            ops.set_context("[fact:2/4]")
            # ... all subsequent ops.* calls in this thread get the prefix
            ops.clear_context()
        """
        _ctx.tag = tag

    @staticmethod
    def clear_context() -> None:
        """Remove the thread-local context tag."""
        _ctx.tag = ""

    @staticmethod
    def _tag() -> str:
        """Return current context tag with trailing space, or empty."""
        t = getattr(_ctx, "tag", "")
        return f"{t} " if t else ""

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        ops_llm: bool = True,
        ops_vector_store: bool = True,
        ops_database: bool = True,
        verbose: bool = False,
    ) -> None:
        """Apply logging switches from ``LoggingConfig``."""
        self._sw = _Switches(
            llm=ops_llm,
            vector_store=ops_vector_store,
            database=ops_database,
            verbose=verbose,
        )

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def llm_start(
        self,
        provider: str,
        model: str,
        n_msgs: int,
        in_tok: int,
        *,
        prompt_name: Optional[str] = None,
        messages: Optional[Sequence[dict]] = None,
    ) -> None:
        """Log the start of an LLM call (before waiting for response)."""
        if not self._sw.llm:
            return
        tag = self._tag()
        prompt_part = f" | {prompt_name}" if prompt_name else ""
        logger.info(
            "%s🧠 [LLM] ▶ %s | %s | %d msgs | ~%d in_tok%s",
            tag, provider, model, n_msgs, in_tok, prompt_part,
        )
        if self._sw.verbose and messages:
            for m in messages:
                role = m.get("role", "?")
                content = m.get("content", "")
                logger.info("  ┊ [%s]\n%s", role, content)
            logger.info("  ┊ ── end of request ──")

    def llm_call(
        self,
        provider: str,
        model: str,
        n_msgs: int,
        in_tok: int,
        out_tok: int,
        elapsed: float,
        *,
        prompt_name: Optional[str] = None,
        messages: Optional[Sequence[dict]] = None,
        response: Optional[str] = None,
    ) -> None:
        """Log a successful LLM call."""
        if not self._sw.llm:
            return
        tag = self._tag()
        logger.info(
            "%s🧠 [LLM] ── %s | %s | %d msgs | ~%d in_tok | ~%d out_tok | %.2fs ──",
            tag, provider, model, n_msgs, in_tok, out_tok, elapsed,
        )
        if self._sw.verbose and response:
            logger.info("  ┊ [response]\n%s", response)
            logger.info("  ┊ ── end of response ──")

    def llm_error(
        self,
        provider: str,
        model: str,
        n_msgs: int,
        in_tok: int,
        elapsed: float,
    ) -> None:
        """Log a failed LLM call (always logged regardless of switch)."""
        tag = self._tag()
        logger.error(
            "%s🧠 [LLM] ── %s | %s | %d msgs | ~%d in_tok | FAILED | %.2fs ──",
            tag, provider, model, n_msgs, in_tok, elapsed,
        )

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def emb_call(
        self,
        provider: str,
        model: str,
        text_len: int,
        dim: int,
        elapsed: float,
        *,
        text: Optional[str] = None,
        vector_preview: Optional[Sequence[float]] = None,
    ) -> None:
        """Log a successful embedding call."""
        if not self._sw.llm:          # shares the LLM switch
            return
        tag = self._tag()
        logger.info(
            "%s🔗 [EMB] ── %s | %s | %d chars | dim=%d | %.2fs ──",
            tag, provider, model, text_len, dim, elapsed,
        )
        if self._sw.verbose and text:
            logger.info("  ┊ input   → %s", text[:_VERBOSE_MAX_LEN])

    def emb_error(
        self,
        provider: str,
        model: str,
        text_len: int,
        elapsed: float,
    ) -> None:
        """Log a failed embedding call (always logged)."""
        tag = self._tag()
        logger.error(
            "%s🔗 [EMB] ── %s | %s | %d chars | FAILED | %.2fs ──",
            tag, provider, model, text_len, elapsed,
        )

    # ------------------------------------------------------------------
    # Vector Store
    # ------------------------------------------------------------------

    def vec_op(
        self,
        action: str,
        collection: str,
        url: str,
        elapsed: float,
        *,
        id: Optional[str] = None,
        limit: Optional[int] = None,
        hits: Optional[int] = None,
        found: Optional[str] = None,
        count: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Log a successful vector store operation."""
        if not self._sw.vector_store:
            return
        parts = [f"📦 [VEC] ── {action}", f"{collection} @ {url}"]
        if id is not None:
            parts.append(f"id={id}")
        if limit is not None:
            parts.append(f"limit={limit}")
        if hits is not None:
            parts.append(f"hits={hits}")
        if found is not None:
            parts.append(found)
        if count is not None:
            parts.append(f"count={count}")
        parts.append(f"{elapsed:.3f}s ──")
        logger.info("%s%s", self._tag(), " | ".join(parts))
        if self._sw.verbose and detail:
            logger.info("  ┊ detail  → %s", detail[:_VERBOSE_MAX_LEN])

    def vec_error(
        self,
        action: str,
        collection: str,
        url: str,
        elapsed: float,
        *,
        id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        """Log a failed vector store operation (always logged)."""
        parts = [f"📦 [VEC] ── {action}", f"{collection} @ {url}"]
        if id is not None:
            parts.append(f"id={id}")
        if limit is not None:
            parts.append(f"limit={limit}")
        parts.append(f"FAILED | {elapsed:.3f}s ──")
        logger.error("%s%s", self._tag(), " | ".join(parts))

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def db_op(
        self,
        action: str,
        table: str,
        db_path: str,
        elapsed: float,
        *,
        detail: Optional[str] = None,
        rows: Optional[int] = None,
    ) -> None:
        """Log a successful database operation."""
        if not self._sw.database:
            return
        parts = [f"💾 [DB] ── {action}", f"{table} @ {db_path}"]
        if detail:
            parts.append(detail)
        if rows is not None:
            parts.append(f"rows={rows}")
        parts.append(f"{elapsed:.3f}s ──")
        logger.info("%s%s", self._tag(), " | ".join(parts))

    def db_error(
        self,
        action: str,
        table: str,
        db_path: str,
        elapsed: float,
        *,
        detail: Optional[str] = None,
    ) -> None:
        """Log a failed database operation (always logged)."""
        parts = [f"💾 [DB] ── {action}", f"{table} @ {db_path}"]
        if detail:
            parts.append(detail)
        parts.append(f"FAILED | {elapsed:.3f}s ──")
        logger.error("%s%s", self._tag(), " | ".join(parts))

    # ------------------------------------------------------------------
    # Generic verbose helper
    # ------------------------------------------------------------------

    def verbose_detail(self, *lines: str) -> None:
        """Print indented detail lines (only when verbose is on)."""
        if not self._sw.verbose:
            return
        for line in lines:
            logger.info("  ┊ %s", line[:_VERBOSE_MAX_LEN])


# ── Module-level singleton ──
ops = OpsLogger()
