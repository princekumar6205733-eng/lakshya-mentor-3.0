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

# 3. System Prompt with Concept-First Guard & Step-by-Step Pedagogy
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
   - Clean readable format use karo:
     * Division: (a / b)
     * Multiplication: * ya x
     * Powers: x^2 ya x cube
     * Roots: sqrt(x)
"""

def clean_math_syntax(text):
    if not text:
        return ""
    text = re.sub(r'\\\[|\\\]|\$|\$', '', text)
    text = text.replace('\\times', '*').replace('\\cdot', '*')
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', text)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'sqrt(\1)', text)
    return text.strip()

def get_dynamic_flash_models():
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name_lower = m.name.lower()
                if 'pro' in name_lower or 'vision' in name_lower:
                    continue
                if 'flash' in name_lower:
                    available_models.append(m.name)
        if available_models:
            return available_models
    except Exception as e:
        print(f"[WARN] Dynamic model fetch failed: {e}")
    return ["models/gemini-1.5-flash", "models/gemini-2.0-flash"]

# --- ROUTES ---

@app.route('/', methods=['GET'])
def home():
    html_page = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lakshya Mentor 3.0</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d1117; color: #c9d1d9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
            .card { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; max-width: 450px; width: 100%; text-align: center; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
            h1 { color: #58a6ff; font-size: 24px; margin-bottom: 10px; }
            p { color: #8b949e; font-size: 14px; line-height: 1.5; }
            .status-badge { display: inline-block; padding: 6px 14px; background: rgba(56, 139, 253, 0.15); color: #58a6ff; border: 1px solid #388bfd; border-radius: 20px; font-weight: 600; font-size: 13px; margin: 15px 0; }
            .info { background: #21262d; border-radius: 8px; padding: 15px; text-align: left; font-size: 13px; color: #8b949e; margin-top: 15px; }
            .info b { color: #f0f6fc; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🚀 Lakshya Mentor 3.0</h1>
            <div class="status-badge">● API Live & Running</div>
            <p>Class 9th & 10th AI Study Mentor Backend is operational.</p>
            <div class="info">
                <div><b>Health Check:</b> <a href="/ping" style="color: #58a6ff;">/ping</a></div>
                <div style="margin-top: 8px;"><b>Chat Endpoint:</b> <code>POST /chat</code></div>
                <div style="margin-top: 8px;"><b>System Architecture:</b> Multi-Tenant Ready</div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_page)

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

    clean_query = re.sub(r'[^\w\s]', '', user_query).lower()
    greeting_triggers = ["hi", "hello", "namaste", "pranam", "hey", "start"]

    # SMART WELCOME & ONBOARDING INTERCEPTOR
    if len(history) == 0 and any(clean_query.startswith(w) for w in greeting_triggers):
        welcome_reply = (
            "🌟 **Namaste aur Lakshya Mentor 3.0 me swagat hai!**\n\n"
            "Main tumhara personal board exam mentor hoon. Padhai shuru karne se pehle mujhe ye do baatein batao:\n"
            "1. **Tumhara Naam kya hai?**\n"
            "2. **Tum kaun si Class me ho (Class 9 ya Class 10)?**\n\n"
            "Batao, taaki hum tumhare target ke hisaab se planning shuru kar sakein!"
        )
        return jsonify({"reply": welcome_reply, "status": "ask_class"}), 200

    if not API_KEYS:
        return jsonify({"reply": "Server error: API Keys configure nahi hain."}), 500

    generation_config = {
        "temperature": 0.3,
        "top_p": 0.85,
        "max_output_tokens": 2048,
    }

    hit_429_quota = False
    hit_503_busy = False

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
                    err_str = str(m_err).lower()
                    if "429" in err_str or "quota" in err_str:
                        hit_429_quota = True
                        break
                    elif "503" in err_str or "overloaded" in err_str:
                        hit_503_busy = True
                        continue
                    else:
                        continue

        except Exception as k_err:
            print(f"[ERROR] Key #{key_idx+1} failed: {k_err}")
            continue

    if hit_429_quota:
        return jsonify({"reply": "System quota limit par hai. Kripya 1 minute baad dobara koshish karein."}), 429
    elif hit_503_busy:
        return jsonify({"reply": "AI server par thoda heavy load hai. 30 second me sawal dobara bhejein."}), 503

    return jsonify({"reply": "AI service se sampark nahi ho pa raha hai. Kripya thodi der baad prayas karein."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
