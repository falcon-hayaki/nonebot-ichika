"""
帮助插件
触发: /help [插件名]
列出所有已加载插件及其用法
"""
from nonebot.plugin import PluginMetadata, get_loaded_plugins
from nonebot import on_command
from nonebot.rule import to_me
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg

__plugin_meta__ = PluginMetadata(
    name="帮助",
    description="查看所有可用指令",
    usage="@一花 help          —— 列出所有插件\n@一花 help <插件名>  —— 查看指定插件的详细用法",
)

help_matcher = on_command("help", aliases={"帮助", "菜单"}, rule=to_me(), priority=1, block=True)

# 不希望出现在 /help 列表中的第三方插件模块名（精确匹配）
_HIDDEN_MODULES: frozenset[str] = frozenset({
    "nonebot_plugin_status",
    "nonebot_plugin_apscheduler",
})


def _get_plugin_metas() -> list[PluginMetadata]:
    """收集所有已加载插件中声明了 PluginMetadata 的条目，按插件名排序。
    过滤规则（满足任意一条即隐藏）：
      1. plugin.module_name 在 _HIDDEN_MODULES 中（屏蔽第三方插件）
      2. meta.extra 中设置了 hidden=True（自有插件手动隐藏）
    """
    metas: list[PluginMetadata] = []
    seen_names: set[str] = set()
    for plugin in get_loaded_plugins():
        if plugin.module_name in _HIDDEN_MODULES:
            continue
        meta = plugin.metadata
        if meta is None:
            continue
        if meta.extra.get("hidden"):
            continue
        if meta.name in seen_names:
            continue
        seen_names.add(meta.name)
        metas.append(meta)
    metas.sort(key=lambda m: m.name)
    return metas


@help_matcher.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()) -> None:
    query = args.extract_plain_text().strip()

    metas = _get_plugin_metas()

    # ── 查询单个插件详情 ──────────────────────────────────────────
    if query:
        matched = next(
            (m for m in metas if m.name.lower() == query.lower()),
            None,
        )
        if matched is None:
            await help_matcher.finish(
                f"找不到插件「{query}」\n"
                "发送 /help 查看所有可用插件"
            )
            return

        lines = [
            f"{matched.name}",
            f"{matched.description}",
            "",
            "用法：",
            matched.usage or "（暂无说明）",
        ]
        await help_matcher.finish("\n".join(lines))
        return

    # ── 列出全部插件 ──────────────────────────────────────────────
    if not metas:
        await help_matcher.finish("暂时没有已加载的插件喵 ><")
        return

    lines = ["✨ 一花 · 可用功能列表", ""]
    for i, meta in enumerate(metas, 1):
        lines.append(f"{i}. 【{meta.name}】{meta.description}")

    lines += [
        "",
        "发送 /help <功能名> 查看详细用法",
        "   例：/help 帮我选",
    ]

    await help_matcher.finish("\n".join(lines))
