"""
Scene CRUD — Phase 4.

/scenes               — list all scenes
/scene <query> activate — activate a scene
/scene <query> delete   — delete (requires confirm)
/scene create <description> — Claude YAML → preview → confirm → create
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


class ScenesModule(ModuleBase):
    name = "scenes"
    description = "Scene CRUD"
    commands: list[str] = ["scenes", "scene"]

    async def setup(self, app: "AppContext") -> None:
        self._app = app
        self._ha = app.ha_client
        self._generator: YAMLGenerator | None = None

    async def teardown(self) -> None:
        pass

    async def handle_command(
        self, cmd: str, args: list[str], context: "CommandContext"
    ) -> None:
        if cmd == "scenes" or not args:
            await self._cmd_list(context)
            return

        # /scene <query> <action> or /scene create <description>
        sub = args[0].lower()
        if sub == "create":
            description = " ".join(args[1:])
            await self._cmd_create(description, context)
        elif len(args) >= 2:
            query = args[0]
            action = args[1].lower()
            await self._cmd_action(query, action, args[2:], context)
        else:
            await self._reply(
                context,
                "Usage:\n"
                "`/scene \\<query\\> activate\\|delete`\n"
                "`/scene create \\<description\\>`",
            )

    # ------------------------------------------------------------------ #

    async def _cmd_list(self, context: "CommandContext") -> None:
        try:
            scenes = await self._ha.get_scenes()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot list scenes: {exc}"))
            return

        if not scenes:
            await self._reply(context, "No scenes found\\.")
            return

        lines = [bold("Scenes"), ""]
        for s in scenes[:30]:
            name = s.get("name", s.get("id", "?"))
            sid = s.get("id", "?")
            lines.append(f"• {escape_md(name)}\n  {code(sid)}")

        if len(scenes) > 30:
            lines.append(f"\n_… and {len(scenes) - 30} more_")
        lines.append(f"\n_{len(scenes)} total_")

        await context.update.message.reply_text(
            "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
        )

    async def _cmd_action(
        self, query: str, action: str, extra_args: list[str], context: "CommandContext"
    ) -> None:
        try:
            scenes = await self._ha.get_scenes()
        except Exception as exc:
            await self._reply(context, error_msg(f"Cannot get scenes: {exc}"))
            return

        scene = self._find(scenes, query)
        if not scene:
            await self._reply(context, escape_md(f"No scene matching '{query}'."))
            return

        name = scene.get("name", scene.get("id", "?"))
        scene_id = scene.get("id", "")
        # Scene entity_id is scene.<id>
        entity_id = f"scene.{scene_id}"

        if action == "activate":
            try:
                await self._ha.call_service("scene", "turn_on", {"entity_id": entity_id})
                await self._reply(context, success_msg(f"Scene '{name}' activated."))
            except Exception as exc:
                await self._reply(context, error_msg(f"Activation failed: {exc}"))

        elif action == "delete":
            confirmed = extra_args and extra_args[0] == "confirm"
            if not confirmed:
                pending = self._app.extra.get("pending_actions")
                if pending:
                    captured_id = scene_id
                    captured_name = name

                    async def _do_delete(_action: Any, _ctx: "CommandContext") -> None:
                        await self._ha.delete_scene(captured_id)
                        await _ctx.update.message.reply_text(
                            success_msg(f"Scene '{captured_name}' deleted."),
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
                        f"⚠️ Delete scene {bold(escape_md(name))}?",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=keyboard,
                    )
                else:
                    await self._reply(
                        context,
                        f"⚠️ Delete {code(escape_md(name))}\\?\n"
                        f"Send `/scene {escape_md(query)} delete confirm` to proceed\\.",
                    )
            else:
                try:
                    await self._ha.delete_scene(scene_id)
                    await self._reply(context, success_msg(f"Scene '{name}' deleted."))
                except Exception as exc:
                    await self._reply(context, error_msg(f"Delete failed: {exc}"))
        else:
            await self._reply(
                context,
                f"Unknown action {code(action)}\\. Use: activate, delete",
            )

    async def _cmd_create(self, description: str, context: "CommandContext") -> None:
        if not description.strip():
            await self._reply(context, "Usage: /scene create \\<description\\>")
            return

        if not self._app.config.ai_enabled:
            await self._reply(context, "AI is disabled\\. Enable `ai_enabled` to create scenes\\.")
            return

        await self._reply(context, "🤖 Generating scene YAML…")

        if not self._generator:
            from app.ai.yaml_generator import YAMLGenerator
            self._generator = YAMLGenerator(
                config=self._app.config,
                discovery=self._app.extra.get("discovery"),
            )

        try:
            scene_config = await self._generator.generate_scene(description)
        except Exception as exc:
            await self._reply(context, error_msg(f"YAML generation failed: {exc}"))
            return

        import json
        preview = json.dumps(scene_config.model_dump(exclude_none=True), indent=2)
        if len(preview) > 2500:
            preview = preview[:2500] + "\n…"

        pending = self._app.extra.get("pending_actions")
        if not pending:
            await self._reply(context, error_msg("Pending actions not available."))
            return

        captured_config = scene_config

        async def _do_create(_action: Any, _ctx: "CommandContext") -> None:
            try:
                await self._ha.create_scene(captured_config.model_dump(exclude_none=True))
                await _ctx.update.message.reply_text(
                    success_msg(f"Scene '{captured_config.name}' created\\!"),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                logger.info("scene_created", name=captured_config.name, user_id=_ctx.user_id)
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
            f"{bold('Scene preview')}\n```json\n{preview}\n```\n\n"
            f"_Confirm to create in Home Assistant_",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard,
        )

    # ------------------------------------------------------------------ #

    def _find(self, scenes: list[dict], query: str) -> dict | None:
        q = query.lower()
        for s in scenes:
            if s.get("id", "").lower() == q:
                return s
        for s in scenes:
            if q in s.get("name", "").lower():
                return s
        return None

    async def _reply(self, context: "CommandContext", text: str) -> None:
        await context.update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
