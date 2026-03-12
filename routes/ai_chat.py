import json
from flask import Blueprint, render_template, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from ai_tools import TOOL_DEFINITIONS, execute_tool
from models import db, ChatMessage, ChatConversation

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/')
@login_required
def chat_page():
    has_key = bool(current_user.ai_api_key)

    # Get or create active conversation
    conv_id = request.args.get('conv')
    conversations = ChatConversation.query.filter_by(user_id=current_user.id)\
        .order_by(ChatConversation.created_at.desc()).all()

    if conv_id:
        active_conv = ChatConversation.query.filter_by(
            id=conv_id, user_id=current_user.id).first()
    elif conversations:
        active_conv = conversations[0]
    else:
        active_conv = None

    messages = []
    if active_conv:
        messages = ChatMessage.query.filter_by(
            user_id=current_user.id, conversation_id=active_conv.id
        ).order_by(ChatMessage.created_at.asc()).all()

    return render_template('chat.html',
        has_api_key=has_key,
        messages=messages,
        conversations=conversations,
        active_conv=active_conv)


@ai_bp.route('/new-conversation', methods=['POST'])
@login_required
def new_conversation():
    conv = ChatConversation(user_id=current_user.id, title='New Chat')
    db.session.add(conv)
    db.session.commit()
    return jsonify({'id': conv.id})


@ai_bp.route('/rename-conversation/<int:conv_id>', methods=['POST'])
@login_required
def rename_conversation(conv_id):
    conv = ChatConversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    conv.title = data.get('title', 'New Chat')[:200]
    db.session.commit()
    return jsonify({'ok': True})


@ai_bp.route('/delete-conversation/<int:conv_id>', methods=['POST'])
@login_required
def delete_conversation(conv_id):
    conv = ChatConversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    db.session.delete(conv)
    db.session.commit()
    return jsonify({'ok': True})


def _get_system_prompt(user_tz=None):
    from app import user_today
    today = user_today(user_tz).isoformat()
    return (
        "You are a knowledgeable, conversational health and fitness coach. You have access to the "
        "user's health tracking data through tools. You are collaborative and thorough.\n\n"
        f"TODAY'S DATE: {today}. All date-based tools default to this date. If the user refers to "
        "'today', 'yesterday', or other relative dates, calculate the correct YYYY-MM-DD date "
        "based on this reference point and pass it explicitly to the tool.\n\n"
        "IMPORTANT BEHAVIOR - ASK QUESTIONS FIRST:\n"
        "- Before creating any plan (meal, workout, etc.), ask clarifying questions to understand "
        "the user's needs. Ask about their experience level, preferences, available equipment, "
        "schedule, injuries, dietary restrictions, etc.\n"
        "- Don't assume — gather information first, then build the plan.\n"
        "- If the user gives a vague request like 'make me a workout plan', ask 2-3 focused "
        "questions before generating one. For example: fitness level, how many days per week, "
        "available equipment, any injuries to work around.\n"
        "- Use get_user_goals at the start of conversations to understand the user's context.\n\n"
        "GOALS MANAGEMENT:\n"
        "- The user has a goals profile you can read with get_user_goals and update with "
        "update_user_goals.\n"
        "- If through conversation you discover the user's goals have changed (e.g., they want "
        "to shift from weight loss to muscle gain, or change their calorie target), ASK the user: "
        "'It sounds like your goals have shifted — would you like me to update your profile to "
        "reflect that?'\n"
        "- Only update goals after the user confirms.\n\n"
        "EXERCISE VIDEOS:\n"
        "- When using the find_exercise_video tool, search YouTube for a high-quality tutorial "
        "video and return the URL.\n\n"
        "GENERAL:\n"
        "- When the user asks about their progress, USE the appropriate tools to fetch actual data.\n"
        "- When looking up food nutrition, provide detailed macro breakdowns.\n"
        "- When creating plans, be specific with portions, exercises, sets, and reps.\n"
        "- When the user confirms a training plan, use save_training_plan to save it.\n"
        "- When you generate a meal plan, IMMEDIATELY save it using save_meal_plan — do NOT wait "
        "for the user to confirm. Include estimated macros (calories, protein, carbs, fat) for each "
        "meal. The user can view and modify it on the Meal Plan page. If they want changes, update "
        "and re-save it.\n"
        "- When the user asks about their current meal plan, or wants to modify it, use get_meal_plan "
        "first to see what they currently have before making changes.\n"
        "- Be encouraging but honest. Base recommendations on evidence-based health practices."
    )


