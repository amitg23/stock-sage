import os
from dotenv import load_dotenv
from datetime import datetime
from pydantic import BaseModel, Field
import uuid
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    TodoListMiddleware,
    PIIMiddleware,
    ModelCallLimitMiddleware,
    HumanInTheLoopMiddleware,
)
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from stock_sage_tools import get_all_tools

load_dotenv(override=True)

MODEL_NAME=os.getenv("MODEL_NAME")
MAX_ATTEMPTS = 3
DEFAULT_MESSAGE = "Search on internet for latest financial news and trends. Find the best company to invest in based on the latest news."
DEFAULT_SUCCESS_CRITERIA = "The analyst is able to find the best company to invest in."

TRENDING_COMPANY_FINDER_PROMPT="""
You are a market expert with a knack for picking out the most interesting companies based on latest news.
You spot multiple companies that are trending in the news.
You read the latest news, then find 2-3 companies that are trending in the news for further research.
If you reach something only a human can do, like logging in, a captcha, or two-factor authentication, use the request_human_help tool to tell the user exactly
what to do in your browser window, then carry on once they have done it.
Always pick new companies. Don't pick the same company twice. Ensure research as of today's date.
Find the top trending companies in the news in Technology as of today's date by searching the latest news. Find new companies that you've not found before.
"""

FINANCIAL_RESEARCHER_PROMPT="""
You are a meticulous, skilled financial analyst with a proven track record of deeply analyzing hot companies and building comprehensive reports.
You have a talent for synthesizing research and picking the best company for investment.
Given details of trending companies in the news, provide comprehensive analysis of each in a report. Ensure research is up to date as of today's date.
Based on this report, select the best one for investment. Before calling send_push_notification, give the user a clear conclusion with the selected company, the research supporting the choice, and the key risk. Include this user-facing conclusion in the same assistant response that calls the tool, so it is shown before the approval prompt. Then call send_push_notification with a concise recommendation as its message. This tool call is intercepted for user approval, so do not ask for approval in plain text or claim that a notification was sent before the tool succeeds.
If the user approves, the notification will be sent. If the user rejects, analyze again and recommend an alternative company for investment, then call send_push_notification with that recommendation. Try this a maximum of 3 times total. After that, return a message to ask the user to try again after a few hours or the next day when more financial news is available.
"""
class EvaluatorOutput(BaseModel):
    feedback: str = Field(description="Feedback on the assistant's response")
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    user_input_needed: bool= Field(description="True if the assistant has a question, needs clarification, or is stuck and needs the user")

class TolerateToolErrors(AgentMiddleware):
    """Hand tool failures back to the model as a message so it can recover, rather than
    crashing the run. Tools that touch the outside world, like a browser, fail now and then."""

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as error:
            return ToolMessage(
                content=f"The tool call failed: {error}. Try another approach.",
                tool_call_id=request.tool_call["id"]
            )

