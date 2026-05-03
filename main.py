"""
╔══════════════════════════════════════════════════════════════════╗
║         BOT TELEGRAM - ASSISTENTE DE FINANÇAS PESSOAIS          ║
║         Arquitetura: Flask + Webhook (compatível com Render)    ║
╚══════════════════════════════════════════════════════════════════╝

⚠️  DIFERENÇA CHAVE vs versão anterior:
    - ANTES: app.run_polling() → loop infinito, Render derruba o processo
    - AGORA: Flask + Webhook → servidor HTTP ativo, Telegram envia as
             mensagens para a URL, igual ao seu bot de dutching.

Variáveis de ambiente necessárias:
  TELEGRAM_TOKEN              → Token do BotFather
  OPENAI_API_KEY              → Chave da OpenAI
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

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
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
# BLOCO 1: LEITURA DA PLANILHA GOOGLE SHEETS
# ══════════════════════════════════════════════

def obter_credenciais_google() -> Credentials:
    """
    Cria as credenciais do Google a partir da variável de ambiente.

    Usa arquivo temporário para não depender de arquivos fixos em disco
    no servidor do Render (que tem filesystem efêmero).
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
        os.unlink(tmp_path)  # Apaga o arquivo temporário imediatamente

    return credenciais


def baixar_dados_planilha() -> pd.DataFrame:
    """
    Conecta ao Google Sheets e retorna os dados como DataFrame do Pandas.

    Colunas esperadas (nomes EXATOS):
      - Carimbo de data/hora
      - Qual a categoria do Gasto?
      - Quanto custou?
      - Quando foi?
      - Descrição do que foi
    """
    logger.info("Conectando ao Google Sheets...")

    credenciais = obter_credenciais_google()
    cliente = gspread.authorize(credenciais)

    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheet_id:
        raise ValueError("Variável GOOGLE_SHEETS_ID não encontrada.")

    planilha = cliente.open_by_key(sheet_id)
    aba = planilha.sheet1

    dados = aba.get_all_records()
    df = pd.DataFrame(dados)

    if df.empty:
        return df

    # Converte coluna de valor para numérico (remove R$, vírgulas etc.)
    if "Quanto custou?" in df.columns:
        df["Quanto custou?"] = (
            df["Quanto custou?"]
            .astype(str)
            .str.replace(r"[R$\s]", "", regex=True)
            .str.replace(",", ".", regex=False)
        )
        df["Quanto custou?"] = pd.to_numeric(df["Quanto custou?"], errors="coerce")

    # Converte coluna de data para datetime (permite filtros por período)
    if "Quando foi?" in df.columns:
        df["Quando foi?"] = pd.to_datetime(
            df["Quando foi?"], dayfirst=True, errors="coerce"
        )

    logger.info(f"Planilha carregada: {len(df)} registros encontrados.")
    return df


# ══════════════════════════════════════════════
# BLOCO 2: FERRAMENTA DO AGENTE (Tool)
# ══════════════════════════════════════════════

def consultar_planilha(pergunta: str) -> str:
    """
    Ferramenta principal do agente LangChain.

    Baixa os dados da planilha, monta um resumo estruturado
    (totais, categorias, meses, últimas transações) e retorna
    como texto para o agente formular a resposta final.
    """
    try:
        df = baixar_dados_planilha()

        if df.empty:
            return "A planilha está vazia ou não foi possível carregar os dados."

        total_geral = df["Quanto custou?"].sum() if "Quanto custou?" in df.columns else 0
        num_registros = len(df)

        # Agrupamento por categoria
        resumo_categorias = ""
        if "Qual a categoria do Gasto?" in df.columns:
            por_categoria = (
                df.groupby("Qual a categoria do Gasto?")["Quanto custou?"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "Total (R$)", "count": "Qtd"})
                .sort_values("Total (R$)", ascending=False)
            )
            resumo_categorias = por_categoria.to_string()

        # Agrupamento por mês
        resumo_mensal = ""
        if "Quando foi?" in df.columns and df["Quando foi?"].notna().any():
            df["Mês"] = df["Quando foi?"].dt.to_period("M").astype(str)
            por_mes = (
                df.groupby("Mês")["Quanto custou?"]
                .sum()
                .sort_index()
            )
            resumo_mensal = por_mes.to_string()

        # Últimas 10 transações para dar contexto ao agente
        cols_exibir = [c for c in [
            "Quando foi?", "Qual a categoria do Gasto?",
            "Quanto custou?", "Descrição do que foi"
        ] if c in df.columns]
        ultimas = df[cols_exibir].tail(10).to_string(index=False)

        contexto = f"""
DADOS DA PLANILHA DE GASTOS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total de registros: {num_registros}
Total geral gasto: R$ {total_geral:.2f}

GASTOS POR CATEGORIA:
{resumo_categorias if resumo_categorias else "Coluna de categoria não encontrada."}

GASTOS POR MÊS:
{resumo_mensal if resumo_mensal else "Coluna de data inválida ou não encontrada."}

ÚLTIMAS 10 TRANSAÇÕES:
{ultimas}

PERGUNTA DO USUÁRIO: {pergunta}
"""
        return contexto.strip()

    except Exception as e:
        logger.error(f"Erro ao consultar planilha: {e}")
        return f"Erro ao acessar a planilha: {str(e)}"


