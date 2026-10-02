/* ═══════════════════════════════════════════════════════════════════════
   KAKINADA EAT STREET — AI Chat (Streaming via SSE)
   Uses /ai/stream endpoint — tokens arrive progressively, no timeouts
   ═══════════════════════════════════════════════════════════════════════ */

let chatOpen = false;
let isStreaming = false;
let currentChatLang = localStorage.getItem('eatstreet_chat_lang') || 'te';

const LANG_TEXTS = {
  te: {
    name: "తెలుగు",
    flag: "🇮🇳",
    welcome: "నమస్కారం! నేను మీ కాకినాడ ఈట్ స్ట్రీట్ AI సహాయకుడిని. ఫుడ్, షాపులు, ధరలు, ఆర్డర్లు లేదా టేబుల్ బుకింగ్స్ గురించి నన్ను ఏదైనా అడగండి!",
    placeholder: "ఫుడ్, ధరలు, షాపుల గురించి తెలుగులో అడగండి…",
    switchNotice: "✅ **తెలుగు భాష ఎంచుకోబడింది!** నేను మీకు కాకినాడ ఈట్ స్ట్రీట్ ఫుడ్ & షాపుల వివరాలలో ఎలా సహాయపడగలను?",
  },
  en: {
    name: "English",
    flag: "🇬🇧",
    welcome: "Hi! I'm your Kakinada Eat Street AI assistant. Ask me anything about food, shops, prices, orders, or table bookings!",
    placeholder: "Ask about food, prices, shops in English…",
    switchNotice: "✅ **English language selected!** How can I assist you with Kakinada Eat Street food and stalls today?",
  },
  hi: {
    name: "हिंदी",
    flag: "🇮🇳",
    welcome: "नमस्ते! मैं आपका काकीनाडा ईट स्ट्रीट AI सहायक हूँ। भोजन, दुकानों, कीमतों, ऑर्डर या टेबल बुकिंग के बारे में कुछ भी पूछें!",
    placeholder: "भोजन, कीमतों, दुकानों के बारे में हिंदी में पूछें…",
    switchNotice: "✅ **हिंदी भाषा चुनी गई!** मैं आपकी काकीनाडा ईट स्ट्रीट के मेनू और दुकानों के बारे में कैसे मदद करूँ?",
  }
};

function renderWelcomeScreen() {
  const messages = document.getElementById('chatMessages');
  if (!messages) return;

  const current = LANG_TEXTS[currentChatLang] || LANG_TEXTS.te;

  messages.innerHTML = `
    <div class="chat-msg bot" style="max-width:96%;background:var(--bg-elevated);border:1px solid var(--border);border-radius:12px;padding:0.85rem">
      <div style="font-weight:700;font-size:0.92rem;color:#fff;margin-bottom:0.25rem">
        👋 Welcome to EatStreet AI!
      </div>
      <div style="font-size:0.75rem;color:var(--text-muted);margin-bottom:0.6rem">
        Choose language / భాషను ఎంచుకోండి / भाषा चुनें:
      </div>
      <div class="chat-lang-chips-grid">
        <button type="button" class="chat-lang-chip ${currentChatLang==='en'?'active':''}" onclick="changeChatLang('en', true)">
          <span style="font-size:1.1rem">🇬🇧</span>
          <span><strong>English</strong></span>
        </button>
        <button type="button" class="chat-lang-chip ${currentChatLang==='te'?'active':''}" onclick="changeChatLang('te', true)">
          <span style="font-size:1.1rem">🇮🇳</span>
          <span><strong>తెలుగు</strong></span>
        </button>
        <button type="button" class="chat-lang-chip ${currentChatLang==='hi'?'active':''}" onclick="changeChatLang('hi', true)">
          <span style="font-size:1.1rem">🇮🇳</span>
          <span><strong>हिंदी</strong></span>
        </button>
      </div>
      <div style="font-size:0.8rem;color:rgba(255,255,255,0.9);line-height:1.4;margin-top:0.6rem;padding-top:0.5rem;border-top:1px solid var(--border)">
        ${current.welcome}
      </div>
    </div>
  `;
}

