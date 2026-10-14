# StockSage Design

## Purpose

StockSage is a Gradio application that researches current technology-company news,
compares potential investment candidates, recommends a company, and can send the
recommendation to the user's phone after human approval.

## Architecture

```text
Gradio UI (app.py)
  ├── Output-only chat, Go / Reset / Approve / Reject controls
  ├── Live plan panel
  └── StockSage session state
        ├── Research agent and evaluator (stock_sage.py)
        ├── In-memory LangGraph checkpoint
        └── Tools (stock_sage_tools.py)
              ├── Google Serper web search
              ├── Pushover notification
              └── Human-help request

Presentation and theme (styles.py)
```

### UI: `app.py`

The Gradio UI owns the conversation history and a `StockSage` instance stored in
`gr.State`. There is no text-entry component: the user cannot submit arbitrary
messages. On page load, the UI initializes the agent and enables Go. Go starts
the built-in default research request. Reset clears the chat and approval
controls and creates a fresh agent instance.

The chat is an output-only transcript for the request and agent responses. The
user interacts only through the buttons. The adjacent PLAN panel renders the
agent's todo state as HTML; todo content is HTML-escaped before rendering. A
one-second timer refreshes the plan while the agent is working. Approve and Reject
resume a paused agent turn and refresh the plan when the action finishes.

### Research and evaluation: `stock_sage.py`

Each `StockSage` instance has a unique thread ID and an in-memory LangGraph
checkpointer. The configured research agent uses the current date in its system
prompt, researches trending technology companies, and is instructed to present a
conclusion with supporting research and key risks before requesting notification
approval.

The agent is configured with:

- A todo-list middleware to expose its work plan.
- PII middleware for email and credit-card data.
- A model-call limit middleware.
- Human-in-the-loop gates for `send_push_notification` and
  `request_human_help`.
- Tool-error middleware that returns tool failures to the agent as messages so it
  can try to recover.

After a non-interrupted response, a structured evaluator checks whether the
success criteria have been met or whether more user input is needed. Since the UI
has no freeform input, the agent cannot receive an arbitrary text reply from the
user; it can only explain what it needs in the output chat. If the success
criteria are unmet and no user input is needed, the agent receives the evaluator's
feedback and tries again, up to `MAX_ATTEMPTS` (currently three).

When an action requires approval, the agent turn pauses. The app displays the
research conclusion and an approval prompt, then exposes Approve and Reject.
Approval resumes the interrupted action. Rejection resumes the run with a reject
decision so the agent can continue its alternative-recommendation flow.

### Integrations: `stock_sage_tools.py`

- **Search:** `GoogleSerperRun` is configured with `GoogleSerperAPIWrapper` for
  web search.
- **Push notifications:** `send_push_notification` posts the recommendation to
  the Pushover API. The human-in-the-loop middleware gates this side effect until
  approval.
- **Human assistance:** `request_human_help` informs the user when a browser
  action such as login or CAPTCHA completion requires their involvement.

### Presentation: `styles.py`

Defines the Gradio theme, brand colors, page CSS, and a small script that selects
light mode. The CSS styles the header, chat, plan, and action buttons.

## State and persistence

Agent state is kept in process memory through `InMemorySaver` and is associated
with a unique thread ID for each `StockSage` instance. It is not persisted across
application restarts. The UI stores the current instance in Gradio session state.
The PLAN panel is derived from the agent's current todo list.

## Configuration and running

Install dependencies listed in `requirements.txt`. Create a local `.env` file
with the credentials needed by the integrations:

- `OPENAI_API_KEY` for the OpenAI-backed agent and evaluator.
- `SERPER_API_KEY` for Google Serper search.
- `PUSHOVER_TOKEN` and `PUSHOVER_USER` for phone notifications.

Run the application from the project root:

```sh
uv run python src/app.py
```

## Tests

The unit tests use Python's standard-library `unittest` framework and mock
external agent/tool interactions. Run them from the project root:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```
