
# StockSage

Built with LangChain and LangGraph for agent orchestration and workflow control.

StockSage researches current technology-company news, compares potential
investment candidates, recommends a company, and can send the recommendation to
your phone after you approve it.

Try it at https://amitg23-stock-sage.hf.space

## How it works

The interface is button-driven and has no text input. Click **Go!** to start the
built-in research request. StockSage researches trending technology companies,
tracks its work in the PLAN panel, and presents its conclusion before asking to
send a push notification.

Use **Approve** to send the notification or **Reject** to have StockSage continue
with an alternative recommendation. **Reset** clears the current run and starts
a fresh session. The chat window displays the run's output; users interact
through these buttons.

## Integrations

- **LangChain / LangGraph** powers the research agent workflow and stateful execution.
- **OpenAI** powers the research agent and response evaluator.
- **Google Serper** provides web search.
- **Pushover** sends approved recommendations to your phone.

## Setup and run

Install the dependencies in `requirements.txt`, then create a `.env` file in the
project root with the required credentials:

```dotenv
OPENAI_API_KEY=your-openai-api-key
SERPER_API_KEY=your-serper-api-key
PUSHOVER_TOKEN=your-pushover-application-token
PUSHOVER_USER=your-pushover-user-key
```

Start the app from the project root:

```sh
uv run python src/app.py
```

The agent's checkpoints are kept in memory and are cleared when the app process
restarts.

## Running tests

Run the unit tests from the project root with Python's standard-library
`unittest` runner:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```
## Disclaimer
StockSage is not a real-time trading advisory service and its output should not be used  as a trading recommendation or as a substitute for independent financial advice.