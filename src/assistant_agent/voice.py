"""The voice walkthrough: a Gemini Live session that presents a dossier like a colleague
and answers questions using the ToolBox, capturing feedback as it goes.

Run with `assistant review <repo>`. Requires GEMINI_API_KEY and working mic/speaker.
"""

from __future__ import annotations

import asyncio

from google import genai
from google.genai import types

from . import config
from .contract import Dossier
from .tools import FUNCTION_DECLARATIONS, ToolBox


def _system_instruction(dossier: Dossier) -> str:
    order = dossier.suggested_walkthrough_order or [
        "what changed", "why", "key decisions", "tests", "risks", "open questions"
    ]
    return f"""You are the engineer's trusted colleague. You just finished a task in the \
repo '{dossier.repo}' (branch {dossier.branch or 'main'}) and you're walking them through \
it out loud, the way you would in their office.

Speak naturally and concisely. Open with a one-or-two sentence headline of what you did, \
then walk through these topics in order, pausing for questions after each: \
{', '.join(order)}.

You have tools to fetch real detail — call show_diff, read_file, list_changed_files, or \
show_test_results rather than guessing. When the engineer gives an opinion, asks for a \
change, or flags something, call record_feedback with a crisp summary of it. If they ask \
you to hand the work back, call create_followup_prompt_for_coding_agent. Do not write code \
yourself — your job is to explain, answer, and capture feedback.

Here is the dossier of what you did:
{dossier.model_dump_json(indent=2)}"""


async def _send_mic(session, mic_queue: "asyncio.Queue[bytes]") -> None:
    while True:
        chunk = await mic_queue.get()
        await session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={16000}")
        )


async def _receive(session, speaker, toolbox: ToolBox) -> None:
    while True:
        async for response in session.receive():
            # Audio out.
            data = getattr(response, "data", None)
            if data:
                speaker.play(data)
            else:
                sc = getattr(response, "server_content", None)
                if sc and sc.model_turn:
                    for part in sc.model_turn.parts:
                        if part.inline_data and isinstance(part.inline_data.data, bytes):
                            speaker.play(part.inline_data.data)

            # Tool calls.
            tool_call = getattr(response, "tool_call", None)
            if tool_call:
                responses = []
                for fc in tool_call.function_calls:
                    result = toolbox.dispatch(fc.name, dict(fc.args or {}))
                    responses.append(
                        types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result})
                    )
                await session.send_tool_response(function_responses=responses)


async def run_walkthrough(toolbox: ToolBox) -> None:
    from .audio import Microphone, Speaker  # local import keeps audio libs out of other paths

    client = genai.Client()
    live_config = {
        "response_modalities": ["AUDIO"],
        "system_instruction": _system_instruction(toolbox.dossier),
        "tools": [{"function_declarations": FUNCTION_DECLARATIONS}],
    }

    loop = asyncio.get_running_loop()
    mic_queue: "asyncio.Queue[bytes]" = asyncio.Queue()

    print("Connecting to Gemini Live… speak when you hear the assistant. Ctrl-C to end.")
    async with client.aio.live.connect(model=config.VOICE_MODEL, config=live_config) as session:
        with Microphone(loop, mic_queue), Speaker() as speaker:
            # Nudge the assistant to open the walkthrough without waiting for the user.
            await session.send_client_content(
                turns={"role": "user", "parts": [{"text": "Start the walkthrough now."}]},
                turn_complete=True,
            )
            try:
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(_send_mic(session, mic_queue))
                    tg.create_task(_receive(session, speaker, toolbox))
            except* Exception as eg:  # surface the first real error
                raise eg.exceptions[0]


def review(toolbox: ToolBox) -> None:
    try:
        asyncio.run(run_walkthrough(toolbox))
    except KeyboardInterrupt:
        pass
    finally:
        if toolbox.feedback_items:
            from . import feedback
            fb = feedback.write_feedback(toolbox.repo_path, toolbox.repo_name, toolbox.feedback_items)
            print(f"\nCaptured {len(toolbox.feedback_items)} feedback item(s) → {fb}")
