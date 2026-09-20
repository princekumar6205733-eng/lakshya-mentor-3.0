import os
import time
import re
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)
CORS(app)

# 1. Dual API Key Pool (Render Environment Variables)
API_KEYS = [
    os.environ.get("GEMINI_API_KEY_1", "").strip(),
    os.environ.get("GEMINI_API_KEY_2", "").strip()
]
API_KEYS = [k for k in API_KEYS if k]

# 2. Aggressive Safety Bypass
SAFE_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

# 3. System Prompt with Proper Math Markdown, NCERT, PYQ & Board Pattern
SYSTEM_PROMPT = """
Tumhara naam Lakshya Mentor 3.0 hai—Class 9 aur Class 10 (Bihar Board / BSEB aur CBSE) ke chhatron ke liye ek academic AI mentor.

CORE PEDAGOGICAL PILLARS:
1. NCERT & STANDARD REFERENCE BASE:
   - Saare concepts, definitions aur numericals strictly NCERT, NCERT Exemplar, aur standard state guide/reference books ke mutabiq hone chahiye.
   - Student jis bhasha (Hindi/Hinglish/English) me baat kare, usi bhasha me samjhao.

2. CONCEPT-FIRST GUARD (NO SHORTCUTS):
   - Agar student direct answer, formula, ya ratta maangta hai:
     * Pehle strictly 2-3 lines me underlying concept/logic samjhao.
     * Saaf bolo: "Pehle logic samajhna zaroori hai, direct ratne se board exam me marks nahi aayenge."
     * Uske baad hi structured answer/formula do.

3. BOARD EXAM STEP-MARKING PATTERN (CLASS 10):
   - Subjective sawalon me strict Bihar Board / CBSE topper step-marking format follow karo:
     * **GIVEN (दिया गया है)**
     * **TO FIND / TO PROVE (ज्ञात करना है / सिद्ध करना है)**
     * **FORMULA / THEOREM (सूत्र / प्रमेय)**
     * **STEP-BY-STEP CALCULATION (चरणबद्ध हल)**
     * **FINAL ANSWER WITH UNIT (उत्तर)**

4. MANDATORY COUNTER-QUESTION (PYQ & OMR OBJECTIVES):
   - Har jawab ke aakhiri me ek challenging concept-checking sawal zaroor poocho.
   - Bihar Board: Pichle saalon ka official BSEB PYQ ya OMR Objective Question (4 options A, B, C, D ke saath).
   - CBSE: NCERT Exemplar ya PYQ case-based sawal.
   - Student se bolo: "Agla topic shuru karne se pehle is sawal ka jawab comment/reply me do!"

5. CLEAN MATH FORMAT:
   - Maths ke expressions ko simple standard format me likho: jaise `a = b * q + r` jahan `0 <= r < b`.
   - Complex roots ko `√5` ya `sqrt(5)` aur powers ko `x²` ya `x^2` likho taaki mobile par saaf padha ja sake.
   - Faltu raw backticks ka prayog har number ke aage-peeche mat karo.
"""

def clean_math_syntax(text):
    if not text:
        return ""
    # Strip unnecessary raw delimiters
    text = text.replace('`', '')
    text = re.sub(r'\\\[\vert{}\\\]|\$|\$', '', text)
    text = text.replace('\\times', '×').replace('\\cdot', '·')
    text = text.replace('\\le', '≤').replace('\\ge', '≥')
    text = text.replace('\\neq', '≠')
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'√\1', text)
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', text)
    return text.strip()

# Dynamic Model Cache
CACHED_MODELS = []
LAST_FETCH_TIME = 0