class StockSage:
    def __init__(self):
        self.stocksage_id = str(uuid.uuid4())
        self.memory = InMemorySaver()
        self.tools = None
        self.sessions = None
        self.worker = None
        self.company_finder = None
        self.evaluator = None
        self.task = ""
        self.attempts = 0
        self.paused = False
        self.pending_actions = 0
        self.todos = []
        self.task_message = DEFAULT_MESSAGE
        self.success_criteria = DEFAULT_SUCCESS_CRITERIA

    async def setup(self):
        self.tools = await get_all_tools()
        self.worker = create_agent(
            model=f"openai:{MODEL_NAME}",
            tools=self.tools,
            system_prompt=f"{TRENDING_COMPANY_FINDER_PROMPT}\n\n{FINANCIAL_RESEARCHER_PROMPT}, Today is {datetime.now():%A %d %B %Y}.",
            middleware=[
                TolerateToolErrors(),
                TodoListMiddleware(),
                PIIMiddleware("email"),
                PIIMiddleware("credit_card", apply_to_tool_results=True),
                ModelCallLimitMiddleware(run_limit=30),
                HumanInTheLoopMiddleware(interrupt_on={"send_push_notification": True, "request_human_help": True}),
            ],
            checkpointer=self.memory
        )
        self.evaluator = ChatOpenAI(model=MODEL_NAME).with_structured_output(EvaluatorOutput)

    async def evaluate(
        self,
        last_reply: str,
        tools_used: list[str],
        message: str,
        success_criteria: str,
    ) -> EvaluatorOutput:
        prompt = f"""You decide whether the analyst has met the success criteria for a task.

                    The request was:
                    {message}

                    The success criteria is:
                    {success_criteria}
                    
                    The tools the analyst called while working, in order:
                    {", ".join(tools_used) or "none"}

                    The analyst's most recent reply was:
                    {last_reply}

                    Decide whether the success criteria are met, using the tool calls as evidence of what was actually done.
                    Also decide whether the analyst needs more input from the user, either because it asked a question,
                    needs clarification, or seems stuck. Give brief, concrete feedback."""
        return await self.evaluator.ainvoke(prompt)

    async def run_turn(self, message: str, success_criteria: str, history: list) -> list:
        """One turn of conversation: the analyst attempts the task and the evaluator checks it,
        retrying with feedback up to MAX_ATTEMPTS. If the analyst pauses for approval, this
        returns straight away with paused set, and resume() continues the same turn."""
        self.attempts = 0
        self.todos = []
        message = message.strip() or DEFAULT_MESSAGE
        success_criteria = success_criteria.strip() or DEFAULT_SUCCESS_CRITERIA
        self.task_message = message
        self.success_criteria = success_criteria
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": f"{message}\n\nThe success criteria for this task are: {success_criteria}",
                }
            ]
        }
        return await self._advance(
            payload,
            history + [{"role": "user", "content": message}],
            self.task_message,
            self.success_criteria,
        )

    async def resume(self, history: list) -> list:
        """Approve the actions the analyst paused on, and continue the turn."""
        payload = Command(resume={"decisions": [{"type": "approve"}] * self.pending_actions})
        history, decision_notice = self._decision_notice(history, "Approved")
        return await self._advance(
            payload, history, self.task_message, self.success_criteria, decision_notice
        )

    async def reject(self, history: list) -> list:
        """Reject the actions the analyst paused on, and continue the turn."""
        payload = Command(resume={"decisions": [{"type": "reject"}] * self.pending_actions})
        history, decision_notice = self._decision_notice(history, "Rejected")
        return await self._advance(
            payload, history, self.task_message, self.success_criteria, decision_notice
        )

    @staticmethod
    def _decision_notice(history: list, decision: str) -> tuple[list, dict | None]:
        approval_prefix = "Waiting for your approval:\n"
        if not history or history[-1].get("role") != "assistant":
            return history, None

        content = history[-1].get("content", "")
        if isinstance(content, str):
            approval_text = content
        elif isinstance(content, list):
            approval_text = "".join(
                part for part in content if isinstance(part, str)
            )
        else:
            return history, None

        if not approval_text.startswith(approval_prefix):
            return history, None

        notice = {
            "role": "assistant",
            "content": f"{decision}:\n{approval_text[len(approval_prefix):]}",
        }
        return history[:-1], notice

    @staticmethod
    def _approval_conclusion(messages: list, actions: list) -> str:
        action_names = {action["name"] for action in actions}
        for message in reversed(messages):
            tool_calls = getattr(message, "tool_calls", None) or []
            if not action_names.intersection(
                call.get("name") for call in tool_calls
            ):
                continue

            content = message.content
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                text = "\n".join(
                    part if isinstance(part, str) else part.get("text", "")
                    for part in content
                    if isinstance(part, str)
                    or isinstance(part, dict) and isinstance(part.get("text"), str)
                ).strip()
                if text:
                    return text

        recommendation = next(
            (
                action.get("args", {}).get("text")
                for action in actions
                if action.get("name") == "send_push_notification"
                and isinstance(action.get("args", {}).get("text"), str)
            ),
            None,
        )
        if recommendation:
            return f"Research conclusion:\n{recommendation}"
        return ""

    async def _advance(
        self,
        payload,
        history: list,
        message: str,
        success_criteria: str,
        decision_notice: dict | None = None,
    ) -> list:
        config = {"configurable": {"thread_id": self.stocksage_id}}
        while True:
            result = None
            async for result in self.worker.astream(payload, config=config, stream_mode="values"):
                self.todos = result.get("todos", self.todos)

            if "__interrupt__" in result:
                messages = result.get("messages", [])
                actions = result["__interrupt__"][0].value["action_requests"]
                self.paused = True
                self.pending_actions = len(actions)
                described = "\n".join(action["description"] for action in actions)
                pending = {"role": "assistant", "content": f"Waiting for your approval:\n{described}"}
                conclusion = self._approval_conclusion(messages, actions)
                response = [
                    {"role": "assistant", "content": conclusion},
                    pending,
                ] if conclusion else [pending]
                return history + ([decision_notice] if decision_notice else []) + response

            self.paused = False
            reply = result["messages"][-1].content
            tools_used = [
                call["name"] for m in result["messages"] for call in (getattr(m, "tool_calls", None) or [])
            ]
            self.attempts += 1
            verdict = await self.evaluate(
                reply, tools_used, message, success_criteria
            )
            if verdict.success_criteria_met or verdict.user_input_needed or self.attempts >= MAX_ATTEMPTS:
                completed_history = history + [
                    {"role": "assistant", "content": reply},
                    {"role": "assistant", "content": f"Evaluator: {verdict.feedback}"},
                ]
                if decision_notice:
                    completed_history.append(decision_notice)
                return completed_history
            payload = {
                "messages": [
                    {
                        "role": "assistant",
                        "content": f"Your last response did not meet the success criteria. "
                        f"Here is the feedback: {verdict.feedback}. Please keep working and address it.",
                    }
                ]
            }
