# AI Document Creator Agent

LLM-guided browser automation agent for creating and filling documents in the Conneto web application.

The project combines **LangChain**, **OpenAI GPT-4o**, and **Selenium** to analyze the current browser state, decide what step should happen next, generate Selenium actions dynamically, request missing business information from the user, and retry failed actions with LLM-assisted error correction.

> **Status:** experimental / portfolio project. The repository demonstrates an agentic browser-automation architecture rather than a general-purpose production browser agent.

## What the project does

The agent automates a multi-step document workflow in `https://app.conneto.com/`:

1. Opens the web application and authenticates.
2. Detects the current page and workflow state.
3. Navigates to **Documents** and starts a new document.
4. Selects **Create from template**.
5. Requests missing business data from the user when required.
6. Helps identify an appropriate document template.
7. Generates Selenium code for the current page and executes it.
8. Fills document fields in English while allowing user interaction in another language.
9. Detects execution errors and asks the LLM to generate a corrected Selenium action.
10. Continues until the workflow reaches the completion state.

## Why LangChain is used

This is a **LangChain-based agentic workflow** rather than a simple scripted Selenium bot.

LangChain is used for:

- `ChatOpenAI` integration with the LLM;
- structured agent components for navigation and prompt generation;
- LangChain `BaseTool` abstractions for browser-related tools;
- message construction with `SystemMessage` / `HumanMessage`;
- LLM-assisted recovery when generated Selenium code fails.

The browser itself is controlled by Selenium. LangChain provides the orchestration layer around LLM reasoning and tool execution.

## Architecture

```text
User
  │
  ▼
MainAgent
  │
  ├── PageContextTool ─────► reads URL, page HTML and interactive elements
  │
  ├── NavigatorAgent ──────► determines the current workflow state
  │                           using page context + LLM reasoning
  │
  ├── PromptGeneratorAgent ► builds a task-specific prompt for the current state
  │
  ├── ChatOpenAI / GPT-4o ─► generates Selenium actions
  │
  ├── SeleniumTool ────────► executes browser actions
  │
  ├── QuestionTool ────────► requests missing business information from the user
  │
  ├── ErrorFixTool ────────► regenerates failed Selenium actions from error context
  │
  └── AgentMemory ─────────► keeps workflow state, user answers, actions and errors
```

### Agent loop

```text
Analyze page
   ↓
Determine state
   ↓
Generate action prompt
   ↓
LLM generates Selenium code
   ↓
Execute action
   ↓
Success? ── yes ──► analyze next page
   │
   no
   ↓
Generate corrected code from error + page context
   ↓
Retry
```

## Main components

### `MainAgent`
Coordinates the full workflow. It initializes the LLM, memory, sub-agents and tools, then runs the iterative analyze → decide → generate → execute → verify loop.

### `NavigatorAgent`
Determines the current browser state. Some states are recognized deterministically from the URL, while others are classified with GPT-4o from page context.

### `PromptGeneratorAgent`
Creates state-specific instructions for Selenium code generation. Different prompts are used for login, navigation, preliminary data collection, template selection and document filling.

### `PageContextTool`
Extracts the current page context so that the agent can reason about the page instead of relying only on hard-coded selectors.

### `SeleniumTool`
Executes generated Python/Selenium actions against the already-open browser session.

### `QuestionTool`
Supports human-in-the-loop interaction when information required to fill the current form is missing.

### `ErrorFixTool`
Uses the original action, exception message, current page context and original prompt to generate a corrected Selenium action and retry the step.

## Tech stack

- **Python**
- **LangChain**
- **langchain-openai**
- **OpenAI GPT-4o**
- **Selenium 4**
- **webdriver-manager**
- **Pydantic**
- **python-dotenv**
- **HTTPX**

## Project structure

```text
new_ur_s/
├── agents/
│   ├── main_agent.py
│   ├── navigator_agent.py
│   ├── prompt_generator_agent.py
│   └── models.py
├── memory/
├── tools/
│   ├── error_fix_tool.py
│   ├── page_context_tool.py
│   ├── question_tool.py
│   └── selenium_tool.py
├── config.py
├── run_agent.py
├── gui_agent.py
├── example_usage.py
├── requirements.txt
├── env_example.txt
└── INSTALL.md
```

## Installation

### Requirements

- Python 3.8+
- Google Chrome
- OpenAI API key with access to the configured model

### 1. Clone the repository

```bash
git clone https://github.com/shibumi2906/new_ur_s.git
cd new_ur_s
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

**Windows**

```bash
.venv\Scripts\activate
```

**macOS / Linux**

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root.

```env
OPENAI_API_KEY=your_openai_api_key
PROXY_URL=
DEFAULT_EMAIL=your_email
DEFAULT_PASSWORD=your_password
BASE_URL=https://app.conneto.com/
```

Do **not** commit real API keys, passwords, tokens or proxy credentials.

### 5. Run

```bash
python run_agent.py
```

ChromeDriver is managed automatically through `webdriver-manager`.

## Agent states

The navigation layer models the document workflow as explicit states, including:

- login
- home / first page
- documents page
- create from template
- preliminary data
- template selection
- document filling
- file upload
- completion

This lets the system combine deterministic routing with LLM reasoning instead of asking the model to rediscover the entire workflow on every step.

## Human-in-the-loop behavior

The agent can stop execution and ask the user for missing information when a form cannot be completed safely from the existing context.

The intended separation is:

- the **LLM** interprets the page and decides what information is needed;
- the **user** supplies business-specific facts;
- the **automation layer** performs browser actions;
- **memory** preserves answers and action history across steps.

## Error recovery

Browser automation is fragile because DOM structure, visibility and timing can change. Instead of immediately terminating on an execution error, the project implements an LLM-assisted recovery loop:

```text
failed Selenium action
        ↓
exception + page context + original prompt
        ↓
ErrorFixTool / GPT-4o
        ↓
corrected Selenium action
        ↓
retry
```

The number of retries is controlled by configuration.

## Design goals

The project explores several practical ideas for agentic automation:

- combining deterministic workflow states with LLM interpretation;
- generating browser actions from live page context;
- human-in-the-loop data collection;
- memory across multi-step workflows;
- automatic recovery from browser-action failures;
- separating navigation reasoning from action generation.

## Limitations

- The workflow is currently specialized for the Conneto document-creation flow.
- Generated browser actions depend on the current DOM and may require adaptation when the website changes.
- LLM-generated Selenium code must be treated as untrusted code and should be sandboxed before production use.
- Authentication and secret handling should be moved entirely to secure environment/secret storage for any real deployment.
- The current project is a prototype and has not been presented here as a production-hardened autonomous browser system.

## Security

Never store real credentials in tracked source files.

If a secret has ever been committed to a public repository, removing it from the latest version is **not sufficient**. Rotate/revoke the exposed credential and remove it from Git history where appropriate.

Recommended production approach:

- `.env` only for local development;
- secret manager / CI secrets for deployed environments;
- no default passwords or API keys in source code;
- restricted API keys and least-privilege credentials;
- explicit confirmation before high-impact browser actions.

## License

See [LICENSE](LICENSE).
