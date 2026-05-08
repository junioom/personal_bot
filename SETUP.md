# 🤖 Bot Telegram — Assistente de Finanças Pessoais

> Powered by LangChain ReAct Agent + Google Sheets + OpenAI

---

## 📁 Estrutura do Projeto

```
telegram-finance-bot/
├── main.py           ← Código principal do bot
├── requirements.txt  ← Dependências Python
└── SETUP.md          ← Este guia
```

---

## 🔑 Passo 1 — Obter o Token do Telegram

1. Abra o Telegram e procure por **@BotFather**
2. Envie `/newbot` e siga as instruções
3. Copie o token gerado (formato: `123456:ABCdef...`)
4. Guarde como variável de ambiente: `TELEGRAM_TOKEN`

---

## 📊 Passo 2 — Configurar o Google Sheets

### 2.1 — Criar o projeto no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um novo projeto (ex: `finance-bot`)
3. No menu lateral: **APIs e serviços** → **Biblioteca**
4. Ative as duas APIs:
   - ✅ **Google Sheets API**
   - ✅ **Google Drive API**

### 2.2 — Criar a Conta de Serviço

1. Vá em **APIs e serviços** → **Credenciais**
2. Clique em **+ Criar credenciais** → **Conta de serviço**
3. Dê um nome (ex: `finance-bot-sa`) e clique em **Criar**
4. Clique na conta de serviço criada → aba **Chaves**
5. **Adicionar chave** → **Criar nova chave** → **JSON**
6. O arquivo `.json` será baixado automaticamente

### 2.3 — Configurar a variável de ambiente

Abra o arquivo `.json` baixado em um editor de texto.
Copie **todo o conteúdo** (incluindo as chaves `{}`) e cole como:
```
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"..."}
```

> ⚠️ O conteúdo deve ser uma linha só, sem quebras de linha extras.

### 2.4 — Compartilhar a planilha com a Conta de Serviço

1. Abra o arquivo `.json` e copie o campo `"client_email"` 
   (algo como `finance-bot-sa@seu-projeto.iam.gserviceaccount.com`)
2. Abra sua planilha Google Sheets
3. Clique em **Compartilhar** e adicione esse e-mail com permissão de **Leitor**

### 2.5 — Obter o ID da planilha

Na URL da planilha:
```
https://docs.google.com/spreadsheets/d/AQUI_ESTÁ_O_ID/edit
```
Copie a parte destacada e salve como: `GOOGLE_SHEETS_ID`

---

## 📋 Passo 3 — Estrutura da Planilha

Sua planilha deve ter exatamente estas colunas (nomes exatos):

| Coluna | Tipo | Exemplo |
|---|---|---|
| `Carimbo de data/hora` | Automático (Forms) | `01/05/2025 14:30:00` |
| `Qual a categoria do Gasto?` | Texto | `Alimentação` |
| `Quanto custou?` | Número | `45.90` |
| `Quando foi?` | Data | `01/05/2025` |
| `Descrição do que foi` | Texto | `Almoço restaurante` |

> 💡 Dica: Use Google Forms vinculado à planilha para cadastrar gastos pelo celular!

---

## 🚀 Passo 4 — Deploy no Render.com

### 4.1 — Subir o código para o GitHub

```bash
git init
git add main.py requirements.txt
git commit -m "feat: bot financeiro com IA"
git remote add origin https://github.com/SEU_USUARIO/finance-bot.git
git push -u origin main
```

### 4.2 — Criar o serviço no Render

1. Acesse [render.com](https://render.com) e faça login
2. Clique em **New** → **Web Service**
3. Conecte seu repositório GitHub
4. Configure:
   - **Name**: `finance-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: `Free` (suficiente para uso pessoal)

### 4.3 — Adicionar variáveis de ambiente no Render

Em **Environment** → **Add Environment Variable**, adicione:

| Chave | Valor |
|---|---|
| `TELEGRAM_TOKEN` | Token do BotFather |
| `OPENAI_API_KEY` | `sk-...` |
| `GOOGLE_SHEETS_ID` | ID da planilha |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Conteúdo completo do `.json` |

Clique em **Deploy**! 🎉

---

## 🛠️ Rodar Localmente (Desenvolvimento)

Crie um arquivo `.env` na raiz do projeto:
```env
TELEGRAM_TOKEN=seu_token_aqui
OPENAI_API_KEY=sk-sua_chave_aqui
GOOGLE_SHEETS_ID=id_da_planilha
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

Instale as dependências e rode:
```bash
pip install -r requirements.txt
python main.py
```

> O arquivo `.env` é carregado automaticamente pela lib `python-dotenv`.
> **Nunca** suba o `.env` para o GitHub! Adicione ao `.gitignore`.

---

## 💬 Exemplos de Perguntas ao Bot

Após configurado, você pode perguntar:

- *"Quanto gastei este mês?"*
- *"Qual categoria tem mais gastos?"*
- *"Mostre meus gastos com alimentação em abril"*
- *"Qual foi meu maior gasto?"*
- *"Quanto gastei na última semana?"*
- *"Faça um resumo financeiro do mês de março"*
- *"Compare meus gastos de fevereiro e março"*

---

## ⚠️ Solução de Problemas

| Problema | Causa provável | Solução |
|---|---|---|
| `SpreadsheetNotFound` | ID da planilha errado | Verifique o ID na URL |
| `Insufficient permission` | Planilha não compartilhada | Compartilhe com o `client_email` |
| `Invalid token` | Token do Telegram errado | Recrie pelo BotFather |
| `AuthenticationError` | Chave OpenAI inválida | Verifique no painel da OpenAI |
| Bot não responde | Bot está offline | Verifique os logs no Render |

---

## 📌 Tecnologias Utilizadas

- **python-telegram-bot** — Interface assíncrona com a API do Telegram
- **LangChain** — Framework do Agente ReAct (raciocínio + ferramentas)
- **OpenAI GPT-4o-mini** — Modelo de linguagem do agente
- **gspread** — Leitura da planilha Google Sheets
- **pandas** — Análise e filtragem dos dados financeiros
- **Render.com** — Hospedagem gratuita do bot