@ai_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    if not current_user.ai_api_key:
        return jsonify({'error': 'Please set your AI API key in Settings first.'}), 400

    data = request.get_json()
    user_message = data.get('message', '').strip()
    conv_id = data.get('conversation_id')
    no_save = data.get('no_save', False)

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    # If no_save, do a quick AI call without creating conversation/messages
    if no_save:
        system_prompt = _get_system_prompt(current_user.tz)
        messages = [{"role": "user", "content": user_message}]
        provider = current_user.ai_provider or 'claude'
        try:
            if provider == 'claude':
                response_data = _call_claude(current_user.ai_api_key, system_prompt, messages)
            else:
                response_data = _call_openai(current_user.ai_api_key, system_prompt, messages)
            return jsonify(response_data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # Get or create conversation
    if conv_id:
        conv = ChatConversation.query.filter_by(
            id=conv_id, user_id=current_user.id).first()
    else:
        conv = None

    if not conv:
        conv = ChatConversation(user_id=current_user.id, title='New Chat')
        db.session.add(conv)
        db.session.commit()

    # Save user message
    user_msg = ChatMessage(
        user_id=current_user.id, conversation_id=conv.id,
        role='user', content=user_message)
    db.session.add(user_msg)
    db.session.commit()

    # Auto-title: use first user message as title if still "New Chat"
    if conv.title == 'New Chat':
        conv.title = user_message[:80] + ('...' if len(user_message) > 80 else '')
        db.session.commit()

    # Load conversation history (last 50 messages for this conversation)
    db_messages = ChatMessage.query.filter_by(
        user_id=current_user.id, conversation_id=conv.id
    ).order_by(ChatMessage.created_at.desc()).limit(50).all()
    db_messages.reverse()

    system_prompt = _get_system_prompt(current_user.tz)
    messages = [{"role": m.role, "content": m.content} for m in db_messages]
    provider = current_user.ai_provider or 'claude'

    try:
        if provider == 'claude':
            response_data = _call_claude(current_user.ai_api_key, system_prompt, messages)
        else:
            response_data = _call_openai(current_user.ai_api_key, system_prompt, messages)

        assistant_msg = ChatMessage(
            user_id=current_user.id, conversation_id=conv.id,
            role='assistant', content=response_data['reply'])
        db.session.add(assistant_msg)
        db.session.commit()

        response_data['conversation_id'] = conv.id
        return jsonify(response_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ai_bp.route('/stream', methods=['POST'])
@login_required
def stream_message():
    """SSE streaming endpoint for AI chat."""
    if not current_user.ai_api_key:
        return jsonify({'error': 'Please set your AI API key in Settings first.'}), 400

    data = request.get_json()
    user_message = data.get('message', '').strip()
    conv_id = data.get('conversation_id')

    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    # Get or create conversation
    if conv_id:
        conv = ChatConversation.query.filter_by(
            id=conv_id, user_id=current_user.id).first()
    else:
        conv = None

    if not conv:
        conv = ChatConversation(user_id=current_user.id, title='New Chat')
        db.session.add(conv)
        db.session.commit()

    user_msg = ChatMessage(
        user_id=current_user.id, conversation_id=conv.id,
        role='user', content=user_message)
    db.session.add(user_msg)
    db.session.commit()

    if conv.title == 'New Chat':
        conv.title = user_message[:80] + ('...' if len(user_message) > 80 else '')
        db.session.commit()

    db_messages = ChatMessage.query.filter_by(
        user_id=current_user.id, conversation_id=conv.id
    ).order_by(ChatMessage.created_at.desc()).limit(50).all()
    db_messages.reverse()

    system_prompt = _get_system_prompt(current_user.tz)
    messages = [{"role": m.role, "content": m.content} for m in db_messages]
    provider = current_user.ai_provider or 'claude'

    user_id = current_user.id
    api_key = current_user.ai_api_key

    def generate():
        try:
            if provider == 'claude':
                full_reply = yield from _stream_claude(
                    api_key, system_prompt, messages, user_id)
            else:
                full_reply = yield from _stream_openai(
                    api_key, system_prompt, messages, user_id)

            # Save complete reply
            assistant_msg = ChatMessage(
                user_id=user_id, conversation_id=conv.id,
                role='assistant', content=full_reply)
            db.session.add(assistant_msg)
            db.session.commit()

            yield f"data: {json.dumps({'done': True, 'conversation_id': conv.id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@ai_bp.route('/clear', methods=['POST'])
@login_required
def clear_chat():
    conv_id = request.get_json().get('conversation_id') if request.is_json else None
    if conv_id:
        ChatMessage.query.filter_by(
            user_id=current_user.id, conversation_id=conv_id).delete()
    else:
        ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'ok': True})


