"""
Automation CRUD — Phase 4.

/auto                       — list all automations
/auto <query> on|off        — enable / disable
/auto <query> trigger       — manual trigger
/auto <query> show          — display YAML
/auto <query> delete        — delete (requires confirm)
/auto create <description>  — Claude YAML → preview → confirm → create
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from app.bot.formatters import bold, code, error_msg, escape_md, success_msg
from app.core.module_base import ModuleBase
from app.observability.logger import get_logger

if TYPE_CHECKING:
    from app.ai.yaml_generator import YAMLGenerator
    from app.bot.handler import CommandContext
    from app.core.module_registry import AppContext

logger = get_logger(__name__)

_COPILOT_TAG = "ha_copilot"


class AutomationsModule(ModuleBase):
    name = "automations"
    description = "Automation CRUD"
    commands: list[str] = ["auto"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._generator: YAMLGenerator | None = None

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if not args:
            await self._cmd_list(context)
            return

        sub = args[0].lower()

        if sub == "create":
            description = " ".join(args[1:])
            await self._cmd_create(description, context)
        else:
            # /auto <query> <action>
            if len(args) < 2:
                await self._reply(
                    context,
                    "Usage: /auto \\<query\\> on\\|off\\|trigger\\|show\\|delete\n"
                    "Or: /auto create \\<description\\>",
                )
                return
            query = args[0]
            action = args[1].lower()
            await self._cmd_action(query, action, args[2:], context)

    # ------------------------------------------------------------------ #

    async def _cmd_list(self, context: "CommandContext") -> None:
        try:
            autos = await self._ha.get_automations()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot list automations: {exc}"))
            return

        if not autos:
            await self._reply(context, "No automations found\\.")
            return

        lines = [bold("Automations"), ""]
        for a in autos[:30]:
            alias = a.get("alias", a.get("id", "?"))
            aid = a.get("id", "?")
            mode = a.get("mode", "single")
            tag = " 🤖" if _COPILOT_TAG in a.get("description", "") else ""
            lines.append(f"• {escape_md(alias)}{tag}\n  {code(aid)} \\[{escape_md(mode)}\\]")

        if len(autos) > 30:
            lines.append(f"\n_… and {len(autos) - 30} more_")
        lines.append(f"\n_{len(autos)} total_")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_action(
        self, query: str, action: str, extra_args: list[str], context: "CommandContext"
    ) -> None:
        # Find automation
        try:
            autos = await self._ha.get_automations()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get automations: {exc}"))
            return

        auto = self._find(autos, query)
        if not auto:
            await self._reply(
                context, escape_md(f"No automation matching '{query}'.")
            )
            return

        alias = auto.get("alias", auto.get("id", "?"))
        auto_id = auto.get("id", "")
        # Derive entity_id from alias: automation.<snake_case_alias>
        entity_id = self._to_entity_id(alias)

        if action == "show":
            import json
            preview = json.dumps(auto, indent=2, ensure_ascii=False)
            if len(preview) > 3500:
                preview = preview[:3500] + "\n…"
            await context.update.message.reply_text(
                f"{bold(escape_md(alias))}\n```json\n{preview}\n```",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

        elif action in ("on", "off"):
            service = "turn_on" if action == "on" else "turn_off"
            try:
                await self._ha.call_service("automation", service, {"entity_id": entity_id})
                icon = "🟢" if action == "on" else "🔴"
                await self._reply(
                    context, success_msg(f"Automation '{alias}' → {action}")
                )
            except Exception as exc:
                await self._reply(context, error_msg(f"Failed: {exc}"))

        elif action == "trigger":
            try:
                await self._ha.call_service("automation", "trigger", {"entity_id": entity_id})
                await self._reply(context, success_msg(f"Automation '{alias}' triggered."))
            except Exception as exc:
                await self._reply(context, error_msg(f"Failed: {exc}"))

        elif action == "delete":
            confirmed = extra_args and extra_args[0] == "confirm"
            if not confirmed:
                # Offer inline confirm/cancel via PendingActions
                pending = self._app.extra.get("pending_actions")
                if pending:
                    captured_id = auto_id
                    captured_alias = alias

                    async def _do_delete(_action: Any, _ctx: "CommandContext") -> None:
                        await self._ha.delete_automation(captured_id)
                        await _ctx.update.message.reply_text(
                            success_msg(f"Automation '{captured_alias}' deleted."),
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )

                    action_id = await pending.store(
                        action=None,
                        trace_id=str(uuid.uuid4())[:8],
                        user_id=context.user_id,
                        executor=_do_delete,
                        context=context,
                    )
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Delete", callback_data=f"confirm:{action_id}"),
                        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action_id}"),
                    ]])
                    await context.update.message.reply_text(
                        f"⚠️ Delete automation {bold(escape_md(alias))}?",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=keyboard,
                    )
                else:
                    await self._reply(
                        context,
                        f"⚠️ Delete {code(escape_md(alias))}\\?\n"
                        f"Send `/auto {escape_md(query)} delete confirm` to proceed\\.",
                    )
            else:
                try:
                    await self._ha.delete_automation(auto_id)
                    await self._reply(context, success_msg(f"Automation '{alias}' deleted."))
                except Exception as exc:
                    await self._reply(context, error_msg(f"Delete failed: {exc}"))
        else:
            await self._reply(
                context,
                f"Unknown action {code(action)}\\. Use: on, off, trigger, show, delete",
            )

    async def _cmd_create(self, description: str, context: "CommandContext") -> None:
        if not description.strip():
            await self._reply(context, "Usage: /auto create \\<description\\>")
            return

        if not self._app.config.ai_enabled:
            await self._reply(context, "AI is disabled\\. Enable `ai_enabled` to create automations\\.")
            return

        await self._reply(context, "🤖 Generating automation YAML…")

        # Lazy-init generator
        if not self._generator:
            from app.ai.yaml_generator import YAMLGenerator
            self._generator = YAMLGenerator(
                config=self._app.config,
                discovery=self._app.extra.get("discovery"),
            )

        try:
            auto_config = await self._generator.generate_automation(description)
        except Exception as exc:
            await self._reply(context, error_msg(f"YAML generation failed: {exc}"))
            return

        # Show preview
        import json
        preview = json.dumps(auto_config.model_dump(exclude_none=True), indent=2)
        if len(preview) > 2500:
            preview = preview[:2500] + "\n…"

        pending = self._app.extra.get("pending_actions")
        if not pending:
            await self._reply(context, error_msg("Pending actions not available."))
            return

        captured_config = auto_config

        async def _do_create(_action: Any, _ctx: "CommandContext") -> None:
            try:
                await self._ha.create_automation(captured_config.model_dump(exclude_none=True))
                await _ctx.update.message.reply_text(
                    success_msg(f"Automation '{captured_config.alias}' created\\!"),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                logger.info(
                    "automation_created",
                    alias=captured_config.alias,
                    user_id=_ctx.user_id,
                )
            except Exception as exc:
                await _ctx.update.message.reply_text(
                    error_msg(f"Create failed: {exc}"),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

        action_id = await pending.store(
            action=None,
            trace_id=str(uuid.uuid4())[:8],
            user_id=context.user_id,
            executor=_do_create,
            context=context,
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Create", callback_data=f"confirm:{action_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel:{action_id}"),
        ]])
        await context.update.message.reply_text(
            f"{bold('Automation preview')}\n```json\n{preview}\n```\n\n"
            f"_Confirm to create in Home Assistant_",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _find(self, autos: list[dict], query: str) -> dict | None:
        q = query.lower()
        # Exact id match first
        for a in autos:
            if a.get("id", "").lower() == q:
                return a
        # Alias contains match
        for a in autos:
            if q in a.get("alias", "").lower():
                return a
        return None

    @staticmethod
    def _to_entity_id(alias: str) -> str:
        """Derive entity_id from automation alias (best-effort)."""
        import re
        slug = re.sub(r"[^a-z0-9_]", "_", alias.lower())
        slug = re.sub(r"_+", "_", slug).strip("_")
        return f"automation.{slug}"

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
