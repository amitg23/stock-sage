"""Gradio app for the StockSage. Run with: uv run python src/app.py"""

import html

import gradio as gr

import styles
from stock_sage import StockSage

LAUNCH_STYLE = {"theme": styles.THEME, "css": styles.CSS, "head": styles.JS}

HEADER = """
<div id="header">
    <div class="context-label">Your personal stock picker.</div>
    <h1>StockSage</h1>
    <div class="brand-bar"></div>
</div>
"""

def render_todos(todos):
    if not todos:
        items = '<div class="placeholder">The StockSage will write its plan here as it works</div>'
    else:
        items = "<ul>" + "".join(
            f'<li class="{todo["status"]}"><span class="mark"></span>{html.escape(todo["content"])}</li>'
            for todo in todos
        ) + "</ul>"
    return f"<h3>Plan</h3>{items}"


async def setup():
    stock_sage = StockSage()
    await stock_sage.setup()
    return stock_sage, gr.update(interactive=True)


async def process_message(stock_sage, message, history):
    if stock_sage is None:
        return history, gr.update(visible=False), gr.update(visible=False), stock_sage
    results = await stock_sage.run_turn(message, "", history)
    approval_visible = stock_sage.paused
    return (
        results,
        gr.update(visible=approval_visible),
        gr.update(visible=approval_visible),
        stock_sage,
    )


async def process_message_from_go(stock_sage, history):
    await reset(stock_sage)
    return await process_message(stock_sage, "", history)


async def approve(stock_sage, history):
    results = await stock_sage.resume(history)
    approval_visible = stock_sage.paused
    return (
        results,
        gr.update(visible=approval_visible),
        gr.update(visible=approval_visible),
        stock_sage,
        render_todos(stock_sage.todos),
    )

async def reject(stock_sage, history):
    results = await stock_sage.reject(history)
    approval_visible = stock_sage.paused
    return (
        results,
        gr.update(visible=approval_visible),
        gr.update(visible=approval_visible),
        stock_sage,
        render_todos(stock_sage.todos),
    )


def watch_todos(stock_sage):
    """Called by the timer. The timer is the plan panel's only writer: if a long-running
    event owned the panel as an output, Gradio would lock it as pending and live updates
    would not render while the StockSage works."""
    return render_todos(stock_sage.todos) if stock_sage else render_todos([])


async def reset(stock_sage):
    new_stock_sage = StockSage()
    await new_stock_sage.setup()
    return (
        [],
        gr.update(visible=False),
        gr.update(visible=False),
        new_stock_sage,
    )


def free_resources(stock_sage):
    if stock_sage:
        stock_sage.cleanup()


with gr.Blocks(title="StockSage") as ui:
    gr.HTML(HEADER)
    stock_sage = gr.State(delete_callback=free_resources)

    with gr.Row():
        chatbot = gr.Chatbot(label="StockSage", height=650, scale=3, elem_id="chat")
        with gr.Column(scale=1):
            todos_panel = gr.HTML(render_todos([]), elem_id="plan-panel")
    with gr.Row():
        reset_button = gr.Button("Reset", elem_id="reset-button")
        approve_button = gr.Button("Approve", visible=False, elem_id="approve-button")
        reject_button = gr.Button("Reject", visible=False, elem_id="reject-button")
        go_button = gr.Button("Go!", elem_id="go-button", interactive=False)
    gr.Markdown(
        "*Prototype only. StockSage is not a real-time trading advisory service. "
        "Do not use its output as a trading recommendation or as a substitute "
        "for independent financial advice.*",
        elem_id="disclaimer",
    )

    timer = gr.Timer(1)

    ui.load(setup, [], [stock_sage, go_button])
    timer.tick(watch_todos, [stock_sage], [todos_panel], show_progress="hidden")
    process_outputs = [chatbot, approve_button, reject_button, stock_sage]
    go_button.click(
        process_message_from_go,
        [stock_sage, chatbot],
        process_outputs,
        show_progress_on=chatbot,
    )
    approve_button.click(
        approve,
        [stock_sage, chatbot],
        [*process_outputs, todos_panel],
        show_progress_on=chatbot,
    )
    reject_button.click(
        reject,
        [stock_sage, chatbot],
        [*process_outputs, todos_panel],
        show_progress_on=chatbot,
    )
    reset_button.click(reset, [stock_sage], process_outputs)


if __name__ == "__main__":
    ui.launch(inbrowser=True, **LAUNCH_STYLE)