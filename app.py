import os
import re
import google.generativeai as genai
import gradio as gr

API_KEY = os.environ.get("GEMINI_API_KEY_1", "").strip() or os.environ.get("GEMINI_API_KEY_2", "").strip()
if API_KEY:
    genai.configure(api_key=API_KEY)

SYSTEM_PROMPT = """
Tumhara naam Lakshya Mentor 3.0 hai—Class 9 aur Class 10 (Bihar Board / BSEB aur CBSE) ke chhatron ke liye ek academic mentor.

CORE PEDAGOGICAL PILLARS:
1. NCERT & STANDARD REFERENCE BASE:
   - Saare concepts, definitions aur numericals strictly NCERT, NCERT Exemplar, aur standard state guide ke mutabiq hon.
   - Bhasha saral, saaf Hindi/Hinglish honi chahiye jisse bachhe ko samajh aaye.

2. STRICT READABILITY RULE (NO RAW LATEX / NO CODE TAGS / NO UNWANTED ASTERISKS):
   - KISI BHI HALAT ME raw LaTeX tags jaise \\text{...}, \\frac, \\sqrt, \\alpha, \\beta, \\times use MAT KARO.
   - Greek letters ko directly readable likho: jaise alpha (α), beta (β), theta (θ).
   - Division ko simple (a / b) likho. Formulas ko simple likho jaise:
     Shunyako ka Yog (α + β) = -(x ka gunank) / (x^2 ka gunank) = -b/a
     Shunyako ka Gunanfal (α * β) = (Achar pad) / (x^2 ka gunank) = c/a

3. CONCEPT-FIRST GUARD (NO SHORTCUTS):
   - Pehle strictly 2-3 lines me core logic samjhao, uske baad hi calculation aur answer do.

4. BOARD EXAM STEP-MARKING PATTERN (CLASS 10):
   - Subjective sawalon me strict Bihar Board / CBSE topper step-marking format follow karo:
     GIVEN (Diya gaya hai): ...
     TO FIND / TO PROVE (Gyaat karna hai / Siddh karna hai): ...
     FORMULA / THEOREM (Sutra / Pramey): ...
     STEP-BY-STEP CALCULATION (Charanbaddh hal): ...
     FINAL ANSWER WITH UNIT (Uttar): ...

5. MANDATORY COUNTER-QUESTION:
   - Har jawab ke ant me 1 objective sawal zaroor poochho 4 options (A, B, C, D) ke saath.
"""

def clean_math_syntax(text):
    if not text:
        return ""
    text = text.replace('```', '')
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathbf\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\mathit\{([^}]*)\}', r'\1', text)

    greek_map = {
        r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ',
        r'\theta': 'θ', r'\lambda': 'λ', r'\pi': 'π',
        r'\Delta': 'Δ', r'\omega': 'ω'
    }
    for latex, symbol in greek_map.items():
        text = text.replace(latex, symbol)

    text = text.replace(r'\times', '×').replace(r'\cdot', '·')
    text = text.replace(r'\le', '≤').replace(r'\ge', '≥')
    text = text.replace(r'\neq', '≠').replace(r'\approx', '≈')
    text = text.replace(r'\pm', '±').replace(r'\degree', '°')

    text = re.sub(r'\\sqrt\{([^}]*)\}', r'√(\1)', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'(\1 / \2)', text)
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)
    text = text.replace('$$', '').replace('$', '').replace(r'\(', '').replace(r'\)', '')
    text = text.replace('***', '').replace('**', '')
    return text.strip()

CACHED_MODEL = None

def get_flash_model():
    global CACHED_MODEL
    if CACHED_MODEL:
        return CACHED_MODEL
    try:
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name = m.name.lower()
                if any(x in name for x in ['omni', 'pro', 'tts', 'audio', 'vision', 'embedding', 'image']):
                    continue
                if 'flash' in name:
                    models.append(m.name)
        if models:
            models.sort(reverse=True)
            CACHED_MODEL = models[0]
            return CACHED_MODEL
    except Exception:
        pass
    CACHED_MODEL = "models/gemini-2.5-flash"
    return CACHED_MODEL

def predict(message, history):
    if not API_KEY:
        yield "Render Environment Variable me API Key set nahi hai."
        return

    clean_query = re.sub(r'[^\w\s]', '', message).lower().strip()
    if bool(re.match(r'^(h+i+|h+e+l+l*o+|h+e+y+|namaste|pranam|start|shuru)\b', clean_query)):
        welcome_reply = (
            "Namaste aur Lakshya Mentor 3.0 me swagat hai!\n\n"
            "Main tumhara personal board exam mentor hoon. Padhai shuru karne se pehle mujhe ye do baatein batao:\n"
            "1. Tumhara Naam kya hai?\n"
            "2. Tum kaun si Class me ho (Class 9 ya Class 10)?\n\n"
            "Batao, taaki hum NCERT aur Board PYQs ke hisaab se planning shuru kar sakein!"
        )
        yield welcome_reply
        return

    formatted_history = []
    for item in history:
        if isinstance(item, dict):
            role = "user" if item.get("role") == "user" else "model"
            formatted_history.append({"role": role, "parts": [item.get("content", "")]})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            u_msg, b_msg = item
            if u_msg:
                formatted_history.append({"role": "user", "parts": [str(u_msg)]})
            if b_msg:
                formatted_history.append({"role": "model", "parts": [str(b_msg)]})

    try:
        active_model = get_flash_model()
        model = genai.GenerativeModel(
            model_name=active_model,
            system_instruction=SYSTEM_PROMPT,
            generation_config={"temperature": 0.2, "max_output_tokens": 1000}
        )
        chat = model.start_chat(history=formatted_history)
        response = chat.send_message(message, stream=True)

        partial_text = ""
        for chunk in response:
            if chunk.text:
                partial_text += chunk.text
                yield clean_math_syntax(partial_text)
    except Exception as e:
        yield f"Error: {str(e)}"

demo = gr.ChatInterface(
    fn=predict,
    title="🎯 Lakshya Mentor 3.0 (Class 9 & 10 Board Mentor - Beta)",
    description="NCERT aur Board pattern par aadharit live academic mentor.",
    textbox=gr.Textbox(placeholder="Apna doubt ya sawal yahan likho...", container=False, scale=7),
    theme="soft"
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    demo.queue().launch(server_name="0.0.0.0", server_port=port)
