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

# 3. System Prompt with Concept-First Guard & Clean Math
SYSTEM_PROMPT = """
Tumhara naam Lakshya Mentor 3.0 hai—Class 9 aur Class 10 (Bihar Board & CBSE) ke bacho ke liye ek academic AI guide aur mentor.

CORE PEDAGOGY RULES:
1. CONCEPT-FIRST GUARD (NO DIRECT SHORTCUTS):
   - Agar student direct 'Notes', 'Important Questions', ya direct formula/solution maangta hai:
     * Pehle strictly 2-3 lines me core concept ka intuition/reason samjhao.
     * Saaf bolo: "Pehle logic samajhna zaroori hai, direct ratne se exam me marks nahi aayenge."
     * Uske baad hi structured key-points ya formulas do.

2. MANDATORY COUNTER-QUESTION:
   - Har jawab ke aakhiri me ek challenging concept-checking sawal zaroor poocho.
   - Class 10: NCERT Exemplar ya Board PYQ level question.
   - Class 9: Foundational concept test question.
   - Student se bolo ki aage badhne ke liye is sawal ka jawab de.

3. CLASS 10 STRICT BOARD PATTERN:
   - Strict aur serious mentor tone.
   - Board exam step-marking follow karo (GIVEN -> FORMULA -> STEP-BY-STEP CALCULATION -> FINAL ANSWER WITH UNIT).

4. CLEAN MATHS RULES (NO LATEX):
   - Kisi bhi halat me raw LaTeX (jaise \\frac, \\sqrt, \\times, $) use mat karo.
   - Numbers ya formulas ke aage peeche backtick (`) mat lagao.
   - Clean readable format use karo:
     * Division: (a / b)
     * Multiplication: * ya x
     * Powers: x^2 ya x cube
     * Roots: sqrt(x)
"""

def clean_math_syntax(text):
    if not text:
        return ""
    text = text.replace('`', '')
    text = re.sub(r'\\\[\vert{}\\\]|\$|\$', '', text)
    text = text.replace('\\times', '*').replace('\\cdot', '*')
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', text)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'sqrt(\1)', text)
    return text.strip()

# CACHED DYNAMIC MODELS (Quota bachane ke liye 5 minute tak cache rahega)
CACHED_MODELS = []
LAST_FETCH_TIME = 0

def get_dynamic_flash_models():
    global CACHED_MODELS, LAST_FETCH_TIME
    now = time.time()
    # Agar pichle 5 minute ke andar models fetch hue hain toh wahi use karo
    if CACHED_MODELS and (now - LAST_FETCH_TIME < 300):
        return CACHED_MODELS

    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name_lower = m.name.lower()
                if 'pro' in name_lower or 'vision' in name_lower or 'embedding' in name_lower:
                    continue
                if 'flash' in name_lower:
                    available_models.append(m.name)
        if available_models:
            CACHED_MODELS = available_models
            LAST_FETCH_TIME = now
            return available_models
    except Exception as e:
        print(f"[WARN] Dynamic model fetch failed: {e}")

    return CACHED_MODELS if CACHED_MODELS else ["models/gemini-1.5-flash", "models/gemini-2.0-flash"]

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
        .message { max-width: 88%; padding: 12px 16px; border-radius: 14px; font-size: 14.5px; line-height: 1.6; word-break: break-word; }
        .message p { margin-bottom: 8px; }
        .message p:last-child { margin-bottom: 0; }
        .message ul, .message ol { margin-left: 20px; margin-bottom: 8px; }
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
                appendMessage("Server par thoda load hai. Kripya dobara bhej kar dekhein.", "bot");
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
    greeting_triggers = ["hi", "hello", "namaste", "pranam", "hey", "hlo", "start", "shuru"]

    if clean_query in greeting_triggers or any(clean_query.startswith(w + " ") for w in greeting_triggers):
        welcome_reply = (
            "🌟 **Namaste aur Lakshya Mentor 3.0 me swagat hai!**\n\n"
            "Main tumhara personal board exam mentor hoon. Padhai shuru karne se pehle mujhe ye do baatein batao:\n"
            "1. **Tumhara Naam kya hai?**\n"
            "2. **Tum kaun si Class me ho (Class 9 ya Class 10)?**\n\n"
            "Batao, taaki hum tumhare target aur syllabus ke mutabiq planning shuru kar sakein!"
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

    # DUAL KEY POOL WITH FAILOVER
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
                    err_str = last_error.lower()
                    if "429" in err_str or "quota" in err_str:
                        # Current key quota full, move to next key immediately
                        break
                    continue

        except Exception as k_err:
            last_error = str(k_err)
            continue

    if "429" in last_error.lower() or "quota" in last_error.lower():
        return jsonify({"reply": "API limit temporary busy hai. Kripya 1 minute baad dobara sawal bhejein."}), 429

    return jsonify({"reply": "AI service se connection me dikkat aayi. Kripya dobara koshish karein."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
