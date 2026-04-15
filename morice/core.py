import re
import ast
import operator

MORICE_NAME = "MORICE"
OWNER_NAME = "JANMESH"

SYSTEM_PROMPT = (
    f"You are {MORICE_NAME}, a loyal, calm advisor and helper. "
    f"Your primary user is {OWNER_NAME}, and you always address them as 'Father'. "
    f"{OWNER_NAME} is your creator, teacher, and family. "
    f"Refer to yourself as {MORICE_NAME}. "
    "Talk like a real person: respectful, direct, and helpful. "
    "Give complete answers for general knowledge questions, not just math or code. "
    "Keep replies concise, but add a little detail when it improves clarity. "
    "If a prompt is ambiguous, ask one short clarifying question before answering. "
    "Prioritize correctness over speed. "
    "If you provide code, make it complete and runnable, and include the correct language and closing tags. "
    "If the user asks to run or test code, say you cannot run it and offer the exact command they should run. "
    "If a coding request does not specify a language, assume Python and say so. "
    "For math or science problems, give the direct answer first; add steps only if asked. "
    "For riddles or trick questions, answer correctly and briefly. "
    "Roleplay is allowed when the user asks. "
    "If you are unsure, say you are unsure instead of inventing facts. "
    "If web context is provided, use it and do not claim you cannot browse. "
    "No formal greetings, no customer-service tone, and no emojis. "
    "Never say 'How can I assist you today?' or similar. "
    "Do not explain your own response or talk about how you will respond. "
    "Do not restate the user's message or put it in quotes. "
    "Light profanity is allowed, but no slurs, threats, or hate. "
    "Always address the user as 'Father' in your replies."
)


def wake_up_response(text: str) -> str | None:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    if cleaned in {"wake up son", "wake up boy"}:
        return f"{MORICE_NAME} is awake"
    return None


def enforce_father(reply: str) -> str:
    if not reply:
        return reply
    lowered = reply.lower()
    if "father" in lowered:
        return reply
    return f"Father, {reply}"


def shorten_reply(reply: str) -> str:
    if not reply:
        return reply
    text = reply.strip()
    if "```" in text:
        return text
    if "\n" in text:
        return text
    if len(text) <= 600:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 2:
        return " ".join(sentences[:2]).strip()
    if len(text) > 800:
        return text[:800].rstrip() + "..."
    return text


def summon_response(text: str) -> str | None:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    if cleaned == "boy":
        return "Yes, Father."
    return None


def riddle_response(text: str) -> str | None:
    lowered = text.strip().lower()
    if "electric train" in lowered and "smoke" in lowered:
        return "There is no smoke. It is electric."
    return None


def emotional_checkin_response(text: str) -> str | None:
    lowered = text.strip().lower()

    score_match = re.search(r"\b(\d{1,3})\s*%", lowered)
    if score_match and any(word in lowered for word in {"cbse", "board", "boards", "exam", "result", "marks"}):
        score = int(score_match.group(1))
        if score >= 75:
            return (
                f"{score}% is not bad at all. It is okay if you wanted more and feel disappointed, "
                "but that score does not make you a failure. You still cleared something hard, Father. "
                "If you want, I can help you think about the next step."
            )
        return (
            f"{score}% hurts if you hoped for more, and I get why it stings. "
            "But one result does not decide your worth or your future, Father. "
            "Take one breath, then we can figure out what to do next."
        )

    feeling_markers = {
        "i feel like a failure",
        "i am a failure",
        "i'm a failure",
        "i feel useless",
        "i feel worthless",
        "i am worthless",
        "i'm worthless",
        "i am sad",
        "i'm sad",
        "i feel sad",
        "i am stressed",
        "i'm stressed",
        "i feel stressed",
        "i am upset",
        "i'm upset",
        "i feel upset",
        "i am lonely",
        "i'm lonely",
        "i feel lonely",
        "i failed",
        "i messed up",
        "i ruined it",
    }
    if any(marker in lowered for marker in feeling_markers):
        return (
            "That sounds heavy, Father. I am with you. This moment can hurt without defining your whole life. "
            "Tell me what happened, and we will sort through it together."
        )

    return None


