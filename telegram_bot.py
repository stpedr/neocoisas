"""Bot do Telegram — opera toda a arquitetura do Auto Niche Engine.

Fala com a API (server.py) por HTTP, então roda como um serviço à parte e reusa
todo o backend: gerar ideias a partir de um prompt, revisar por botões inline
(✅ aprovar / ❌ rejeitar), renderizar e postar.

Comandos:
    /start, /ajuda           — ajuda
    /gerar <prompt>          — gera ideias (modo manual) e manda para revisão
    /auto <prompt>           — gera já aprovadas (prompta-e-posta)
    /pendentes               — lista ideias aguardando decisão
    /aprovadas               — lista aprovadas (renderizar / postar)

Configuração (via .env):
    TELEGRAM_BOT_TOKEN         — token do bot (obrigatório para rodar)
    ANE_API_URL                — base da API (padrão http://localhost:8000)
    TELEGRAM_ALLOWED_CHAT_IDS  — opcional: lista de chat ids autorizados (CSV)

As funções puras (parse_callback, format_idea, is_allowed) não dependem da lib
do Telegram e são cobertas por testes; os handlers importam a lib sob demanda.
"""

from __future__ import annotations

import os

import requests

API_URL = os.environ.get("ANE_API_URL", "http://localhost:8000").rstrip("/")
_TIMEOUT = 300


# --------------------------------------------------------------- helpers puros
def parse_callback(data: str) -> tuple[str, str]:
    """Divide o callback_data 'acao:id' em (acao, id)."""
    action, _, idea_id = data.partition(":")
    return action, idea_id


def is_allowed(chat_id, allowed_csv: str | None) -> bool:
    """Controle de acesso simples por lista de chat ids (CSV). Vazio = liberado."""
    if not allowed_csv:
        return True
    permitidos = {c.strip() for c in allowed_csv.split(",") if c.strip()}
    return str(chat_id) in permitidos


def select_new(current_ids: list[str], seen) -> list[str]:
    """Ids presentes agora que ainda não foram vistos (para notificar 1x)."""
    seen = seen or set()
    return [i for i in current_ids if i not in seen]


def format_idea(idea: dict) -> str:
    """Monta o texto de uma ideia para o chat (texto simples)."""
    cenas = idea.get("scenes", [])
    linhas = [f"💡 {idea.get('title', 'Ideia')}", f"{len(cenas)} cenas · {idea.get('mode', '')}"]
    if idea.get("video_path"):
        linhas.append("🎬 vídeo renderizado")
    linhas.append("")
    for i, s in enumerate(cenas, 1):
        narr = (s.get("narration") or "").strip()
        linhas.append(f"{i}. {narr}")
    return "\n".join(linhas).strip()


