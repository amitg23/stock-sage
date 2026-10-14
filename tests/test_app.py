import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app


class RenderTodosTests(unittest.TestCase):
    def test_empty_plan_shows_placeholder(self):
        rendered = app.render_todos([])

        self.assertIn("<h3>Plan</h3>", rendered)
        self.assertIn("The StockSage will write its plan here as it works", rendered)

    def test_plan_items_are_rendered_and_escaped(self):
        rendered = app.render_todos(
            [{"status": "in_progress", "content": "<Research & compare>"}]
        )

        self.assertIn('class="in_progress"', rendered)
        self.assertIn("&lt;Research &amp; compare&gt;", rendered)
        self.assertNotIn("<Research & compare>", rendered)


class AppCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_message_shows_approval_controls_when_paused(self):
        sage = SimpleNamespace(
            paused=True,
            run_turn=AsyncMock(return_value=[{"role": "assistant", "content": "Ready"}]),
        )

        result = await app.process_message(sage, "Find a stock", [])

        sage.run_turn.assert_awaited_once_with("Find a stock", "", [])
        self.assertEqual(result[0], [{"role": "assistant", "content": "Ready"}])
        self.assertTrue(result[1]["visible"])
        self.assertTrue(result[2]["visible"])

    async def test_approve_returns_updated_plan(self):
        sage = SimpleNamespace(
            paused=False,
            todos=[{"status": "completed", "content": "Send recommendation"}],
            resume=AsyncMock(return_value=[]),
        )

        result = await app.approve(sage, [])

        self.assertIn("Send recommendation", result[4])
        self.assertFalse(result[1]["visible"])
        self.assertFalse(result[2]["visible"])

    async def test_reject_returns_updated_plan(self):
        sage = SimpleNamespace(
            paused=False,
            todos=[{"status": "in_progress", "content": "Research alternative"}],
            reject=AsyncMock(return_value=[]),
        )

        result = await app.reject(sage, [])

        self.assertIn("Research alternative", result[4])
        self.assertFalse(result[1]["visible"])
        self.assertFalse(result[2]["visible"])

    async def test_reset_creates_fresh_stock_sage_state(self):
        new_sage = SimpleNamespace(setup=AsyncMock())
        with patch("app.StockSage", return_value=new_sage):
            result = await app.reset(None)

        new_sage.setup.assert_awaited_once()
        self.assertEqual(result[0], [])
        self.assertFalse(result[1]["visible"])
        self.assertFalse(result[2]["visible"])
        self.assertIs(result[3], new_sage)


if __name__ == "__main__":
    unittest.main()