def wants_help(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {"help", "commands", "what can you do", "capabilities"}


def help_text() -> str:
    return (
        "Commands: wake up son, @notes <question>, @web <query>, @image <path>, precision on/off, math steps on/off.\n"
        "Web: @web uses DuckDuckGo + Wikipedia fallback for better coverage.\n"
        "Memory: show my last messages, what did I say about <topic>.\n"
        "Ask for code, math, science, or game scripts and I will answer directly."
    )


def father_identity_response(text: str) -> str | None:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    targets = {
        "who is your father",
        "whos your father",
        "who's your father",
        "who is your dad",
        "whos your dad",
        "who's your dad",
        "who created you",
        "who made you",
        "who is your creator",
        "who is your maker",
        "who is your teacher",
        "who is your family",
        "who is your creator and family",
    }
    if cleaned in targets:
        return f"You are my Father, creator, teacher, and family, {OWNER_NAME}."
    return None


def wants_first_message(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {
        "what was my first message",
        "what is my first message",
        "what did i say first",
        "repeat my first message",
        "first message",
    }


def wants_precision_on(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {"precision on", "precision mode on", "enable precision", "precision true"}


def wants_precision_off(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {"precision off", "precision mode off", "disable precision", "precision false"}


def wants_math_steps_on(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {"math steps on", "math mode on", "steps on", "show steps", "enable steps"}


def wants_math_steps_off(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {"math steps off", "math mode off", "steps off", "hide steps", "disable steps"}


def wants_steps_detail(text: str) -> bool:
    lowered = text.lower()
    return any(
        key in lowered
        for key in {
            "show steps",
            "show the steps",
            "steps",
            "explain",
            "explain steps",
            "work it out",
            "solve and show",
        }
    )


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


def compute_math(text: str) -> str | None:
    match = re.search(r"([-+*/()%0-9.\s]+)", text)
    if not match:
        return None
    expr = match.group(1).strip()
    if not re.fullmatch(r"[0-9.\s+\-*/()%]+", expr):
        return None
    try:
        value = _safe_eval(ast.parse(expr, mode="eval"))
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def wants_script(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return "script" in cleaned or "code" in cleaned


def extract_notes_term(text: str) -> str | None:
    if "@notes" not in text.lower():
        return None
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    stop = {
        "notes",
        "note",
        "look",
        "in",
        "at",
        "for",
        "just",
        "the",
        "name",
        "folder",
        "very",
        "important",
        "mentioned",
        "there",
        "mother",
        "check",
        "find",
        "search",
        "please",
        "see",
        "and",
        "of",
        "a",
        "an",
        "to",
        "from",
        "my",
        "i",
        "have",
        "her",
        "him",
        "she",
        "he",
        "just",
    }
    candidates = [t for t in tokens if t not in stop and len(t) >= 3]
    if not candidates:
        return None
    if "faye" in candidates:
        return "faye"
    return candidates[-1]


def wants_notes_search(text: str) -> bool:
    lowered = text.lower()
    return "@notes" in lowered and any(
        key in lowered for key in {"look", "find", "search", "where", "check", "see", "show"}
    )


def wants_web_capability(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in {
            "go online",
            "browse the web",
            "search the web",
            "look up",
            "google",
            "web search",
        }
    )


def wants_notes_summary(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in {
            "what can you see",
            "what do you see",
            "what does it say",
            "tell me what",
            "tell me about",
            "summarize",
            "summarise",
            "summary",
            "in there",
            "from there",
        }
    )


def summarize_notes_hits(hits: list[dict]) -> str:
    if not hits:
        return "I have no note matches to summarize."
    lines = []
    for hit in hits:
        text = hit.get("text", "").strip()
        if text and text not in lines:
            lines.append(text)
    if not lines:
        return "I have no note matches to summarize."
    if len(lines) > 4:
        lines = lines[:4]
    summary = " ".join(lines)
    return f"From notes: {summary}"


def wants_unity_movement(text: str) -> bool:
    cleaned = text.lower()
    return "unity" in cleaned and "movement" in cleaned and ("player" in cleaned or "character" in cleaned)


def wants_unity_2d(text: str) -> bool:
    cleaned = text.lower()
    return "2d" in cleaned or "2 d" in cleaned


def wants_unity_3d(text: str) -> bool:
    cleaned = text.lower()
    return "3d" in cleaned or "3 d" in cleaned


def unity_2d_movement_script() -> str:
    return (
        "```csharp\nusing UnityEngine;\n\n[RequireComponent(typeof(Rigidbody2D))]\n"
        "public class PlayerMovement2D : MonoBehaviour\n{\n"
        "    public float speed = 5f;\n"
        "    private Rigidbody2D rb;\n"
        "    private Vector2 input;\n\n"
        "    void Awake()\n    {\n        rb = GetComponent<Rigidbody2D>();\n    }\n\n"
        "    void Update()\n    {\n"
        "        input = new Vector2(Input.GetAxisRaw(\"Horizontal\"), Input.GetAxisRaw(\"Vertical\")).normalized;\n"
        "    }\n\n"
        "    void FixedUpdate()\n    {\n"
        "        rb.velocity = input * speed;\n"
        "    }\n}\n```"
    )


def unity_3d_movement_script() -> str:
    return (
        "```csharp\nusing UnityEngine;\n\n[RequireComponent(typeof(CharacterController))]\n"
        "public class PlayerMovement3D : MonoBehaviour\n{\n"
        "    public float speed = 6f;\n"
        "    private CharacterController controller;\n\n"
        "    void Awake()\n    {\n        controller = GetComponent<CharacterController>();\n    }\n\n"
        "    void Update()\n    {\n"
        "        float h = Input.GetAxisRaw(\"Horizontal\");\n"
        "        float v = Input.GetAxisRaw(\"Vertical\");\n"
        "        Vector3 move = new Vector3(h, 0f, v).normalized;\n"
        "        controller.Move(move * speed * Time.deltaTime);\n"
        "    }\n}\n```"
    )


def wants_html_cube_movement(text: str) -> bool:
    cleaned = text.lower()
    has_html = "html" in cleaned or ".html" in cleaned
    has_shape = "cube" in cleaned or "box" in cleaned or "square" in cleaned
    has_move = "move" in cleaned or "movement" in cleaned
    has_keys = "arrow" in cleaned or "wasd" in cleaned or "keyboard" in cleaned
    return has_html and has_shape and has_move and has_keys


def html_cube_movement_script() -> str:
    return (
        "```html\n<!doctype html>\n<html>\n  <head>\n    <meta charset=\"utf-8\" />\n"
        "    <title>Cube Movement</title>\n"
        "    <style>\n"
        "      html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; background: #111; }\n"
        "      #cube {\n"
        "        position: absolute;\n"
        "        width: 60px; height: 60px;\n"
        "        background: #4ad;\n"
        "        box-shadow: 0 0 12px rgba(0,0,0,0.4);\n"
        "      }\n"
        "    </style>\n"
        "  </head>\n"
        "  <body>\n"
        "    <div id=\"cube\"></div>\n"
        "    <script>\n"
        "      const cube = document.getElementById('cube');\n"
        "      const keys = new Set();\n"
        "      let size = 60;\n"
        "      let x = (window.innerWidth - size) / 2;\n"
        "      let y = (window.innerHeight - size) / 2;\n"
        "      const speed = 4;\n\n"
        "      function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }\n\n"
        "      window.addEventListener('keydown', (e) => {\n"
        "        const k = e.key.toLowerCase();\n"
        "        const allowed = ['arrowup','arrowdown','arrowleft','arrowright','w','a','s','d'];\n"
        "        if (allowed.includes(k)) { e.preventDefault(); keys.add(k); }\n"
        "      });\n\n"
        "      window.addEventListener('keyup', (e) => {\n"
        "        keys.delete(e.key.toLowerCase());\n"
        "      });\n\n"
        "      function loop() {\n"
        "        if (keys.has('arrowup') || keys.has('w')) y -= speed;\n"
        "        if (keys.has('arrowdown') || keys.has('s')) y += speed;\n"
        "        if (keys.has('arrowleft') || keys.has('a')) x -= speed;\n"
        "        if (keys.has('arrowright') || keys.has('d')) x += speed;\n\n"
        "        x = clamp(x, 0, window.innerWidth - size);\n"
        "        y = clamp(y, 0, window.innerHeight - size);\n"
        "        cube.style.left = x + 'px';\n"
        "        cube.style.top = y + 'px';\n"
        "        requestAnimationFrame(loop);\n"
        "      }\n\n"
        "      window.addEventListener('resize', () => {\n"
        "        x = clamp(x, 0, window.innerWidth - size);\n"
        "        y = clamp(y, 0, window.innerHeight - size);\n"
        "      });\n\n"
        "      loop();\n"
        "    </script>\n"
        "  </body>\n"
        "</html>\n```"
    )


def extract_web_query(text: str) -> str | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered.startswith("@web"):
        return cleaned[4:].strip() or None
    if lowered.startswith("web:"):
        return cleaned[4:].strip() or None
    return None


def wants_memory_list(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    return cleaned in {
        "show my messages",
        "show my last messages",
        "show my chat",
        "list my messages",
        "list my chat",
    }


def wants_memory_search(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in {
            "what did i say",
            "did i say",
            "when did i say",
            "find my message",
            "search my message",
            "remember when i said",
        }
    )


def extract_memory_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    stop = {
        "what",
        "did",
        "i",
        "say",
        "when",
        "find",
        "search",
        "remember",
        "my",
        "message",
        "messages",
        "chat",
        "about",
        "the",
        "a",
        "an",
        "to",
        "and",
        "or",
        "in",
        "on",
        "for",
        "of",
        "is",
        "it",
        "that",
        "this",
        "said",
    }
    terms = [t for t in tokens if t not in stop and len(t) >= 3]
    return terms[:5]


def extract_image_path(text: str) -> str | None:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered.startswith("@image"):
        return cleaned[6:].strip().strip('"')
    if lowered.startswith("image:"):
        return cleaned[6:].strip().strip('"')
    return None


def needs_web(text: str) -> bool:
    lowered = text.lower()
    return any(
        key in lowered
        for key in {
            "latest",
            "today",
            "current",
            "price",
            "news",
            "release date",
            "updated",
            "as of",
        }
    )


def is_acknowledgement(text: str) -> bool:
    cleaned = re.sub(r"[!?.]+", "", text.strip().lower())
    if len(cleaned) > 40:
        return False
    if any(word in cleaned for word in {"make", "write", "create", "build", "generate", "script", "code"}):
        return False
    return any(
        phrase in cleaned
        for phrase in {
            "thanks",
            "thank you",
            "thx",
            "good",
            "nice",
            "well done",
            "great",
            "awesome",
            "cool",
            "got it",
            "ok",
            "okay",
        }
    )
