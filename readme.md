# 💰 FinTrack Bot — Personal Finance Automation via Telegram

> Automação de controle financeiro pessoal com integração em nuvem, processamento de dados em tempo real e interface conversacional via Telegram.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram%20Bot%20API-v20+-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-34A853?style=flat-square&logo=google-sheets&logoColor=white)
![Render](https://img.shields.io/badge/Deploy-Render.com-46E3B7?style=flat-square&logo=render&logoColor=white)
![Status](https://img.shields.io/badge/Status-Produção-success?style=flat-square)

---

## 📌 Descrição Geral

O **FinTrack Bot** nasceu de uma necessidade prática: acompanhar gastos pessoais de forma ágil, sem depender de aplicativos complexos ou planilhas que exigem abertura manual. O objetivo era criar um canal de consulta financeira disponível a qualquer momento, diretamente no Telegram — o aplicativo de mensagens já presente na rotina diária.

O projeto resolve três problemas centrais:

- **Fragmentação do registro financeiro** — os dados são inseridos via Google Forms (acessível de qualquer dispositivo) e armazenados automaticamente em uma planilha Google Sheets, eliminando o atrito do registro manual.
- **Falta de visibilidade rápida** — consultas por categoria, mês ou período são respondidas em segundos via comandos de texto, sem necessidade de abrir planilhas ou aplicativos de finanças.
- **Dependência de ferramentas pagas** — toda a stack utiliza serviços gratuitos ou de baixo custo, tornando a solução acessível e sustentável.

---

## ⚙️ Funcionalidades

| Funcionalidade | Descrição |
|---|---|
| 📥 Registro via formulário | Novos gastos cadastrados pelo Google Forms, refletidos instantaneamente na base |
| 🗂️ Categorização | Filtragem por categorias customizáveis (Alimentação, Transporte, Pix, etc.) |
| 📊 Relatório mensal | Listagem completa de gastos do mês com total consolidado |
| 🏷️ Relatório por categoria | Gastos de uma categoria específica em um mês, com soma final |
| 📋 Resumo de categorias | Visão agregada de todas as categorias do mês com totais individuais |
| 🔍 Busca inteligente | Pesquisa parcial e sem acento — "aliment" localiza "Alimentação" |
| 💬 Interface conversacional | Interação via comandos no Telegram, sem necessidade de interface gráfica |
| ☁️ Disponibilidade contínua | Bot hospedado em nuvem, disponível 24/7 sem depender de máquina local |
| 🔒 Segurança por variáveis de ambiente | Credenciais isoladas do código-fonte via environment variables |

---

## 🏗️ Arquitetura do Projeto

### Visão Geral do Fluxo

```
┌─────────────┐     Comando      ┌─────────────────┐     HTTPS/Webhook    ┌──────────────────┐
│   Usuário   │ ──────────────▶  │  Telegram API   │ ───────────────────▶ │  Backend Python  │
│  (Telegram) │                  │                 │                       │  (Flask + PTB)   │
└─────────────┘                  └─────────────────┘                       └────────┬─────────┘
                                                                                    │
                                                                          gspread + pandas
                                                                                    │
                                                                                    ▼
┌─────────────┐   Resposta       ┌─────────────────┐     Dados filtrados  ┌──────────────────┐
│   Usuário   │ ◀──────────────  │  Telegram API   │ ◀─────────────────── │  Google Sheets   │
│  (Telegram) │                  │                 │                       │   (Data Source)  │
└─────────────┘                  └─────────────────┘                       └──────────────────┘
```

### Detalhamento por Camada

**1. Camada de Entrada de Dados**
O usuário registra gastos via Google Forms — uma interface mobile-friendly que não exige instalação. Cada resposta é automaticamente gravada como uma nova linha na planilha Google Sheets vinculada, com carimbo de data/hora gerado automaticamente.

**2. Camada de Interface (Telegram)**
O usuário interage com o bot via comandos de texto no Telegram. Cada mensagem é enviada ao servidor via protocolo Webhook — o Telegram realiza uma requisição HTTPS para a URL do backend sempre que uma mensagem é recebida, eliminando a necessidade de polling contínuo.

**3. Camada de Backend (Python + Flask)**
O servidor Flask recebe os eventos do Telegram, identifica o comando e aciona o handler correspondente. A biblioteca `python-telegram-bot` (v20+) gerencia o ciclo de vida assíncrono das mensagens. O processamento de dados é feito com `pandas`, garantindo filtragens rápidas e precisas independentemente do volume de registros.

**4. Camada de Dados (Google Sheets)**
A planilha atua como banco de dados leve e de fácil manutenção. A autenticação ocorre via Google Service Account, com credenciais armazenadas como variável de ambiente — nunca expostas no repositório.

**5. Camada de Infraestrutura (Render.com)**
O backend está hospedado no Render, que mantém o servidor HTTP ativo de forma contínua. O deploy é realizado diretamente a partir do repositório GitHub, com build automático a cada novo push.

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Versão | Papel no Projeto |
|---|---|---|
| **Python** | 3.11+ | Linguagem principal da aplicação |
| **python-telegram-bot** | 20.7 | Integração assíncrona com a Telegram Bot API |
| **Flask** | 3.0.3 | Servidor HTTP para recepção dos webhooks |
| **gspread** | 6.1.2 | Leitura e autenticação na API do Google Sheets |
| **google-auth** | 2.29.0 | Autenticação via Service Account no Google Cloud |
| **pandas** | 2.2.2 | Manipulação, filtragem e agregação dos dados financeiros |
| **Google Sheets** | — | Armazenamento dos registros financeiros |
| **Google Forms** | — | Interface de entrada de dados (formulário mobile) |
| **Telegram Bot API** | — | Canal de comunicação e interface do usuário |
| **Render.com** | — | Hospedagem do backend em nuvem (PaaS) |
| **Google Cloud** | — | Gerenciamento de credenciais via Service Account |

---

## 🤖 Uso de IA no Desenvolvimento

O desenvolvimento do FinTrack Bot adotou IA generativa como **ferramenta de aceleração produtiva**, não como substituto do raciocínio técnico.

As decisões de maior impacto — arquitetura da solução, escolha da stack, modelo de dados, fluxo de interação e estratégia de deploy — foram definidas e validadas manualmente, com base em critérios técnicos e de produto. A IA foi acionada de forma estratégica nas seguintes frentes:

- **Geração de boilerplate:** estruturação inicial de handlers, configuração do webhook e setup do Flask, acelerando etapas repetitivas sem valor diferencial.
- **Otimização de código:** refinamento de funções de filtragem e formatação de dados com pandas, com revisão e adaptação manual posterior.
- **Documentação:** apoio na estruturação de docstrings e comentários técnicos, revisados e ajustados para refletir a lógica real implementada.
- **Resolução de erros:** diagnóstico assistido de incompatibilidades entre `run_polling` e a infraestrutura do Render, com a solução arquitetural (migração para Webhook + Flask) definida pelo desenvolvedor.

Toda saída gerada por IA passou por revisão crítica, testes funcionais e ajustes manuais antes de ser incorporada ao projeto. O uso de IA representou uma redução significativa no tempo de desenvolvimento sem comprometer a qualidade técnica ou a propriedade intelectual da solução.

---

## 🔄 Pipeline e Automações

```
[Google Forms]
      │
      │  Resposta submetida
      ▼
[Google Sheets]  ◀─── Gravação automática pelo Forms
      │
      │  gspread.get_all_records()
      ▼
[pandas DataFrame]
      │
      ├── Limpeza de dados (conversão de tipos, remoção de símbolos)
      ├── Filtragem por mês / categoria
      ├── Agregações (sum, count, groupby)
      │
      ▼
[Formatação da resposta]
      │
      ▼
[Telegram API]  ──▶  Mensagem entregue ao usuário
```

**Processamento de mensagens:**
Cada comando recebido passa por validação de argumentos, resolução de parâmetros (ex: nome do mês para número), consulta à planilha e formatação da resposta. O tratamento de erros está presente em todas as camadas, com mensagens descritivas retornadas ao usuário em caso de falha.

**Automações ativas:**
- Carimbo de data/hora gerado automaticamente pelo Google Forms
- Conversão automática de tipos no carregamento da planilha
- Busca de categoria sem acento e case-insensitive
- Divisão automática de mensagens longas respeitando o limite do Telegram (4.096 caracteres)

**Integrações futuras planejadas:**
- Triggers automáticos por valor de gasto (alertas)
- Exportação periódica de relatórios via agendamento
- Integração com APIs bancárias abertas (Open Finance)

---

## 🚀 Deploy e Infraestrutura

### Hospedagem — Render.com

O backend está implantado no Render como um **Web Service** Python, com as seguintes configurações:

| Configuração | Valor |
|---|---|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python main.py` |
| Ambiente | Python 3.11 |
| Instância | Free tier (escalável) |

### Webhook vs. Polling

A escolha pelo modelo **Webhook** em vez de polling foi deliberada e motivada por limitações de infraestrutura:

- O `run_polling` mantém um loop bloqueante que impede o Render de inicializar corretamente o servidor HTTP.
- Com Webhook, o Telegram realiza chamadas HTTPS para a URL do serviço, que responde de forma assíncrona via Flask — compatível com qualquer PaaS que exija um servidor HTTP ativo.

### Segurança

- Todas as credenciais são armazenadas como **variáveis de ambiente** no Render, nunca no repositório.
- O endpoint do webhook utiliza o token do bot na URL como camada de autenticação implícita.
- As credenciais do Google Cloud são carregadas em arquivo temporário na memória e removidas imediatamente após uso.

---

## 🧩 Desafios Técnicos

**1. Incompatibilidade entre `run_polling` e Render**
O principal obstáculo de deploy foi identificar que o modo polling bloqueava a inicialização do servidor HTTP, causando falha no healthcheck do Render. A solução foi migrar para arquitetura Webhook com Flask, replicando o padrão já validado em outro bot em produção.

**2. Gerenciamento de credenciais em ambiente efêmero**
O filesystem do Render é efêmero — arquivos escritos em disco não persistem entre deploys. A solução foi injetar o JSON de credenciais via variável de ambiente e gravá-lo em arquivo temporário apenas durante a autenticação, removendo-o logo em seguida.

**3. Parsing de dados do Google Sheets**
Dados inseridos via formulário chegam como strings com formatações variadas (vírgulas, símbolos de moeda, datas em formatos distintos). Foi necessário implementar uma pipeline de limpeza e tipagem robusta com pandas para garantir consistência nas agregações.

**4. Limite de caracteres do Telegram**
Respostas com muitos registros ultrapassavam o limite de 4.096 caracteres por mensagem. A solução implementada divide automaticamente a resposta em partes sequenciais, mantendo a experiência do usuário sem erros silenciosos.

**5. Busca de categorias sem acento**
Usuários naturalmente digitam sem acentuação ("alimentacao", "transporte"). Foi implementada normalização Unicode para comparação insensível a acentos e maiúsculas, eliminando falsos negativos nas buscas.

---

## 🔭 Melhorias Futuras

| Melhoria | Descrição | Impacto |
|---|---|---|
| 📊 Dashboard Power BI | Conexão direta ao Google Sheets para visualizações interativas | Alto |
| 🧠 IA para insights | Análise de padrões de gasto e recomendações personalizadas | Alto |
| 🗄️ Banco de dados relacional | Migração para PostgreSQL para suporte a maior volume e consultas complexas | Médio |
| 🔔 Alertas inteligentes | Notificações automáticas ao atingir limites de categoria | Alto |
| 👤 Autenticação multi-usuário | Suporte a múltiplos usuários com dados isolados por conta Telegram | Médio |
| 📈 Análise preditiva | ML para projeção de gastos com base em histórico | Alto |
| 🏦 Open Finance | Integração com APIs bancárias para importação automática de transações | Alto |
| 📅 Relatórios agendados | Envio automático de resumo semanal/mensal sem necessidade de comando | Médio |
| 🧾 OCR de comprovantes | Extração automática de valor e data a partir de fotos de recibos | Alto |

---

## 📚 Conclusão

O FinTrack Bot é um projeto que vai além do controle financeiro pessoal — é uma demonstração prática de como integrar múltiplas tecnologias para resolver um problema real com baixo custo operacional e alta disponibilidade.

Do ponto de vista técnico, o projeto consolida competências em **engenharia de dados** (pipeline de ingestão e transformação), **desenvolvimento backend** (APIs, webhooks, deploy em nuvem), **automação** (formulários, processamento assíncrono) e **uso estratégico de IA** como ferramenta de produtividade.

A arquitetura foi projetada com escalabilidade em mente: a substituição do Google Sheets por um banco relacional, a adição de novos comandos ou a expansão para múltiplos usuários podem ser feitas de forma incremental, sem reestruturação do sistema.

Mais do que um bot, o FinTrack é um produto funcional em produção — desenvolvido com visão de engenharia, boas práticas de segurança e foco na experiência do usuário final.

---

<div align="center">

**Desenvolvido com 🐍 Python · ☁️ Render · 📊 Google Sheets · 🤖 Telegram**

</div>
