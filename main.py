"""
╔══════════════════════════════════════════════════════════════════╗
║         BOT TELEGRAM - ASSISTENTE DE FINANÇAS PESSOAIS          ║
║         Arquitetura: Flask + Webhook + Comandos diretos         ║
╚══════════════════════════════════════════════════════════════════╝

SEM dependência de LLM (OpenAI, etc.) — zero custo de API.
Os dados vêm direto do Google Sheets via gspread + pandas.

Comandos disponíveis:
  /total (mes)                    → todos os gastos do mês + soma final
  /categoria (categoria) (mes)    → gastos de uma categoria no mês + soma

Exemplos:
  /total maio
  /total 05
  /categoria alimentacao abril
  /categoria transporte 03

Variáveis de ambiente necessárias:
  TELEGRAM_TOKEN              → Token do BotFather
  GOOGLE_SHEETS_ID            → ID da planilha (na URL)
  GOOGLE_SERVICE_ACCOUNT_JSON → Conteúdo JSON das credenciais do Google Cloud
  WEBHOOK_URL                 → URL pública do Render (ex: https://meubot.onrender.com)
"""

import os
import asyncio
import logging
import tempfile

import pandas as pd
import gspread
from flask import Flask, request
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ──────────────────────────────────────────────
# CONFIGURAÇÃO DE LOGS
# ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# BLOCO 1: MAPEAMENTO DE MESES
# ══════════════════════════════════════════════

# Aceita tanto nome ("janeiro", "jan") quanto número ("01", "1")
MESES_NOMES = {
    "janeiro": 1,  "jan": 1,
    "fevereiro": 2, "fev": 2,
    "março": 3,    "mar": 3,  "marco": 3,
    "abril": 4,    "abr": 4,
    "maio": 5,     "mai": 5,
    "junho": 6,    "jun": 6,
    "julho": 7,    "jul": 7,
    "agosto": 8,   "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11,"nov": 11,
    "dezembro": 12,"dez": 12,
}

MESES_EXTENSO = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março",
    4: "Abril",   5: "Maio",      6: "Junho",
    7: "Julho",   8: "Agosto",    9: "Setembro",
    10: "Outubro",11: "Novembro", 12: "Dezembro",
}

def resolver_mes(texto: str) -> int | None:
    """
    Converte uma string de mês para número inteiro (1–12).

    Aceita:
      - Nome completo: "janeiro", "fevereiro" ...
      - Abreviação: "jan", "fev" ...
      - Número: "1", "01", "12" ...

    Retorna None se não conseguir identificar o mês.
    """
    texto = texto.strip().lower()

    # Tenta pelo nome/abreviação
    if texto in MESES_NOMES:
        return MESES_NOMES[texto]

    # Tenta como número
    try:
        num = int(texto)
        if 1 <= num <= 12:
            return num
    except ValueError:
        pass

    return None


# ══════════════════════════════════════════════
# BLOCO 2: LEITURA DA PLANILHA GOOGLE SHEETS
# ══════════════════════════════════════════════

def obter_credenciais_google() -> Credentials:
    """
    Cria as credenciais do Google a partir da variável de ambiente.
    Usa arquivo temporário para não depender de arquivos fixos em disco.
    """
    json_content = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_content:
        raise ValueError("Variável GOOGLE_SERVICE_ACCOUNT_JSON não encontrada.")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(json_content)
        tmp_path = tmp.name

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        credenciais = Credentials.from_service_account_file(tmp_path, scopes=scopes)
    finally:
        os.unlink(tmp_path)

    return credenciais