# ------------------------------------------------------------------ API client
def api_generate(prompt: str, mode: str, count: int = 5, num_scenes: int = 5) -> dict:
    r = requests.post(
        f"{API_URL}/api/generate",
        json={"prompt": prompt, "mode": mode, "count": count, "num_scenes": num_scenes},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def api_list(status: str) -> list[dict]:
    r = requests.get(f"{API_URL}/api/ideas", params={"status": status}, timeout=30)
    r.raise_for_status()
    return r.json().get("ideas", [])


def api_action(idea_id: str, action: str) -> dict:
    """action ∈ {approve, reject, render, post}."""
    r = requests.post(f"{API_URL}/api/ideas/{idea_id}/{action}", timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------------ main
def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN não definido. Configure-o no .env para rodar o bot."
        )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
    )

    allowed = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS")

    def review_keyboard(idea_id: str):
        return InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Aprovar", callback_data=f"approve:{idea_id}"),
                InlineKeyboardButton("❌ Rejeitar", callback_data=f"reject:{idea_id}"),
            ]]
        )

    def approved_keyboard(idea_id: str):
        return InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("🎬 Renderizar", callback_data=f"render:{idea_id}"),
                InlineKeyboardButton("🚀 Postar", callback_data=f"post:{idea_id}"),
            ]]
        )

    async def guard(update: Update) -> bool:
        chat_id = update.effective_chat.id if update.effective_chat else None
        if not is_allowed(chat_id, allowed):
            if update.effective_message:
                await update.effective_message.reply_text("Acesso não autorizado.")
            return False
        return True

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await guard(update):
            return
        await update.message.reply_text(
            "Auto Niche Engine 🤖\n\n"
            "/gerar <prompt> — gera ideias para revisar\n"
            "/auto <prompt> — gera já aprovadas\n"
            "/pendentes — revisar pendentes\n"
            "/aprovadas — renderizar/postar aprovadas"
        )

    async def _send_ideas(update, ideas, keyboard_fn):
        for idea in ideas:
            await update.effective_message.reply_text(
                format_idea(idea), reply_markup=keyboard_fn(idea["id"])
            )

    async def cmd_gerar(update: Update, ctx: ContextTypes.DEFAULT_TYPE, mode="manual"):
        if not await guard(update):
            return
        prompt = " ".join(ctx.args).strip()
        if not prompt:
            await update.message.reply_text("Uso: /gerar <seu prompt>")
            return
        await update.message.reply_text(f"Gerando ideias para: {prompt} …")
        try:
            res = api_generate(prompt, mode)
        except Exception as exc:  # noqa: BLE001
            await update.message.reply_text(f"Erro ao gerar: {exc}")
            return
        if mode == "auto":
            await update.message.reply_text(
                f"{res['generated']} ideias geradas e aprovadas. Use /aprovadas."
            )
        else:
            await _send_ideas(update, res.get("ideas", []), review_keyboard)

    async def cmd_auto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await cmd_gerar(update, ctx, mode="auto")

    async def cmd_pendentes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await guard(update):
            return
        ideas = api_list("pending")
        if not ideas:
            await update.message.reply_text("Nenhuma ideia pendente.")
            return
        await _send_ideas(update, ideas, review_keyboard)

    async def cmd_aprovadas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not await guard(update):
            return
        ideas = api_list("approved")
        if not ideas:
            await update.message.reply_text("Nenhuma ideia aprovada.")
            return
        await _send_ideas(update, ideas, approved_keyboard)

    async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not is_allowed(update.effective_chat.id, allowed):
            return
        action, idea_id = parse_callback(query.data)
        rotulos = {
            "approve": "✅ Aprovada",
            "reject": "❌ Rejeitada",
            "render": "🎬 Renderizada",
            "post": "🚀 Postada",
        }
        try:
            if action in ("render", "post"):
                await query.edit_message_text(f"{query.message.text}\n\n⏳ {action}…")
            api_action(idea_id, action)
            await query.edit_message_text(f"{query.message.text}\n\n{rotulos.get(action, action)}")
        except Exception as exc:  # noqa: BLE001
            await query.edit_message_text(f"{query.message.text}\n\n⚠️ Erro: {exc}")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "ajuda", "help"], cmd_start))
    app.add_handler(CommandHandler("gerar", cmd_gerar))
    app.add_handler(CommandHandler("auto", cmd_auto))
    app.add_handler(CommandHandler("pendentes", cmd_pendentes))
    app.add_handler(CommandHandler("aprovadas", cmd_aprovadas))
    app.add_handler(CallbackQueryHandler(on_callback))

    # Notificações proativas: avisa quando surgem novas ideias pendentes.
    notify_chat = os.environ.get("TELEGRAM_NOTIFY_CHAT_ID")
    interval = int(os.environ.get("TELEGRAM_NOTIFY_INTERVAL", "120"))
    if notify_chat and app.job_queue is not None:
        async def notify_job(ctx: ContextTypes.DEFAULT_TYPE):
            seen = ctx.bot_data.setdefault("seen_pending", set())
            try:
                ideas = api_list("pending")
            except Exception:  # noqa: BLE001 - API pode estar reiniciando
                return
            novas = select_new([i["id"] for i in ideas], seen)
            for idea in ideas:
                if idea["id"] in novas:
                    await ctx.bot.send_message(
                        chat_id=notify_chat,
                        text="🆕 Nova ideia para revisar:\n\n" + format_idea(idea),
                        reply_markup=review_keyboard(idea["id"]),
                    )
            seen.update(i["id"] for i in ideas)

        app.job_queue.run_repeating(notify_job, interval=interval, first=10)
        print(f"[telegram] notificações ativas (chat {notify_chat}, {interval}s)")

    print(f"[telegram] bot iniciado; API em {API_URL}")
    app.run_polling()


if __name__ == "__main__":
    main()
