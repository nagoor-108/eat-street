"""
AI Chat Routes — Kakinada Eat Street
Uses Ollama streaming via SSE (Server-Sent Events) so:
  - Browser receives tokens progressively
  - No more ConnectionResetError [WinError 10054]
  - Works with llama3, llama3.2, mistral, gemma — any installed model
"""
from flask import Blueprint, request, jsonify, session, current_app, Response, stream_with_context
from ollama_rag import stream_ollama, build_context, chat_with_ollama
import json

ai_chat_bp = Blueprint('ai_chat', __name__)

# Module-level cache (per-process)
_histories: dict = {}
_rag_context: str = ""


def get_context(app):
    """Return cached RAG context, building it if needed."""
    global _rag_context
    if not _rag_context:
        _rag_context = build_context(app)
    return _rag_context


# ─── STREAMING CHAT ENDPOINT ──────────────────────────────────────────────────
@ai_chat_bp.route('/stream', methods=['POST'])
def chat_stream():
    """
    SSE streaming endpoint — yields tokens as they arrive from Ollama.
    Frontend reads this as a ReadableStream to show typing effect.
    """
    data    = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    lang    = data.get('lang', 'en')
    sid     = session.get('_id', 'anon')

    if not message:
        return jsonify({'error': 'Empty message'}), 400

    app     = current_app._get_current_object()
    context = get_context(app)
    history = _histories.get(sid, [])

    def generate():
        full_reply = []
        try:
            for token in stream_ollama(message, context, history, lang=lang):
                full_reply.append(token)
                # SSE format: "data: <json>\n\n"
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {str(e)}'})}\n\n"
        finally:
            # Save to history after streaming completes
            reply_text = "".join(full_reply).strip()
            if reply_text:
                history.append({'role': 'user',      'content': message})
                history.append({'role': 'assistant',  'content': reply_text})
                _histories[sid] = history[-12:]
            # Signal stream end
            yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':   'no-cache',
            'X-Accel-Buffering': 'no',   # disable nginx buffering if present
        }
    )


# ─── NON-STREAMING FALLBACK ───────────────────────────────────────────────────
@ai_chat_bp.route('/chat', methods=['POST'])
def chat():
    """
    Non-streaming JSON endpoint (fallback).
    Uses threaded Flask so the 30-60s wait doesn't block other requests.
    """
    data    = request.get_json(silent=True) or {}
    message = data.get('message', '').strip()
    lang    = data.get('lang', 'en')
    sid     = session.get('_id', 'anon')

    if not message:
        return jsonify({'reply': 'Please type something!'}), 400

    app     = current_app._get_current_object()
    context = get_context(app)
    history = _histories.get(sid, [])

    reply = chat_with_ollama(message, context, history, lang=lang)

    history.append({'role': 'user',      'content': message})
    history.append({'role': 'assistant', 'content': reply})
    _histories[sid] = history[-12:]

    return jsonify({'reply': reply})


# ─── CLEAR HISTORY ────────────────────────────────────────────────────────────
@ai_chat_bp.route('/clear', methods=['POST'])
def clear_history():
    global _rag_context
    sid = session.get('_id', 'anon')
    _histories.pop(sid, None)
    _rag_context = ""   # force fresh context rebuild
    return jsonify({'success': True})


# ─── SUGGESTIONS ─────────────────────────────────────────────────────────────
SUGGESTIONS_BY_LANG = {
    'en': [
        "🍗 What chicken dishes are available?",
        "🥦 Show veg food under Rs.100",
        "🍽️ Which shops have dine-in?",
        "🍢 I want BBQ food",
        "🔥 What's popular at Eat Street?",
        "💰 Show food under Rs.50",
        "🥟 Any momos available?",
        "⭐ Best rated shops",
    ],
    'te': [
        "🍗 చికెన్ వంటకాలు ఏమున్నాయి?",
        "🥦 ₹100 లోపు వెజ్ ఫుడ్ చూపించు",
        "🍽️ డైన్-ఇన్ ఉన్న షాపులు ఏవి?",
        "🍢 నాకు BBQ ఫుడ్ కావాలి",
        "🔥 ఈట్ స్ట్రీట్‌లో పాపులర్ ఏమిటి?",
        "💰 ₹50 లోపు ఫుడ్ ఐటమ్స్",
        "🥟 మోమోస్ అందుబాటులో ఉన్నాయా?",
        "⭐ బెస్ట్ రేటెడ్ షాపులు",
    ],
    'teluglish': [
        "🍗 Chicken dishes emunnayi?",
        "🥦 Rs.100 lopala veg items chupinchu",
        "🍽️ Dine-in unna shops evi?",
        "🍢 Naku BBQ food kavali",
        "🔥 Eat Street lo popular items enti?",
        "💰 Rs.50 lopu snacks items",
        "🥟 Momos dorukutaya?",
        "⭐ Best rated shops evi?",
    ],
    'hi': [
        "🍗 कौन से चिकन व्यंजन उपलब्ध हैं?",
        "🥦 ₹100 के अंदर शाकाहारी भोजन दिखाओ",
        "🍽️ डाइन-इन वाली दुकानें कौन सी हैं?",
        "🍢 मुझे बारबेक्यू खाना चाहिए",
        "🔥 ईट स्ट्रीट में क्या प्रसिद्ध है?",
        "💰 ₹50 के अंदर खाना दिखाओ",
        "🥟 क्या मोमोज उपलब्ध हैं?",
        "⭐ बेस्ट रेटेड दुकानें",
    ]
}

@ai_chat_bp.route('/suggestions')
def suggestions():
    lang = request.args.get('lang', 'en')
    return jsonify(SUGGESTIONS_BY_LANG.get(lang, SUGGESTIONS_BY_LANG['en']))


# ─── STATUS / HEALTH CHECK ────────────────────────────────────────────────────
@ai_chat_bp.route('/status')
def status():
    """Check Ollama availability and list installed models."""
    import requests as req
    from config import Config
    try:
        r      = req.get(f"{Config.OLLAMA_URL}/api/tags", timeout=4)
        models = [m['name'] for m in r.json().get('models', [])]
        return jsonify({'online': True, 'models': models, 'using': Config.OLLAMA_MODEL})
    except Exception as e:
        return jsonify({'online': False, 'error': str(e)})