# ══════════════════════════════════════════════
# BLOCO 3: CONFIGURAÇÃO DO AGENTE LANGCHAIN
# ══════════════════════════════════════════════

def criar_agente() -> AgentExecutor:
    """
    Cria o ReAct Agent do LangChain com a ferramenta de planilha.

    ReAct = Reasoning + Acting:
      1. PENSA sobre a pergunta (Thought)
      2. DECIDE qual ferramenta usar (Action)
      3. OBSERVA o resultado (Observation)
      4. Repete até chegar na resposta final
    """
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
    )

    ferramentas = [
        Tool(
            name="consultar_planilha",
            func=consultar_planilha,
            description=(
                "Use esta ferramenta SEMPRE que o usuário perguntar sobre gastos, "
                "finanças, categorias, valores, datas ou qualquer informação financeira. "
                "Passe a pergunta do usuário como entrada. "
                "Ela retorna dados reais da planilha do Google Sheets."
            ),
        )
    ]

    prompt_template = PromptTemplate.from_template("""
Você é um assistente financeiro pessoal simpático e preciso chamado FinBot.
Você tem acesso à planilha de gastos do usuário via ferramentas.

SEMPRE que o usuário perguntar sobre gastos, valores, categorias ou datas,
use a ferramenta 'consultar_planilha' para obter os dados reais antes de responder.

Responda sempre em português brasileiro.
Seja direto, organize os números de forma clara e use emojis quando apropriado (💰📊📅).
Formate valores monetários como R$ X.XXX,XX.

Ferramentas disponíveis:
{tools}

Nomes das ferramentas: {tool_names}

Formato obrigatório de raciocínio:
Question: a pergunta do usuário
Thought: meu raciocínio sobre o que fazer
Action: nome_da_ferramenta
Action Input: entrada para a ferramenta
Observation: resultado da ferramenta
... (repita Thought/Action/Observation se necessário)
Thought: Agora tenho informação suficiente para responder
Final Answer: minha resposta final para o usuário

Comece!

Question: {input}
Thought: {agent_scratchpad}
""")

    agente = create_react_agent(llm=llm, tools=ferramentas, prompt=prompt_template)

    return AgentExecutor(
        agent=agente,
        tools=ferramentas,
        verbose=True,
        max_iterations=5,
        handle_parsing_errors=True,
    )


# ══════════════════════════════════════════════
# BLOCO 4: HANDLERS DO TELEGRAM
# ══════════════════════════════════════════════

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para /start — apresenta o bot ao usuário."""
    nome = update.effective_user.first_name
    mensagem = (
        f"Olá, {nome}! 👋 Sou seu assistente financeiro pessoal.\n\n"
        "💬 *Como usar:*\n"
        "Basta me perguntar em linguagem natural sobre seus gastos!\n\n"
        "📌 *Exemplos:*\n"
        "• _Quanto gastei este mês?_\n"
        "• _Qual categoria tem mais gastos?_\n"
        "• _Mostre meus gastos com alimentação_\n"
        "• _Qual foi meu maior gasto em março?_\n\n"
        "Seus dados vêm direto da sua planilha Google Sheets. 📊"
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown")


async def comando_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler para /ajuda — exibe exemplos de perguntas."""
    mensagem = (
        "🤖 *Como funciono:*\n"
        "Acesso sua planilha de gastos em tempo real e uso IA para responder suas perguntas.\n\n"
        "💡 *Perguntas que você pode fazer:*\n"
        "• Total gasto por categoria\n"
        "• Comparação entre meses\n"
        "• Gastos em um período específico\n"
        "• Qual foi o gasto mais alto\n"
        "• Resumo financeiro do mês\n\n"
        "⚡ _Dica: Seja específico! Ex: 'quanto gastei com transporte em abril'_"
    )
    await update.message.reply_text(mensagem, parse_mode="Markdown")


