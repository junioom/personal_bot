"""
╔══════════════════════════════════════════════════════════════════╗
║         BOT TELEGRAM - ASSISTENTE DE FINANÇAS PESSOAIS          ║
║         Powered by LangChain ReAct Agent + Google Sheets        ║
╚══════════════════════════════════════════════════════════════════╝

Arquitetura:
  - python-telegram-bot (v20+): Interface com o Telegram
  - LangChain ReAct Agent: Lógica de raciocínio da IA
  - gspread + pandas: Leitura e filtragem da planilha
  - OpenAI GPT: LLM base do agente

Variáveis de ambiente necessárias:
  TELEGRAM_TOKEN              → Token do BotFather
  OPENAI_API_KEY              → Chave da OpenAI
  GOOGLE_SHEETS_ID            → ID da planilha (na URL)
  GOOGLE_SERVICE_ACCOUNT_JSON → Conteúdo JSON das credenciais do Google Cloud
"""

import os
import json
import logging
import tempfile
from datetime import datetime

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from telegram import Update
from telegram.ext import (
    Application,
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

    A variável GOOGLE_SERVICE_ACCOUNT_JSON deve conter o conteúdo
    COMPLETO do arquivo .json gerado no Google Cloud Console.
    Para evitar problemas com arquivos em disco no servidor,
    usamos um arquivo temporário que é apagado após o uso.

    Returns:
        Credentials: Objeto de credenciais autenticado para a API do Google.
    """
    json_content = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not json_content:
        raise ValueError("Variável GOOGLE_SERVICE_ACCOUNT_JSON não encontrada.")

    # Escreve o JSON em arquivo temporário (necessário para a lib do Google)
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

    Colunas esperadas na planilha (nomes EXATOS):
      - Carimbo de data/hora
      - Qual a categoria do Gasto?
      - Quanto custou?
      - Quando foi?
      - Descrição do que foi

    Returns:
        pd.DataFrame: Dados completos da planilha com tipos corrigidos.

    Raises:
        Exception: Se a planilha não for encontrada ou as credenciais forem inválidas.
    """
    logger.info("Conectando ao Google Sheets...")

    credenciais = obter_credenciais_google()
    cliente = gspread.authorize(credenciais)

    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not sheet_id:
        raise ValueError("Variável GOOGLE_SHEETS_ID não encontrada.")

    planilha = cliente.open_by_key(sheet_id)
    aba = planilha.sheet1  # Pega a primeira aba

    dados = aba.get_all_records()
    df = pd.DataFrame(dados)

    if df.empty:
        return df

    # ── Limpeza e tipagem dos dados ──────────────────────────────
    # Converte a coluna de valor para numérico (remove R$, vírgulas, etc.)
    if "Quanto custou?" in df.columns:
        df["Quanto custou?"] = (
            df["Quanto custou?"]
            .astype(str)
            .str.replace(r"[R$\s]", "", regex=True)
            .str.replace(",", ".", regex=False)
        )
        df["Quanto custou?"] = pd.to_numeric(df["Quanto custou?"], errors="coerce")

    # Tenta converter "Quando foi?" para datetime para filtros por data
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
    Ferramenta principal do agente. Recebe uma pergunta em linguagem natural,
    carrega os dados da planilha e retorna um resumo estruturado para que
    a IA possa formular a resposta final.

    O agente LangChain chamará esta função automaticamente quando decidir
    que precisa consultar os dados financeiros.

    Args:
        pergunta (str): Pergunta ou instrução do usuário (ex: "total gasto em alimentação").

    Returns:
        str: Resumo dos dados da planilha em formato texto para o agente processar.
    """
    try:
        df = baixar_dados_planilha()

        if df.empty:
            return "A planilha está vazia ou não foi possível carregar os dados."

        # ── Resumo geral para contexto ─────────────────────────────
        total_geral = df["Quanto custou?"].sum() if "Quanto custou?" in df.columns else 0
        num_registros = len(df)

        # ── Gastos por categoria ────────────────────────────────────
        resumo_categorias = ""
        if "Qual a categoria do Gasto?" in df.columns:
            por_categoria = (
                df.groupby("Qual a categoria do Gasto?")["Quanto custou?"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "Total (R$)", "count": "Qtd"})
                .sort_values("Total (R$)", ascending=False)
            )
            resumo_categorias = por_categoria.to_string()

        # ── Gastos por mês (se a coluna de data for válida) ─────────
        resumo_mensal = ""
        if "Quando foi?" in df.columns and df["Quando foi?"].notna().any():
            df["Mês"] = df["Quando foi?"].dt.to_period("M").astype(str)
            por_mes = (
                df.groupby("Mês")["Quanto custou?"]
                .sum()
                .sort_index()
            )
            resumo_mensal = por_mes.to_string()

        # ── Últimas 10 transações ────────────────────────────────────
        cols_exibir = [c for c in [
            "Quando foi?", "Qual a categoria do Gasto?",
            "Quanto custou?", "Descrição do que foi"
        ] if c in df.columns]

        ultimas = df[cols_exibir].tail(10).to_string(index=False)

        # ── Monta o contexto completo para o agente ─────────────────
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
    Cria e configura o ReAct Agent do LangChain.

    O ReAct (Reasoning + Acting) é um padrão onde a IA:
      1. PENSA sobre a pergunta (Thought)
      2. DECIDE qual ferramenta usar (Action)
      3. OBSERVA o resultado (Observation)
      4. Repete até ter a resposta final (Final Answer)

    Returns:
        AgentExecutor: Agente pronto para receber perguntas.
    """

    # ── LLM: Modelo de linguagem ────────────────────────────────
    llm = ChatOpenAI(
        model="gpt-4o-mini",      # Bom equilíbrio custo/qualidade
        temperature=0.3,          # Baixa criatividade para respostas financeiras precisas
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
    )

    # ── Ferramenta disponível para o agente ─────────────────────
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

    # ── Prompt do sistema (instrução de comportamento) ───────────
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

    # ── Criação do agente ReAct ──────────────────────────────────
    agente = create_react_agent(llm=llm, tools=ferramentas, prompt=prompt_template)

    executor = AgentExecutor(
        agent=agente,
        tools=ferramentas,
        verbose=True,           # Mostra o raciocínio nos logs do servidor
        max_iterations=5,       # Evita loops infinitos
        handle_parsing_errors=True,  # Recupera de erros de formatação do LLM
    )

    return executor


# ══════════════════════════════════════════════
# BLOCO 4: HANDLERS DO TELEGRAM
# ══════════════════════════════════════════════

# Instância global do agente (criada uma vez ao iniciar o bot)
agente_executor: AgentExecutor = None


async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler para o comando /start.
    Enviado automaticamente quando o usuário inicia o bot pela primeira vez.
    """
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
    """
    Handler para o comando /ajuda.
    Exibe dicas de uso e exemplos de perguntas.
    """
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
    Handler principal: processa toda mensagem de texto enviada pelo usuário.

    Fluxo:
      1. Recebe a mensagem do usuário
      2. Envia para o agente LangChain
      3. O agente decide consultar a planilha se necessário
      4. Retorna a resposta formatada

    Args:
        update: Objeto do Telegram com dados da mensagem
        context: Contexto da conversa (não utilizado diretamente aqui)
    """
    pergunta = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Mensagem recebida do usuário {user_id}: {pergunta[:50]}...")

    # Avisa que está processando (evita o usuário achar que travou)
    await update.message.chat.send_action("typing")

    try:
        # Invoca o agente com a pergunta do usuário
        resultado = agente_executor.invoke({"input": pergunta})
        resposta = resultado.get("output", "Não consegui processar sua pergunta.")

    except Exception as e:
        logger.error(f"Erro ao processar mensagem: {e}")
        resposta = (
            "⚠️ Ocorreu um erro ao processar sua pergunta.\n"
            "Verifique se a planilha está acessível e tente novamente.\n"
            f"_Detalhe técnico: {str(e)[:100]}_"
        )

    await update.message.reply_text(resposta, parse_mode="Markdown")


# ══════════════════════════════════════════════
# BLOCO 5: INICIALIZAÇÃO DO BOT
# ══════════════════════════════════════════════

def main() -> None:
    """
    Ponto de entrada principal da aplicação.

    Inicializa o agente LangChain e o bot do Telegram,
    registra os handlers e inicia o polling (escuta contínua).

    Para rodar em produção (Render/Railway), este arquivo deve ser
    executado diretamente: `python main.py`
    """
    global agente_executor

    # ── Valida variáveis de ambiente obrigatórias ────────────────
    variaveis_obrigatorias = [
        "TELEGRAM_TOKEN",
        "OPENAI_API_KEY",
        "GOOGLE_SHEETS_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON",
    ]
    ausentes = [v for v in variaveis_obrigatorias if not os.environ.get(v)]
    if ausentes:
        raise EnvironmentError(
            f"Variáveis de ambiente ausentes: {', '.join(ausentes)}\n"
            "Configure-as antes de iniciar o bot."
        )

    logger.info("Inicializando agente LangChain...")
    agente_executor = criar_agente()
    logger.info("Agente criado com sucesso!")

    # ── Configura o bot do Telegram ─────────────────────────────
    token = os.environ.get("TELEGRAM_TOKEN")
    app = Application.builder().token(token).build()

    # Registra os handlers de comandos
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("ajuda", comando_ajuda))

    # Handler para mensagens de texto comuns (exclui comandos /)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagem))

    logger.info("Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import os
from flask import Flask
import threading

# Cria um mini servidor web fantasma
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Roda o servidor web em uma thread separada
    threading.Thread(target=run_web, daemon=True).start()
    
    # Aqui vai o comando que inicia seu bot (exemplo):
    # seu_bot.run_polling() 
    print("Bot iniciado...")