def carregar_planilha() -> pd.DataFrame:
    """
    Conecta ao Google Sheets e retorna os dados como DataFrame.

    Colunas esperadas (nomes EXATOS):
      - Carimbo de data/hora
      - Qual a categoria do Gasto?
      - Quanto custou?
      - Quando foi?
      - Descrição do que foi

    Já aplica limpeza e tipagem nos dados retornados.
    """
    credenciais = obter_credenciais_google()
    cliente = gspread.authorize(credenciais)

    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    planilha = cliente.open_by_key(sheet_id)
    aba = planilha.sheet1

    df = pd.DataFrame(aba.get_all_records())

    if df.empty:
        return df

    # Limpa e converte coluna de valor para float
    if "Quanto custou?" in df.columns:
        df["Quanto custou?"] = (
            df["Quanto custou?"]
            .astype(str)
            .str.replace(r"[R$\s]", "", regex=True)
            .str.replace(",", ".", regex=False)
        )
        df["Quanto custou?"] = pd.to_numeric(df["Quanto custou?"], errors="coerce")

    # Converte coluna de data para datetime
    if "Quando foi?" in df.columns:
        df["Quando foi?"] = pd.to_datetime(
            df["Quando foi?"], dayfirst=True, errors="coerce"
        )

    logger.info(f"Planilha carregada: {len(df)} registros.")
    return df


def filtrar_por_mes(df: pd.DataFrame, numero_mes: int) -> pd.DataFrame:
    """
    Filtra o DataFrame mantendo apenas os registros do mês informado.
    O ano não é filtrado — considera todos os anos com aquele mês.
    """
    if "Quando foi?" not in df.columns:
        return pd.DataFrame()

    return df[df["Quando foi?"].dt.month == numero_mes].copy()


# ══════════════════════════════════════════════
# BLOCO 3: FORMATAÇÃO DAS RESPOSTAS
# ══════════════════════════════════════════════