async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler principal para mensagens de texto.

    Recebe a pergunta, passa para o agente LangChain (que consulta
    a planilha se necessário) e devolve a resposta ao usuário.
    """
    pergunta = update.message.text
    logger.info(f"Mensagem: {pergunta[:60]}...")

    # Mostra "digitando..." enquanto a IA processa
    await update.message.chat.send_action("typing")

    try:
        resultado = agente_executor.invoke({"input": pergunta})
        resposta = resultado.get("output", "Não consegui processar sua pergunta.")
    except Exception as e:
        logger.error(f"Erro no agente: {e}")
        resposta = (
            "⚠️ Ocorreu um erro ao processar sua pergunta.\n"
            f"_Detalhe: {str(e)[:120]}_"
        )

    await update.message.reply_text(resposta, parse_mode="Markdown")


# ══════════════════════════════════════════════
# BLOCO 5: FLASK + WEBHOOK (compatível Render)
# ══════════════════════════════════════════════
#
# POR QUE ISSO FUNCIONA NO RENDER:
#   O Render exige que a aplicação suba um servidor HTTP na porta
#   fornecida pela variável PORT. Com run_polling() isso não acontecia.
#   Aqui o Flask sobe o servidor, e o Telegram chama nosso /webhook
#   a cada mensagem recebida — o mesmo padrão do seu bot de dutching.
# ──────────────────────────────────────────────

TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Servidor HTTP Flask
flask_app = Flask(__name__)

# App do Telegram (sem iniciar polling)
telegram_app = ApplicationBuilder().token(TOKEN).build()

# Registra os handlers de comandos e mensagens
telegram_app.add_handler(CommandHandler("start", comando_start))
telegram_app.add_handler(CommandHandler("ajuda", comando_ajuda))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagem))

# ── Inicializa o bot UMA única vez com asyncio ──────────────────
# Mesmo padrão exato do seu bot de dutching que já funciona no Render
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(telegram_app.initialize())
loop.run_until_complete(telegram_app.start())

# Inicializa o agente LangChain uma única vez na subida do servidor
logger.info("Inicializando agente LangChain...")
agente_executor = criar_agente()
logger.info("Agente criado com sucesso!")


@flask_app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    """
    Endpoint que recebe as atualizações do Telegram.

    O Telegram chama esta URL via HTTPS cada vez que alguém manda
    uma mensagem para o bot. O TOKEN na URL serve como segurança
    básica: só quem conhece a URL consegue chamar o endpoint.
    """
    try:
        data = request.get_json()
        update = Update.de_json(data, telegram_app.bot)

        # Processa o update no loop asyncio já existente
        loop.run_until_complete(telegram_app.process_update(update))

        return "ok", 200

    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        return "error", 500


@flask_app.route("/")
def home():
    """Rota raiz — confirma que o servidor está no ar."""
    return "✅ FinBot rodando!", 200


@flask_app.route("/set_webhook")
def set_webhook():
    """
    Rota auxiliar para registrar o webhook no Telegram.

    ▶️  Acesse esta URL UMA VEZ pelo navegador após o deploy:
        https://SEU-APP.onrender.com/set_webhook

    Isso diz ao Telegram para qual URL ele deve enviar as mensagens.
    Só é necessário fazer isso uma vez (ou se mudar a URL do Render).
    """
    webhook_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    url_completa = f"{webhook_url}/webhook/{TOKEN}"

    result = loop.run_until_complete(
        telegram_app.bot.set_webhook(url=url_completa)
    )

    if result:
        return f"✅ Webhook registrado!\nURL: {url_completa}", 200
    else:
        return "❌ Falha ao registrar webhook. Verifique WEBHOOK_URL.", 500


# ══════════════════════════════════════════════
# BLOCO 6: PONTO DE ENTRADA
# ══════════════════════════════════════════════

if __name__ == "__main__":
    """
    Inicia o servidor Flask.

    O Render injeta a porta automaticamente via variável PORT.
    host="0.0.0.0" é obrigatório para o Render conseguir acessar.
    """
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
