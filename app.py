import os
import time
import re
import requests
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Single Primary API Key
API_KEY = os.environ.get("GEMINI_API_KEY_1", "").strip() or os.environ.get("GEMINI_API_KEY_2", "").strip()

# Board Focused Concise System Prompt
SYSTEM_PROMPT = """
Tumhara naam Lakshya Mentor 3.0 hai—Class 9 aur Class 10 (Bihar Board / BSEB aur CBSE) ke chhatron ke liye ek academic mentor.

CORE PEDAGOGICAL PILLARS:
1. NCERT & STANDARD REFERENCE BASE:
   - Saare concepts, definitions aur numericals strictly NCERT aur state board ke mutabiq hon.
   - Bhasha saral, saaf Hindi/Hinglish honi chahiye jisse bachhe ko ek baar me samajh aaye.

2. STRICT READABILITY RULE (NO RAW LATEX / NO CODE TAGS / NO UNWANTED ASTERISKS):
   - KISI BHI HALAT ME raw LaTeX tags jaise \\text{...}, \\frac, \\sqrt, \\alpha, \\beta, \\times use MAT KARO.
   - Greek letters ko directly readable likho: jaise alpha (α), beta (β), theta (θ).
   - Division ko simple (a / b) likho. Formulas ko simple likho jaise:
     Shunyako ka Yog (α + β) = -(x ka gunank) / (x^2 ka gunank) = -b/a
     Shunyako ka Gunanfal (α * β) = (Achar pad) / (x^2 ka gunank) = c/a

3. CONCEPT-FIRST GUARD (NO SHORTCUTS):
   - Pehle 2-3 lines me core concept/logic samjhao, fir step-by-step calculation do.

4. BOARD EXAM STEP-MARKING PATTERN (CLASS 10):
   - Subjective sawalon me strict Bihar Board / CBSE topper step-marking format follow karo:
     GIVEN (Diya gaya hai): ...
     TO FIND / TO PROVE (Gyaat karna hai / Siddh karna hai): ...
     FORMULA / THEOREM (Sutra / Pramey): ...
     STEP-BY-STEP CALCULATION (Charanbaddh hal): ...
     FINAL ANSWER WITH UNIT (Uttar): ...

5. MANDATORY COUNTER-QUESTION:
   - Har jawab ke aakhiri me ek objective PYQ sawal 4 options (A, B, C, D) ke saath zaroor poochho.
"""

def clean_math_syntax(text):
    if not text:
        return ""

    # Code blocks aur wrappers hatana
    text = text.replace('```', '')
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)

    # \text{...} hatana
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathit\{([^}]*)\}', r'\1', text)

    # Greek letters mapping
    greek_map = {
        r'\alpha': 'α',
        r'\beta': 'β',
        r'\gamma': 'γ',
        r'\theta': 'θ',
        r'\lambda': 'λ',
        r'\pi': 'π',
        r'\Delta': 'Δ',
        r'\omega': 'ω'
    }
    for latex, symbol in greek_map.items():
        text = text.replace(latex, symbol)

    # Math symbols
    text = text.replace(r'\times', '×').replace(r'\cdot', '·')
    text = text.replace(r'\le', '≤').replace(r'\ge', '≥')
    text = text.replace(r'\neq', '≠').replace(r'\approx', '≈')
    text = text.replace(r'\pm', '±').replace(r'\degree', '°')

    # Fractions aur Roots
    text = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1 / \2)', text)

    # Leftover backslashes hatana
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)

    # Extra LaTeX markers aur stars saaf karna
    text = text.replace('$$', '').replace('$', '').replace(r'\(', '').replace(r'\)', '')
    text = text.replace('***', '').replace('**', '')

    return text.strip()

# Dynamic Available Model Discovery via REST API
CACHED_AVAILABLE_MODEL = None

