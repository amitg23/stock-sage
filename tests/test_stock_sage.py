import unittest
from types import SimpleNamespace

from stock_sage import EvaluatorOutput, StockSage


class ApprovalMessageTests(unittest.TestCase):
    def test_decision_notice_replaces_approval_message(self):
        history = [
            {"role": "user", "content": "Find a stock"},
            {
                "role": "assistant",
                "content": "Waiting for your approval:\nSend the recommendation",
            },
        ]

        remaining, notice = StockSage._decision_notice(history, "Approved")

        self.assertEqual(remaining, history[:1])
        self.assertEqual(
            notice,
            {"role": "assistant", "content": "Approved:\nSend the recommendation"},
        )

    def test_decision_notice_handles_list_content(self):
        history = [
            {
                "role": "assistant",
                "content": ["Waiting for your approval:\n", "Send the recommendation"],
            }
        ]

        remaining, notice = StockSage._decision_notice(history, "Rejected")

        self.assertEqual(remaining, [])
        self.assertEqual(
            notice,
            {"role": "assistant", "content": "Rejected:\nSend the recommendation"},
        )

    def test_non_approval_message_is_unchanged(self):
        history = [{"role": "assistant", "content": ["An ordinary response"]}]

        remaining, notice = StockSage._decision_notice(history, "Rejected")

        self.assertIs(remaining, history)
        self.assertIsNone(notice)

    def test_approval_conclusion_uses_tool_message_text(self):
        conclusion = "Acme is the top pick; its key risk is cyclicality."
        messages = [
            SimpleNamespace(
                content=conclusion,
                tool_calls=[{"name": "send_push_notification"}],
            )
        ]
        actions = [
            {
                "name": "send_push_notification",
                "args": {"text": "Acme is the top pick"},
            }
        ]

        self.assertEqual(
            StockSage._approval_conclusion(messages, actions), conclusion
        )

    def test_approval_conclusion_falls_back_to_notification_text(self):
        recommendation = "Acme is the top pick."
        messages = [
            SimpleNamespace(
                content="",
                tool_calls=[{"name": "send_push_notification"}],
            )
        ]
        actions = [
            {
                "name": "send_push_notification",
                "args": {"text": recommendation},
            }
        ]

        self.assertEqual(
            StockSage._approval_conclusion(messages, actions),
            f"Research conclusion:\n{recommendation}",
        )


class AgentAdvanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_shows_conclusion_before_approval_prompt(self):
        conclusion = "Acme is the top pick because of strong growth."
        action = {
            "name": "send_push_notification",
            "args": {"text": "Acme is the top pick"},
            "description": "Send recommendation",
        }
        interrupt = SimpleNamespace(value={"action_requests": [action]})
        snapshot = {
            "__interrupt__": [interrupt],
            "messages": [
                SimpleNamespace(
                    content=conclusion,
                    tool_calls=[{"name": "send_push_notification"}],
                )
            ],
            "todos": [{"status": "completed", "content": "Research companies"}],
        }

        class Worker:
            async def astream(self, payload, config, stream_mode):
                yield snapshot

        sage = StockSage()
        sage.worker = Worker()
        history = [{"role": "user", "content": "Find a stock"}]

        result = await sage._advance({}, history, "Find a stock", "Pick a company")

        self.assertEqual(
            [item["content"] for item in result if item["role"] == "assistant"],
            [
                conclusion,
                "Waiting for your approval:\nSend recommendation",
            ],
        )
        self.assertTrue(sage.paused)
        self.assertEqual(sage.pending_actions, 1)
        self.assertEqual(sage.todos, snapshot["todos"])

    async def test_successful_completion_appends_reply_and_verdict(self):
        reply = "Acme is the recommended investment."
        snapshot = {
            "messages": [
                SimpleNamespace(content=reply, tool_calls=[]),
            ],
            "todos": [],
        }

        class Worker:
            async def astream(self, payload, config, stream_mode):
                yield snapshot

        class Evaluator:
            async def ainvoke(self, prompt):
                return EvaluatorOutput(
                    feedback="The recommendation meets the criteria.",
                    success_criteria_met=True,
                    user_input_needed=False,
                )

        sage = StockSage()
        sage.worker = Worker()
        sage.evaluator = Evaluator()

        result = await sage._advance(
            {}, [{"role": "user", "content": "Find a stock"}], "Find a stock", "Pick one"
        )

        self.assertEqual(
            [item["content"] for item in result if item["role"] == "assistant"],
            [reply, "Evaluator: The recommendation meets the criteria."],
        )
        self.assertFalse(sage.paused)
        self.assertEqual(sage.attempts, 1)


if __name__ == "__main__":
    unittest.main()