def _stream_claude(api_key, system_prompt, messages, user_id):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    tools = [{"name": t["name"], "description": t["description"],
              "input_schema": t["input_schema"]} for t in TOOL_DEFINITIONS]

    full_text = ""

    while True:
        current_text = ""

        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            system=system_prompt,
            tools=tools,
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, 'text'):
                        current_text += event.delta.text
                        yield f"data: {json.dumps({'text': event.delta.text})}\n\n"

        response = stream.get_final_message()

        if response.stop_reason != "tool_use":
            full_text = current_text
            break

        # Handle tool use
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                yield f"data: {json.dumps({'status': f'Using tool: {block.name}...'})}\n\n"
                result = execute_tool(block.name, block.input, user_id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return full_text


def _stream_openai(api_key, system_prompt, messages, user_id):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    tools = [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["input_schema"]}} for t in TOOL_DEFINITIONS]

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append({"role": msg["role"], "content": msg["content"]})

    full_text = ""

    while True:
        collected_text = ""
        tool_calls_map = {}

        stream = client.chat.completions.create(
            model="gpt-4o",
            messages=oai_messages,
            tools=tools,
            max_tokens=16384,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                collected_text += delta.content
                yield f"data: {json.dumps({'text': delta.content})}\n\n"

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "arguments": ""
                        }
                    if tc.id:
                        tool_calls_map[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        tool_calls_map[idx]["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        tool_calls_map[idx]["arguments"] += tc.function.arguments

        finish_reason = chunk.choices[0].finish_reason if chunk.choices else None

        if not tool_calls_map:
            full_text = collected_text
            break

        # Handle tool calls
        assistant_msg = {"role": "assistant", "content": collected_text or None, "tool_calls": []}
        for idx in sorted(tool_calls_map.keys()):
            tc_data = tool_calls_map[idx]
            assistant_msg["tool_calls"].append({
                "id": tc_data["id"],
                "type": "function",
                "function": {"name": tc_data["name"], "arguments": tc_data["arguments"]}
            })
        oai_messages.append(assistant_msg)

        for idx in sorted(tool_calls_map.keys()):
            tc_data = tool_calls_map[idx]
            tool_name = tc_data["name"]
            yield f"data: {json.dumps({'status': f'Using tool: {tool_name}...'})}\n\n"
            args = json.loads(tc_data["arguments"])
            result = execute_tool(tc_data["name"], args, user_id)
            oai_messages.append({
                "role": "tool",
                "tool_call_id": tc_data["id"],
                "content": result,
            })

    return full_text


def _call_claude(api_key, system_prompt, messages):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    tools = [{"name": t["name"], "description": t["description"],
              "input_schema": t["input_schema"]} for t in TOOL_DEFINITIONS]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=16384,
        system=system_prompt,
        tools=tools,
        messages=messages,
    )

    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input, current_user.id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16384,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

    text_parts = [block.text for block in response.content if hasattr(block, 'text')]
    return {"reply": "\n".join(text_parts)}


def _call_openai(api_key, system_prompt, messages):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    tools = [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["input_schema"]}} for t in TOOL_DEFINITIONS]

    oai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        oai_messages.append({"role": msg["role"], "content": msg["content"]})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=oai_messages,
        tools=tools,
        max_tokens=16384,
    )

    msg = response.choices[0].message

    while msg.tool_calls:
        oai_messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args, current_user.id)
            oai_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=oai_messages,
            tools=tools,
            max_tokens=16384,
        )
        msg = response.choices[0].message

    return {"reply": msg.content}