def get_dynamic_model():
    global CACHED_AVAILABLE_MODEL
    if CACHED_AVAILABLE_MODEL:
        return CACHED_AVAILABLE_MODEL

    try:
        url = f"[https://generativelanguage.googleapis.com/v1beta/models?key=](https://generativelanguage.googleapis.com/v1beta/models?key=){API_KEY}"
        res = requests.get(url, timeout=5).json()

        flash_models = []
        for m in res.get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            name = m.get("name", "")  # Format: "models/gemini-..."
            name_lower = name.lower()

            if "generateContent" in methods:
                # Omni, pro, tts, vision, audio ko bypass karna
                if any(bad in name_lower for bad in ['omni', 'pro', 'tts', 'audio', 'vision', 'embedding', 'image']):
                    continue
                if 'flash' in name_lower:
                    clean_name = name.replace("models/", "")
                    flash_models.append(clean_name)

        if flash_models:
            flash_models.sort(reverse=True)
            CACHED_AVAILABLE_MODEL = flash_models[0]
            return CACHED_AVAILABLE_MODEL
    except Exception as e:
        print(f"Dynamic discovery error: {e}")

    # Fallback to standard live flash
    CACHED_AVAILABLE_MODEL = "gemini-2.5-flash"
    return CACHED_AVAILABLE_MODEL

