import os
from dotenv import load_dotenv

import requests
from langchain_community.tools import GoogleSerperRun
from langchain_core.tools import tool
from langchain_community.utilities import GoogleSerperAPIWrapper

load_dotenv(override=True)

search = GoogleSerperRun(api_wrapper=GoogleSerperAPIWrapper())

@tool
def send_push_notification(text: str) -> str:
    """ Send a short notification to the users phone """
    response = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": os.getenv("PUSHOVER_TOKEN"), "user": os.getenv("PUSHOVER_USER"), "message": text},
    )
    response.raise_for_status()
    return "Notification sent successfully"

@tool
def request_human_help(instructions: str) -> str:
    """Ask the user to do something in the browser window that you cannot do yourself,
    such as logging in to a site, passing a captcha, or approving two-factor authentication.
    Explain exactly what you need them to do. The run pauses until they have done it."""
    return "The user says it is done. Continue with the task."

async def get_all_tools():
    """Return the full tool list (our tools plus the MCP server tools) and the session holder."""
    our_tools = [search, send_push_notification, request_human_help]
    return our_tools