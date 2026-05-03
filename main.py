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
import asyncio
from datetime import datetime

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# CORREÇÃO DAS IMPORTAÇÕES (Padrão LangChain 0.1+)
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# 1. CONFIGURAÇÃO DE LOGS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. FLASK E CONFIGURAÇÕES
app = Flask(__name__)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL") # URL do seu app no Render

# 3. FUNÇÕES DE APOIO (GOOGLE SHEETS)
def obter_credenciais_google():
    json_content = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write(json_content)
        tmp_path = tmp.name
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
        credenciais = Credentials.from_service_account_file(tmp_path, scopes=scopes)
    finally:
        os.unlink(tmp_path)
    return credenciais

def baixar_dados_planilha():
    credenciais = obter_credenciais_google()
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(os.environ.get("GOOGLE_SHEETS_ID"))
    df = pd.DataFrame(planilha.sheet1.get_all_records())
    
    if not df.empty:
        if "Quanto custou?" in df.columns:
            df["Quanto custou?"] = df["Quanto custou?"].astype(str).str.replace(r"[R$\s]", "", regex=True).str.replace(",", ".", regex=False)
            df["Quanto custou?"] = pd.to_numeric(df["Quanto custou?"], errors="coerce")
        if "Quando foi?" in df.columns:
            df["Quando foi?"] = pd.to_datetime(df["Quando foi?"], dayfirst=True, errors="coerce")
    return df

def consultar_planilha(pergunta: str) -> str:
    df = baixar_dados_planilha()
    if df.empty: return "Planilha vazia."
    # (O restante da sua lógica de resumo aqui...)
    return f"Dados carregados. Total gasto: R$ {df['Quanto custou?'].sum():.2f}"

# 4. CRIAÇÃO DO AGENTE
def criar_agente():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    ferramentas = [Tool(name="consultar_planilha", func=consultar_planilha, description="Consulta gastos.")]
    prompt = PromptTemplate.from_template("Responda em PT-BR... {tools} {tool_names} {input} {agent_scratchpad}")
    
    agente = create_react_agent(llm, ferramentas, prompt)
    return AgentExecutor(agent=agente, tools=ferramentas, verbose=True, handle_parsing_errors=True)

agente_executor = criar_agente()

# 5. HANDLERS DO TELEGRAM
async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pergunta = update.message.text
    resultado = agente_executor.invoke({"input": pergunta})
    await update.message.reply_text(resultado["output"])

# 6. INICIALIZAÇÃO DO TELEGRAM (Igual ao seu bot_telegram.py)
telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, processar_mensagem))

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(telegram_app.initialize())
loop.run_until_complete(telegram_app.start())

# 7. ROTAS WEBHOOK (Para o Render não dar erro 127/Status 1)
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    update = Update.de_json(data, telegram_app.bot)
    loop.run_until_complete(telegram_app.process_update(update))
    return "ok"

@app.route("/")
def home():
    return "FinBot Rodando!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)