# --- HTML & CHAT INTERFACE ---
CHAT_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lakshya Mentor 3.0</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; height: 100vh; display: flex; flex-direction: column; }
        header { background: #1e293b; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; }
        header h1 { font-size: 18px; font-weight: 700; color: #38bdf8; }
        header span { font-size: 12px; color: #94a3b8; }
        .tag { font-size: 11px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
        #chat-box { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
        .placeholder-hint { margin: auto; text-align: center; color: #64748b; font-size: 14px; }
        .message { max-width: 90%; padding: 12px 16px; border-radius: 14px; font-size: 15px; line-height: 1.65; word-break: break-word; white-space: pre-wrap; }
        .user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 2px; }
        .bot { align-self: flex-start; background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-bottom-left-radius: 2px; }
        .typing-indicator { display: flex; align-items: center; gap: 6px; padding: 10px 16px; font-size: 13px; color: #94a3b8; }
        .dot { width: 7px; height: 7px; background: #38bdf8; border-radius: 50%; animation: blink 1.4s infinite both; }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink { 0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1); } }
        .timer-text { margin-left: 5px; font-variant-numeric: tabular-nums; color: #38bdf8; font-weight: 600; }
        #input-area { background: #1e293b; padding: 12px; border-top: 1px solid #334155; display: flex; gap: 10px; }
        input { flex: 1; padding: 12px 16px; border-radius: 24px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 15px; outline: none; }
        input:focus { border-color: #38bdf8; }
        button { background: #2563eb; color: #fff; border: none; padding: 0 20px; border-radius: 24px; font-weight: 600; cursor: pointer; transition: 0.2s; }
        button:hover { background: #1d4ed8; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>Lakshya Mentor 3.0</h1>
            <span>Class 9 & 10 Board Mentor</span>
        </div>
        <span class="tag">Active</span>
    </header>

    <div id="chat-box">
        <div class="placeholder-hint" id="hint-text">Padhai shuru karne ke liye niche <b>'Hi'</b> ya apna sawal likho</div>
    </div>

    <form id="input-area" onsubmit="sendQuery(event)">
        <input type="text" id="user-input" placeholder="Apna doubt ya sawal likho..." autocomplete="off" required />
        <button type="submit" id="send-btn">Send</button>
    </form>

    <script>
        let chatHistory = [];
        let timerInterval = null;
        const chatBox = document.getElementById('chat-box');
        const userInput = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');

        function appendMessage(text, sender) {
            const hint = document.getElementById('hint-text');
            if (hint) hint.remove();

            const div = document.createElement('div');
            div.className = `message ${sender}`;
            div.innerText = text;

            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
            return div;
        }

        async function sendQuery(e) {
            e.preventDefault();
            const msg = userInput.value.trim();
            if (!msg) return;

            appendMessage(msg, "user");
            userInput.value = "";
            userInput.disabled = true;
            sendBtn.disabled = true;

            const loaderDiv = document.createElement('div');
            loaderDiv.className = "message bot typing-indicator";
            loaderDiv.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="timer-text">0.0s</span>';
            chatBox.appendChild(loaderDiv);
            chatBox.scrollTop = chatBox.scrollHeight;

            let startTime = performance.now();
            timerInterval = setInterval(() => {
                const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
                const timerSpan = loaderDiv.querySelector('.timer-text');
                if (timerSpan) timerSpan.innerText = elapsed + "s";
            }, 100);

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msg, history: chatHistory })
                });

                const data = await res.json();
                clearInterval(timerInterval);
                loaderDiv.remove();

                const reply = data.reply || "Kuch takneeki dikkat aayi, dobara prayas karein.";
                appendMessage(reply, "bot");

                chatHistory.push({ role: "user", parts: [{ text: msg }] });
                chatHistory.push({ role: "model", parts: [{ text: reply }] });

                if (chatHistory.length > 6) {
                    chatHistory = chatHistory.slice(-6);
                }
            } catch (err) {
                clearInterval(timerInterval);
                loaderDiv.remove();
                appendMessage("Server par load hai. Kripya 5 second ruk kar dobara bhej kar dekhein.", "bot");
            } finally {
                userInput.disabled = false;
                sendBtn.disabled = false;
                userInput.focus();
            }
        }
    </script>
</body>
</html>
"""

# --- ROUTES ---

@app.route("/", methods=['GET'])
def home():
    return render_template_string(CHAT_HTML)

@app.route("/ping", methods=['GET'])
def keep_alive():
    return jsonify({"status": "active", "service": "Lakshya Mentor 3.0", "timestamp": time.time()}), 200

@app.route("/chat", methods=['POST'])
def chat():
    global CACHED_AVAILABLE_MODEL
    data = request.get_json(silent=True) or {}
    user_query = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_query:
        return jsonify({"reply": "Apna sawal likhein ya batayein kis topic me doubt hai."}), 400

    clean_query = re.sub(r'[^\w\s]', '', user_query).lower().strip()
    is_greeting = bool(re.match(r'^(h+i+|h+e+l+l*o+|h+e+y+|namaste|pranam|start|shuru)\b', clean_query))

    if is_greeting:
        welcome_reply = (
            "Namaste aur Lakshya Mentor 3.0 me swagat hai!\n\n"
            "Main tumhara personal board exam mentor hoon. Padhai shuru karne se pehle mujhe ye do baatein batao:\n"
            "1. Tumhara Naam kya hai?\n"
            "2. Tum kaun si Class me ho (Class 9 ya Class 10)?\n\n"
            "Batao, taaki hum NCERT aur Board PYQs ke hisaab se planning shuru kar sakein!"
        )
        return jsonify({"reply": welcome_reply}), 200

    if not API_KEY:
        return jsonify({"reply": "Server error: API Key configure nahi hai."}), 500

    selected_model = get_dynamic_model()
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){selected_model}:generateContent?key={API_KEY}"

    contents = []
    for h in history:
        contents.append(h)
    contents.append({"role": "user", "parts": [{"text": user_query}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 800
        }
    }

    try:
        r = requests.post(url, json=payload, timeout=18)
        res_data = r.json()

        if "candidates" in res_data and len(res_data["candidates"]) > 0:
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            cleaned = clean_math_syntax(raw_text)
            return jsonify({"reply": cleaned, "model_used": selected_model}), 200
        elif "error" in res_data:
            CACHED_AVAILABLE_MODEL = None  # Error par cache reset
            err_msg = res_data['error'].get('message', 'Unknown Error')
            return jsonify({"reply": f"API Error: {err_msg}"}), 200
        else:
            return jsonify({"reply": "Jawab prapt nahi hua, kripya dobara sawal bhejein."}), 200

    except requests.exceptions.Timeout:
        return jsonify({"reply": "Server response me thoda time lag gaya. Kripya chhota sawal likh kar bhejein."}), 200
    except Exception as e:
        CACHED_AVAILABLE_MODEL = None
        return jsonify({"reply": f"Error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