function updateLangTabUI(lang) {
  document.querySelectorAll('.chat-lang-tab').forEach(tab => {
    if (tab.dataset.lang === lang) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  const current = LANG_TEXTS[lang] || LANG_TEXTS.te;
  const input = document.getElementById('chatInput');
  if (input) {
    input.placeholder = current.placeholder;
  }
}

function changeChatLang(lang, fromClick = false) {
  if (!LANG_TEXTS[lang]) lang = 'te';
  currentChatLang = lang;

  try {
    localStorage.setItem('eatstreet_chat_lang', lang);
  } catch (_) {}

  updateLangTabUI(lang);
  loadSuggestions();

  const messages = document.getElementById('chatMessages');
  if (messages) {
    const userMsgs = messages.querySelectorAll('.chat-msg.user');
    if (userMsgs.length === 0) {
      // Re-render initial welcome card with active highlight
      renderWelcomeScreen();
    } else if (fromClick) {
      // Append language switch notification
      const notice = LANG_TEXTS[lang].switchNotice;
      appendMessage(notice, 'bot');
    }
    messages.scrollTop = messages.scrollHeight;
  }

  const input = document.getElementById('chatInput');
  if (input) {
    input.focus();
  }
}
window.changeChatLang = changeChatLang;
window.onChatLangChange = changeChatLang;

// ─── TOGGLE CHAT WINDOW ───────────────────────────────────────────────────
function toggleChat() {
  chatOpen = !chatOpen;
  const win = document.getElementById('chatWindow');
  const fab = document.getElementById('chatFab');
  if (!win) return;

  if (chatOpen) {
    win.classList.add('open');
    if (fab) fab.innerHTML = '<i class="ri-close-line"></i>';
    
    updateLangTabUI(currentChatLang);
    const messages = document.getElementById('chatMessages');
    if (messages && messages.children.length === 0) {
      renderWelcomeScreen();
    }
    loadSuggestions();

    setTimeout(() => {
      const inp = document.getElementById('chatInput');
      if (inp) inp.focus();
    }, 300);
  } else {
    win.classList.remove('open');
    if (fab) fab.innerHTML = '<i class="ri-sparkling-2-line"></i>';
  }
}

// ─── LOAD QUICK SUGGESTIONS ───────────────────────────────────────────────
function loadSuggestions() {
  fetch(`/ai/suggestions?lang=${encodeURIComponent(currentChatLang)}`)
    .then(r => r.json())
    .then(list => {
      const container = document.getElementById('chatSuggestions');
      if (!container) return;
      container.style.display = 'flex';
      container.innerHTML = list.slice(0, 4)
        .map(s => `<button class="chat-suggestion-btn" onclick="sendSuggestion(this)">${s}</button>`)
        .join('');
    })
    .catch(() => {});
}

function sendSuggestion(btn) {
  const input = document.getElementById('chatInput');
  if (input) { input.value = btn.textContent; sendChat(); }
}

// ─── MAIN SEND (SSE STREAMING) ────────────────────────────────────────────
async function sendChat() {
  if (isStreaming) return;   // prevent double-send

  const input    = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');
  if (!input || !messages) return;

  const text = input.value.trim();
  if (!text) return;

  input.value    = '';
  input.disabled = true;

  // Hide suggestions while chatting
  const sugg = document.getElementById('chatSuggestions');
  if (sugg) sugg.style.display = 'none';

  // Show user message
  appendMessage(text, 'user');

  // Create bot bubble that we'll stream into
  const botId  = 'bot-msg-' + Date.now();
  const botDiv = createBotBubble(botId);
  messages.appendChild(botDiv);
  messages.scrollTop = messages.scrollHeight;

  isStreaming = true;
  let fullReply = '';

  try {
    // POST the message, then read SSE stream back
    const resp = await fetch('/ai/stream', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: text, lang: currentChatLang }),
    });

    if (!resp.ok) {
      throw new Error(`Server error ${resp.status}`);
    }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();  // keep incomplete last line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;

        try {
          const payload = JSON.parse(trimmed.slice(5).trim());

          if (payload.done) break;

          if (payload.token) {
            fullReply += payload.token;
            // Render token into the bot bubble
            const bubble = document.getElementById(botId);
            if (bubble) {
              bubble.innerHTML = formatChatText(fullReply);
              // Keep cursor-style blinking while streaming
              bubble.innerHTML += '<span class="typing-cursor">▌</span>';
            }
            messages.scrollTop = messages.scrollHeight;
          }

        } catch (_) {}
      }
    }

    // Remove blinking cursor and finalize
    const bubble = document.getElementById(botId);
    if (bubble) bubble.innerHTML = formatChatText(fullReply || "I'm here to help!");

  } catch (err) {
    const bubble = document.getElementById(botId);
    if (bubble) {
      // Show a helpful error message based on the error type
      if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
        bubble.innerHTML = '⚠️ Cannot reach the server. Please refresh the page and try again.';
      } else {
        bubble.innerHTML = `⚠️ ${err.message || 'Connection error. Please try again.'}`;
      }
    }
  } finally {
    isStreaming    = false;
    input.disabled = false;
    input.focus();
    messages.scrollTop = messages.scrollHeight;
    const sugg = document.getElementById('chatSuggestions');
    if (sugg) {
      sugg.style.display = 'flex';
      loadSuggestions();
    }
  }
}

// ─── CREATE BOT BUBBLE ────────────────────────────────────────────────────
function createBotBubble(id) {
  const div = document.createElement('div');
  div.className = 'chat-msg bot';
  div.id = id;
  div.innerHTML = '<span class="typing-cursor">▌</span>';
  return div;
}

// ─── APPEND USER MESSAGE ──────────────────────────────────────────────────
function appendMessage(text, type) {
  const messages = document.getElementById('chatMessages');
  if (!messages) return;
  const div = document.createElement('div');
  div.className = `chat-msg ${type}`;
  div.innerHTML = formatChatText(text);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

// ─── TEXT FORMATTER ───────────────────────────────────────────────────────
function formatChatText(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/Rs\.(\d+)/g, '<span style="color:var(--primary);font-weight:700">₹$1</span>')
    .replace(/₹(\d+)/g, '<span style="color:var(--primary);font-weight:700">₹$1</span>')
    .replace(/\n/g, '<br>');
}

// ─── KEYBOARD SHORTCUT & INIT ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  updateLangTabUI(currentChatLang);
  const messages = document.getElementById('chatMessages');
  if (messages && messages.children.length === 0) {
    renderWelcomeScreen();
  }

  const input = document.getElementById('chatInput');
  if (input) {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChat();
      }
    });
  }

  // Add blinking cursor CSS
  const style = document.createElement('style');
  style.textContent = `
    .typing-cursor {
      display: inline-block;
      animation: blink 0.7s step-end infinite;
      color: var(--primary);
      font-weight: 700;
    }
    @keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0 } }
  `;
  document.head.appendChild(style);
});