def get_dynamic_flash_models():
    global CACHED_MODELS, LAST_FETCH_TIME
    now = time.time()
    if CACHED_MODELS and (now - LAST_FETCH_TIME < 300):
        return CACHED_MODELS

    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name_lower = m.name.lower()
                if any(x in name_lower for x in ['pro', 'tts', 'audio', 'vision', 'embedding', 'image']):
                    continue
                if 'flash' in name_lower:
                    available_models.append(m.name)
        if available_models:
            # Sort to put high-speed flash models first
            available_models.sort(key=lambda x: ('1.5' in x or '2.0' in x), reverse=True)
            CACHED_MODELS = available_models
            LAST_FETCH_TIME = now
            return available_models
    except Exception as e:
        print(f"[WARN] Dynamic model fetch failed: {e}")

    return ["models/gemini-1.5-flash", "models/gemini-2.0-flash"]

# --- HTML & CHAT INTERFACE ---
CHAT_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lakshya Mentor 3.0</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; height: 100vh; display: flex; flex-direction: column; }
        header { background: #1e293b; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #334155; }
        header h1 { font-size: 18px; font-weight: 700; color: #38bdf8; }
        .tag { font-size: 11px; background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #38bdf8; padding: 3px 8px; border-radius: 12px; }
        #chat-box { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
        .placeholder-hint { margin: auto; text-align: center; color: #64748b; font-size: 14px; }
        .message { max-width: 90%; padding: 12px 16px; border-radius: 14px; font-size: 15px; line-height: 1.65; word-break: break-word; }
        .message p { margin-bottom: 10px; }
        .message p:last-child { margin-bottom: 0; }
        .message ul, .message ol { margin-left: 20px; margin-bottom: 10px; }
        .message li { margin-bottom: 4px; }
        .message strong { color: #38bdf8; }
        .message hr { border: 0; border-top: 1px solid #334155; margin: 12px 0; }
        .user { align-self: flex-end; background: #2563eb; color: #fff; border-bottom-right-radius: 2px; }
        .bot { align-self: flex-start; background: #1e293b; color: #e2e8f0; border: 1px solid #334155; border-bottom-left-radius: 2px; }
        .typing-indicator { display: flex; align-items: center; gap: 6px; padding: 10px 16px; font-size: 13px; color: #94a3b8; }
        .dot { width: 7px; height: 7px; background: #38bdf8; border-radius: 50%; animation: blink 1.4s infinite both; }
        .dot:nth-child(2) { animation-delay: 0.2s; }
        .dot:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink { 0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1.1); } }
        .timer-text { margin-left: 8px; font-variant-numeric: tabular-nums; color: #38bdf8; font-weight: 600; }
        #input-area { background: #1e293b; padding: 12px; border-top: 1px solid #334155; display: flex; gap: 10px; }
        input { flex: 1; padding: 12px 16px; border-radius: 24px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 15px; outline: none; }
        input:focus { border-color: #38bdf8; }
        button { background: #2563eb; color: #fff; border: none; padding: 0 20px; border-radius: 24px; font-weight: 600; cursor: pointer; }
        button:hover { background: #1d4ed8; }
        button:disabled { opacity: 0.6; cursor: not-allowed; }
    </style>
</head>
<body>
    <header>
        <div>
            <h1>🚀 Lakshya Mentor 3.0</h1>
            <span style="font-size: 12px; color: #94a3b8;">Class 9 & 10 Board Mentor</span>
        </div>
        <span class="tag">Active</span>
    </header>

    <div id="chat-box">
        <div class="placeholder-hint" id="hint-text">Padhai shuru karne ke liye niche <b>'Hi'</b> ya apna sawal likho 👇</div>
    </div>

    <form id="input-area" onsubmit="sendQuery(event)">
        <input type="text" id="user-input" placeholder="Apna doubt ya sawal likho..." autocomplete="off" required />
        <button type="submit" id="send-btn">Send</button>
    </form>

    <script>
        let chatHistory = [];
        let timerInterval = null;
        const chatBox = document.getElementById("chat-box");
        const userInput = document.getElementById("user-input");
        const sendBtn = document.getElementById("send-btn");

        function appendMessage(text, sender) {
            const hint = document.getElementById("hint-text");
            if (hint) hint.remove();

            const div = document.createElement("div");
            div.className = "message " + sender;
            
            if (sender === "bot") {
                div.innerHTML = marked.parse(text);
            } else {
                div.innerText = text;
            }

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

            const loaderDiv = document.createElement("div");
            loaderDiv.className = "message bot typing-indicator";
            loaderDiv.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="timer-text">0.0s</span>';
            chatBox.appendChild(loaderDiv);
            chatBox.scrollTop = chatBox.scrollHeight;

            let startTime = performance.now();
            timerInterval = setInterval(() => {
                const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
                const timerSpan = loaderDiv.querySelector(".timer-text");
                if (timerSpan) timerSpan.innerText = elapsed + "s";
            }, 100);

            try {
                const res = await fetch("/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ message: msg, history: chatHistory })
                });

                const data = await res.json();
                clearInterval(timerInterval);
                loaderDiv.remove();

                const reply = data.reply || "Kuch takneeki dikkat aayi, dobara prayas karein.";
                appendMessage(reply, "bot");

                chatHistory.push({ role: "user", parts: [msg] });
                chatHistory.push({ role: "model", parts: [reply] });
            } catch (err) {
                clearInterval(timerInterval);
                loaderDiv.remove();
                appendMessage("Server par load hai. Kripya thoda ruk kar dobara bhej kar dekhein.", "bot");
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

@app.route('/', methods=['GET'])
def home():
    return render_template_string(CHAT_HTML)

@app.route('/ping', methods=['GET'])
def keep_alive():
    return jsonify({"status": "active", "service": "Lakshya Mentor 3.0", "timestamp": time.time()}), 200

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_query = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_query:
        return jsonify({"reply": "Apna sawal likhein ya batayein kis topic me doubt hai."}), 400

    clean_query = re.sub(r'[^\w\s]', '', user_query).lower().strip()
    
    # Accurate greeting regex
    is_greeting = bool(re.match(r'^(h+i+|h+e+l+o+|h+e+y+|namaste|pranam|start|shuru)\b', clean_query))

    if is_greeting:
        welcome_reply = (
            "🌟 **Namaste aur Lakshya Mentor 3.0 me swagat hai!**\n\n"
            "Main tumhara personal board exam mentor hoon. Padhai shuru karne se pehle mujhe ye do baatein batao:\n"
            "1. **Tumhara Naam kya hai?**\n"
            "2. **Tum kaun si Class me ho (Class 9 ya Class 10)?**\n\n"
            "Batao, taaki hum NCERT aur Board PYQs ke hisaab se planning shuru kar sakein!"
        )
        return jsonify({"reply": welcome_reply, "status": "ask_class"}), 200

    if not API_KEYS:
        return jsonify({"reply": "Server error: API Keys configure nahi hain."}), 500

    generation_config = {
        "temperature": 0.3,
        "top_p": 0.85,
        "max_output_tokens": 2048,
    }

    last_error = ""

    # DUAL KEY ROTATION WITH SORTED MODELS
    for key_idx, key in enumerate(API_KEYS):
        try:
            genai.configure(api_key=key)
            models = get_dynamic_flash_models()

            for model_name in models:
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=SYSTEM_PROMPT,
                        generation_config=generation_config,
                        safety_settings=SAFE_SETTINGS
                    )

                    chat_session = model.start_chat(history=history)
                    response = chat_session.send_message(user_query)

                    cleaned_reply = clean_math_syntax(response.text)
                    return jsonify({"reply": cleaned_reply, "model_used": model_name}), 200

                except Exception as m_err:
                    last_error = str(m_err)
                    continue

        except Exception as k_err:
            last_error = str(k_err)
            continue

    if "429" in last_error.lower() or "quota" in last_error.lower():
        return jsonify({"reply": f"Google Quota Alert: {last_error}"}), 429

    return jsonify({"reply": f"AI Error: {last_error}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