def formatar_valor(valor: float) -> str:
    """Formata um float como moeda brasileira: R$ 1.234,56"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_lista_gastos(df: pd.DataFrame) -> str:
    """
    Monta a lista de gastos linha a linha no formato:
      📅 DD/MM  |  🏷 Categoria  |  📝 Descrição  |  💸 R$ X,XX

    Retorna a lista formatada + linha de total no final.
    """
    if df.empty:
        return ""

    linhas = []
    for _, row in df.iterrows():
        # Data
        data = row.get("Quando foi?")
        data_str = data.strftime("%d/%m") if pd.notna(data) else "??/??"

        # Categoria
        categoria = str(row.get("Qual a categoria do Gasto?", "—")).strip()

        # Descrição
        descricao = str(row.get("Descrição do que foi", "—")).strip()
        if not descricao or descricao == "nan":
            descricao = "—"

        # Valor
        valor = row.get("Quanto custou?", 0)
        valor_str = formatar_valor(valor) if pd.notna(valor) else "—"

        linhas.append(
            f"📅 {data_str}  |  🏷 {categoria}\n"
            f"   📝 {descricao}\n"
            f"   💸 {valor_str}"
        )

    total = df["Quanto custou?"].sum()
    linhas.append(f"\n{'─' * 30}\n💰 *Total: {formatar_valor(total)}*")

    return "\n\n".join(linhas)


# ══════════════════════════════════════════════
# BLOCO 4: HANDLERS DOS COMANDOS
# ══════════════════════════════════════════════

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para /start — apresenta os comandos disponíveis."""
    nome = update.effective_user.first_name
    mensagem = (
        f"Olá, {nome}! 👋 Sou seu assistente de finanças pessoais.\n\n"
        "📋 *Comandos disponíveis:*\n\n"
        "*/total (mês)*\n"
        "Retorna todos os gastos do mês com detalhes e soma final.\n"
        "_Exemplos: /total maio · /total 05_\n\n"
        "*/categoria (categoria) (mês)*\n"
        "Retorna os gastos de uma categoria específica no mês.\n"
        "_Exemplos: /categoria alimentacao abril · /categoria transporte 04_\n\n"
        "*/categorias (mês)*\n"
        "Lista todas as categorias do mês com seus totais.\n"
        "_Exemplo: /categorias maio_"
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown")


async def comando_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler para /total (mes).

    Uso: /total maio  ou  /total 05

    Retorna todos os gastos do mês informado, um por linha,
    com data, categoria, descrição e valor — seguido da soma total.
    """
    # ── Valida o argumento de mês ────────────────────────────────
    if not context.args:
        await update.message.reply_text(
            "⚠️ Informe o mês.\n_Exemplo: /total maio  ou  /total 05_",
            parse_mode="Markdown"
        )
        return

    numero_mes = resolver_mes(context.args[0])
    if numero_mes is None:
        await update.message.reply_text(
            "❌ Mês não reconhecido. Use o nome (maio) ou número (05)."
        )
        return

    nome_mes = MESES_EXTENSO[numero_mes]
    await update.message.chat.send_action("typing")

    try:
        df = carregar_planilha()

        if df.empty:
            await update.message.reply_text("⚠️ A planilha está vazia.")
            return

        df_mes = filtrar_por_mes(df, numero_mes)

        if df_mes.empty:
            await update.message.reply_text(
                f"📭 Nenhum gasto encontrado em *{nome_mes}*.",
                parse_mode="Markdown"
            )
            return

        # Ordena por data para exibição cronológica
        df_mes = df_mes.sort_values("Quando foi?")

        cabecalho = f"📊 *Gastos de {nome_mes}* ({len(df_mes)} registros)\n{'─' * 30}\n\n"
        lista = montar_lista_gastos(df_mes)
        resposta = cabecalho + lista

        # Telegram tem limite de 4096 caracteres por mensagem
        # Se passar, divide em partes
        if len(resposta) <= 4096:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        else:
            # Envia o cabeçalho + lista sem o total primeiro
            partes = [resposta[i:i+4000] for i in range(0, len(resposta), 4000)]
            for parte in partes:
                await update.message.reply_text(parte, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro no /total: {e}")
        await update.message.reply_text(
            f"❌ Erro ao consultar a planilha.\n_Detalhe: {str(e)[:100]}_",
            parse_mode="Markdown"
        )


async def comando_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler para /categoria (categoria) (mes).

    Uso: /categoria alimentacao maio  ou  /categoria transporte 04

    A busca por categoria é parcial e sem acento — "alimenta" encontra
    "Alimentação", "trans" encontra "Transporte", etc.
    """
    # ── Valida os argumentos ─────────────────────────────────────
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Uso correto: /categoria (categoria) (mês)\n"
            "_Exemplo: /categoria alimentacao maio_",
            parse_mode="Markdown"
        )
        return

    # Último argumento é o mês, tudo antes é a categoria
    # (permite categorias com espaço: /categoria vale refeicao maio)
    texto_mes = context.args[-1]
    texto_categoria = " ".join(context.args[:-1])

    numero_mes = resolver_mes(texto_mes)
    if numero_mes is None:
        await update.message.reply_text(
            "❌ Mês não reconhecido. Use o nome (maio) ou número (05)."
        )
        return

    nome_mes = MESES_EXTENSO[numero_mes]
    await update.message.chat.send_action("typing")

    try:
        df = carregar_planilha()

        if df.empty:
            await update.message.reply_text("⚠️ A planilha está vazia.")
            return

        df_mes = filtrar_por_mes(df, numero_mes)

        if df_mes.empty:
            await update.message.reply_text(
                f"📭 Nenhum gasto encontrado em *{nome_mes}*.",
                parse_mode="Markdown"
            )
            return

        # ── Busca parcial sem acento na categoria ────────────────
        # Normaliza texto para comparação (remove acentos e caixa)
        import unicodedata

        def normalizar(texto: str) -> str:
            return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()

        busca = normalizar(texto_categoria)
        col_cat = "Qual a categoria do Gasto?"

        mascara = df_mes[col_cat].astype(str).apply(normalizar).str.contains(busca, na=False)
        df_filtrado = df_mes[mascara].sort_values("Quando foi?")

        if df_filtrado.empty:
            # Mostra as categorias disponíveis para ajudar o usuário
            categorias_disponiveis = sorted(df_mes[col_cat].dropna().unique())
            cats_str = "\n".join(f"  • {c}" for c in categorias_disponiveis)
            await update.message.reply_text(
                f"📭 Nenhum gasto com categoria *{texto_categoria}* em *{nome_mes}*.\n\n"
                f"Categorias disponíveis neste mês:\n{cats_str}",
                parse_mode="Markdown"
            )
            return

        # Pega o nome real da categoria (como está na planilha)
        nome_categoria_real = df_filtrado[col_cat].iloc[0]

        cabecalho = (
            f"🏷 *{nome_categoria_real}* — {nome_mes}\n"
            f"({len(df_filtrado)} registros)\n"
            f"{'─' * 30}\n\n"
        )
        lista = montar_lista_gastos(df_filtrado)
        resposta = cabecalho + lista

        if len(resposta) <= 4096:
            await update.message.reply_text(resposta, parse_mode="Markdown")
        else:
            partes = [resposta[i:i+4000] for i in range(0, len(resposta), 4000)]
            for parte in partes:
                await update.message.reply_text(parte, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro no /categoria: {e}")
        await update.message.reply_text(
            f"❌ Erro ao consultar a planilha.\n_Detalhe: {str(e)[:100]}_",
            parse_mode="Markdown"
        )


async def comando_categorias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler para /categorias (mes).

    Bônus útil: lista todas as categorias do mês com o total de cada uma,
    para o usuário saber quais nomes usar no /categoria.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Informe o mês.\n_Exemplo: /categorias maio_",
            parse_mode="Markdown"
        )
        return

    numero_mes = resolver_mes(context.args[0])
    if numero_mes is None:
        await update.message.reply_text(
            "❌ Mês não reconhecido. Use o nome (maio) ou número (05)."
        )
        return

    nome_mes = MESES_EXTENSO[numero_mes]
    await update.message.chat.send_action("typing")

    try:
        df = carregar_planilha()
        df_mes = filtrar_por_mes(df, numero_mes)

        if df_mes.empty:
            await update.message.reply_text(
                f"📭 Nenhum gasto encontrado em *{nome_mes}*.",
                parse_mode="Markdown"
            )
            return

        col_cat = "Qual a categoria do Gasto?"
        resumo = (
            df_mes.groupby(col_cat)["Quanto custou?"]
            .agg(["sum", "count"])
            .sort_values("sum", ascending=False)
        )

        total_geral = df_mes["Quanto custou?"].sum()
        linhas = [f"📊 *Categorias de {nome_mes}*\n{'─' * 30}\n"]

        for categoria, row in resumo.iterrows():
            linhas.append(
                f"🏷 *{categoria}*\n"
                f"   {int(row['count'])} gasto(s) · {formatar_valor(row['sum'])}"
            )

        linhas.append(f"\n{'─' * 30}\n💰 *Total geral: {formatar_valor(total_geral)}*")
        resposta = "\n\n".join(linhas)

        await update.message.reply_text(resposta, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erro no /categorias: {e}")
        await update.message.reply_text(
            f"❌ Erro ao consultar a planilha.\n_Detalhe: {str(e)[:100]}_",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════
# BLOCO 5: FLASK + WEBHOOK (compatível Render)
# ══════════════════════════════════════════════

TOKEN = os.environ.get("TELEGRAM_TOKEN")

flask_app = Flask(__name__)
telegram_app = ApplicationBuilder().token(TOKEN).build()

# Registra todos os comandos
telegram_app.add_handler(CommandHandler("start",      comando_start))
telegram_app.add_handler(CommandHandler("total",      comando_total))
telegram_app.add_handler(CommandHandler("categoria",  comando_categoria))
telegram_app.add_handler(CommandHandler("categorias", comando_categorias))

# Inicializa o bot com asyncio (mesmo padrão do bot de dutching)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(telegram_app.initialize())
loop.run_until_complete(telegram_app.start())


@flask_app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    """Recebe as atualizações do Telegram e processa de forma assíncrona."""
    try:
        data = request.get_json()
        update = Update.de_json(data, telegram_app.bot)
        loop.run_until_complete(telegram_app.process_update(update))
        return "ok", 200
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return "error", 500


@flask_app.route("/")
def home():
    return "✅ FinBot rodando!", 200


@flask_app.route("/set_webhook")
def set_webhook():
    """
    Acesse esta URL UMA VEZ após o deploy para registrar o webhook:
    https://SEU-APP.onrender.com/set_webhook
    """
    webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    url_completa = f"{webhook_url}/webhook/{TOKEN}"
    result = loop.run_until_complete(telegram_app.bot.set_webhook(url=url_completa))
    if result:
        return f"✅ Webhook registrado!\nURL: {url_completa}", 200
    return "❌ Falha. Verifique WEBHOOK_URL.", 500


# ══════════════════════════════════════════════
# BLOCO 6: PONTO DE ENTRADA
# ══════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
