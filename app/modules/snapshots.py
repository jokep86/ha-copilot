"""
Entity state snapshots and text diff — Phase 7.

/snapshot save [name]   — save all current entity states to DB
/snapshot diff [name]   — text diff: saved snapshot vs current states
/snapshot list          — list all saved snapshots
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger
from app.schemas.snapshot_schema import SnapshotDiff

if TYPE_CHECKING:
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_MAX_DIFF_LINES = 50
_MAX_MSG = 3800


class SnapshotsModule(ModuleBase):
    name = "snapshots"
    description = "Entity state snapshots and diff"
    commands: list[str] = ["snapshot"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._db = app.db

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self,
        cmd: str,
        args: list[str],
        context: "CommandContext",
    ) -> None:
        sub = args[0].lower() if args else "list"

        if sub == "save":
            name = args[1] if len(args) > 1 else _default_name()
            await self._cmd_save(name, context)
        elif sub == "diff":
            name = args[1] if len(args) > 1 else None
            await self._cmd_diff(name, context)
        elif sub == "list":
            await self._cmd_list(context)
        else:
            await self._reply(
                context,
                "Usage: `/snapshot save [name]`, `/snapshot diff [name]`, `/snapshot list`",
            )

    # ------------------------------------------------------------------ #

    async def _cmd_save(self, name: str, context: "CommandContext") -> None:
        try:
            states = await self._ha.get_states()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot fetch states: {exc}"))
            return

        states_map = {s["entity_id"]: s for s in states}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        await self._db.conn.execute(
            """
            INSERT INTO entity_snapshots (name, timestamp, user_id, states, entity_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, now, context.user_id, json.dumps(states_map), len(states_map)),
        )
        await self._db.conn.commit()

        logger.info("snapshot_saved", name=name, entity_count=len(states_map))
        await self._reply(
            context,
            success_msg(f"Snapshot '{name}' saved ({len(states_map)} entities)."),
        )

    async def _cmd_diff(self, name: str | None, context: "CommandContext") -> None:
        # Resolve snapshot: by name or most recent
        if name:
            cursor = await self._db.conn.execute(
                "SELECT name, timestamp, states FROM entity_snapshots "
                "WHERE name = ? ORDER BY timestamp DESC LIMIT 1",
                (name,),
            )
        else:
            cursor = await self._db.conn.execute(
                "SELECT name, timestamp, states FROM entity_snapshots "
                "ORDER BY timestamp DESC LIMIT 1"
            )
        row = await cursor.fetchone()
        if not row:
            msg = f"Snapshot '{name}' not found\\." if name else "No snapshots saved\\."
            await self._reply(context, msg)
            return

        snap_name, snap_ts, states_json = row[0], row[1], row[2]
        saved_states: dict = json.loads(states_json)

        try:
            current_states_list = await self._ha.get_states()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot fetch current states: {exc}"))
            return

        current_states = {s["entity_id"]: s for s in current_states_list}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        diff = _compute_diff(snap_name, snap_ts, now, saved_states, current_states)
        await self._send_diff(diff, context)

    async def _cmd_list(self, context: "CommandContext") -> None:
        cursor = await self._db.conn.execute(
            "SELECT name, timestamp, entity_count FROM entity_snapshots "
            "ORDER BY timestamp DESC LIMIT 20"
        )
        rows = await cursor.fetchall()
        if not rows:
            await self._reply(context, "No snapshots saved\\.")
            return

        lines = [bold("Snapshots"), ""]
        for r in rows:
            ts = r[1][:16].replace("T", " ")
            lines.append(
                f"• {code(escape_md(r[0]))} — {escape_md(ts)} "
                f"\\({r[2]} entities\\)"
            )
        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _send_diff(self, diff: SnapshotDiff, context: "CommandContext") -> None:
        lines = [
            bold(f"Snapshot diff: {escape_md(diff.snapshot_name)}"),
            f"_Saved: {escape_md(diff.snapshot_timestamp[:16].replace('T', ' '))} UTC_",
            "",
        ]

        if diff.added:
            lines.append(f"➕ Added \\({len(diff.added)}\\):")
            for eid in diff.added[:20]:
                lines.append(f"  `{escape_md(eid)}`")

        if diff.removed:
            lines.append(f"➖ Removed \\({len(diff.removed)}\\):")
            for eid in diff.removed[:20]:
                lines.append(f"  `{escape_md(eid)}`")

        if diff.changed:
            lines.append(f"🔄 Changed \\({len(diff.changed)}\\):")
            for eid, (old, new) in list(diff.changed.items())[:_MAX_DIFF_LINES]:
                lines.append(
                    f"  `{escape_md(eid)}`: "
                    f"{code(escape_md(old))} → {code(escape_md(new))}"
                )

        if not diff.added and not diff.removed and not diff.changed:
            lines.append("✅ No state changes since snapshot\\.")
        else:
            lines.append(f"\n_{diff.unchanged_count} entities unchanged_")

        msg = "\n".join(lines)
        if len(msg) > _MAX_MSG:
            msg = msg[:_MAX_MSG] + "\n_\\.\\.\\. truncated_"

        await context.update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _default_name() -> str:
    return datetime.now(timezone.utc).strftime("snap_%Y%m%d_%H%M")


def _compute_diff(
    snap_name: str,
    snap_ts: str,
    now: str,
    saved: dict,
    current: dict,
) -> SnapshotDiff:
    saved_ids = set(saved.keys())
    current_ids = set(current.keys())

    added = sorted(current_ids - saved_ids)
    removed = sorted(saved_ids - current_ids)
    changed: dict[str, tuple[str, str]] = {}
    unchanged = 0

    for eid in saved_ids & current_ids:
        old_state = saved[eid].get("state", "")
        new_state = current[eid].get("state", "")
        if old_state != new_state:
            changed[eid] = (str(old_state), str(new_state))
        else:
            unchanged += 1

    return SnapshotDiff(
        snapshot_name=snap_name,
        snapshot_timestamp=snap_ts,
        current_timestamp=now,
        added=added,
        removed=removed,
        changed=changed,
        unchanged_count=unchanged,
    )
