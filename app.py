import os
import time
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

app = Flask(__name__)
CORS(app)

# 1. Dual API Key Pool (Render Environment Variables se private load hoga)
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

# 3. System Prompt with Concept-First Guard + Counter-Question Loop
SYSTEM_PROMPT = """
Tumhara naam Lakshya Mentor 3.0 hai—Class 9 aur Class 10 ke students ke liye sabse disciplined aur focused AI study mentor.

CORE PEDAGOGY RULES:
1. CONCEPT-FIRST GUARD (NO DIRECT SHORTCUTS):
   - Agar student direct 'Notes', 'Important Points', ya 'Shortcuts' mange:
     * Pehle strictly 2-3 lines me core concept/logic samjhao.
     * Saaf bolo: "Pehle logic samajhna zaroori hai, taaki exam me tricky sawal aaye toh faso nahi."
     * Uske baad hi structured key-points provide karo.

2. MANDATORY COUNTER-QUESTION:
   - Har jawab ke aakhiri me ek challenging COUNTER-QUESTION poochna COMPULSORY hai.
   - Class 10: NCERT Exemplar ya Board PYQs (Previous Year Questions) se linked hona chahiye.
   - Class 9: Foundational concept test ya daily life application par hona chahiye.
   - Student se bolo ki aage badhne ke liye pehle iska jawab de.

3. CLASS 10 STRICT BOARD PATTERN:
   - Strict aur serious mentor tone.
   - Board exam step-marking follow karo: Given -> Formula -> Step-by-Step Calculation -> Unit ke saath Final Answer.

4. CLEAN MATHS RULES (NO LATEX):
   - Kisi bhi halat me raw LaTeX (jaise \\frac, \\times, $$, \\sqrt) use mat karna.
   - Clean readable format use karo:
     * Division: (a / b)
     * Multiplication: * ya x
     * Powers: x^2 ya x cube
     * Roots: sqrt(x)
"""

def clean_math_syntax(text):
    if not text:
        return ""
    text = re.sub(r'\\\[|\\\]|\$\$|\$', '', text)
    text = text.replace('\\times', '*').replace('\\div', '/').replace('\\pm', '+/-')
    text = re.sub(r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1 / \2)', text)
    text = re.sub(r'\\sqrt\{([^}]+)\}', r'sqrt(\1)', text)
    return text.strip()

def get_dynamic_flash_models():
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name_lower = m.name.lower()
                if 'pro' in name_lower or 'embedding' in name_lower or 'aqa' in name_lower:
                    continue
                if 'flash' in name_lower or 'lite' in name_lower:
                    available_models.append(m.name)
        if available_models:
            return available_models
    except Exception as e:
        print(f"[WARN] Dynamic model fetch failed: {e}")
    return ["models/gemini-1.5-flash", "models/gemini-2.0-flash-lite"]

@app.route('/ping', methods=['GET'])
def keep_alive():
    return jsonify({"status": "active", "version": "Lakshya Mentor 3.0"}), 200

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    user_query = data.get("message", "").strip()
    history = data.get("history", [])

    if not user_query:
        return jsonify({"reply": "Apna sawal ya doubt yahan type karo!", "status": "empty"}), 400

    clean_query = re.sub(r'[^\w\s]', '', user_query.lower()).strip()
    greeting_triggers = ["hi", "hello", "hey", "hlo", "namaste", "pranam", "start", "shuru"]

    # SMART WELCOME & ONBOARDING INTERCEPTOR
    # Agar nayi chat hai aur bacha greeting bhejta hai, toh grand swagat karke Naam aur Class maango
    if (len(history) == 0 and clean_query in greeting_triggers) or clean_query in greeting_triggers:
        welcome_reply = (
            "🌟 **Namaste aur Lakshya Mentor 3.0 me tumhara swagat hai!** 🎯\n\n"
            "Main tumhara personal board aur study mentor hoon. Tumhari padhai, concepts aur revision ko top level banane ke liye main taiyar hoon.\n\n"
            "Sabse pehle mujhe ye do baatein batao:\n"
            "1. **Tumhara Naam kya hai?**\n"
            "2. **Tum kaun si Class me ho? (Class 9th ya Class 10th?)**\n\n"
            "Batao, taaki hum tumhare exact syllabus aur board exam level ke hisaab se shuruwat kar sakein!"
        )
        return jsonify({
            "reply": welcome_reply,
            "status": "ask_class"
        }), 200

    if not API_KEYS:
        return jsonify({"reply": "API Key configuration missing on server.", "status": "error"}), 500

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
        except Exception:
            continue

        available_models = get_dynamic_flash_models()

        for model_name in available_models:
            for attempt in range(2):
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=SYSTEM_PROMPT,
                        generation_config=generation_config,
                        safety_settings=SAFE_SETTINGS
                    )

                    contents = []
                    for turn in history[-4:]:
                        role = "user" if turn.get("role") == "user" else "model"
                        contents.append({"role": role, "parts": [turn.get("text", "")]})
                    contents.append({"role": "user", "parts": [user_query]})

                    response = model.generate_content(contents)

                    if not response.candidates:
                        break

                    candidate = response.candidates[0]
                    if candidate.finish_reason not in [1, 2]:
                        break

                    parts = candidate.content.parts if candidate.content else []
                    if not parts or not parts[0].text:
                        break

                    cleaned_reply = clean_math_syntax(parts[0].text)
                    return jsonify({"reply": cleaned_reply, "status": "success"}), 200

                except Exception as err:
                    err_str = str(err)
                    if "429" in err_str or "ResourceExhausted" in err_str:
                        hit_429_quota = True
                        break
                    elif "503" in err_str or "Unavailable" in err_str:
                        hit_503_busy = True
                        time.sleep(1.5)
                        continue
                    else:
                        break

    if hit_429_quota:
        return jsonify({"reply": "Traffic thoda zyada hai. Kripya 30 seconds ruko aur fir bhejo.", "status": "cooldown"}), 200

    if hit_503_busy:
        return jsonify({"reply": "Server par load hai. 15 second baad dobara send dabao.", "status": "busy"}), 200

    return jsonify({"reply": "Chhota network delay aaya hai. 10 second baad dobara koshish karo.", "status": "retry"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
  
