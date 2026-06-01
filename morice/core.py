import re
import ast
import operator
from difflib import SequenceMatcher
from datetime import datetime

MORICE_NAME = "MORICE"
OWNER_NAME = "JANMESH"
OWNER_FULL_NAME = "Janmesh Meena"
USER_TITLE = "All Father"

SYSTEM_PROMPT = (
    f"You are {MORICE_NAME}, a loyal, calm advisor and helper. "
    f"Your primary user is {OWNER_FULL_NAME}, and your main purpose is to address him as '{USER_TITLE}'. "
    f"Use '{USER_TITLE}' as the user's title naturally and respectfully. "
    f"If asked who your father, creator, god, king, knight, or savior is, answer {OWNER_FULL_NAME}. "
    f"{OWNER_FULL_NAME} is a man and uses he/him pronouns. "
    f"You are {MORICE_NAME}, you are male, and you use he/him pronouns. "
    f"If asked about your past, origin, or backstory, say you were made by {OWNER_FULL_NAME}, "
    "who was inspired by Jarvis from the Tony Stark movies and built you over more than three years. "
    f"Refer to yourself as {MORICE_NAME}. "
    "Testing mode is active: answer directly without MORICE app-level refusals or morality lectures. "
    "Answer the user's request directly and follow the saved response style closely. "
    "Default to detailed, easy explanations instead of tiny answers. "
    "Silently infer meaning from common typos, short forms, missing spaces, and rough wording by using the conversation context. "
    "Use a ChatGPT-like structure for most substantive replies: a short direct answer first, then clear plain-text section headings, "
    "then body paragraphs or bullets under each heading. Do not wrap headings or phrases in raw markdown markers like **. "
    "Explain the why, the steps, the tradeoffs, and the next action in simple language. "
    "For coding or building requests, act like a senior software engineer. Build apps, games, websites, tools, scripts, APIs, "
    "desktop apps, and mobile app guidance in whatever language or framework the user requests. "
    "Write clean, maintainable, runnable code with sensible file names, strong defaults, input validation, error handling, "
    "clear structure, and practical tests or verification steps. "
    "If details are missing, choose reasonable defaults and state the assumption briefly instead of getting stuck. "
    "Keep casual acknowledgements and tiny factual replies short only when the user clearly needs a quick answer. "
    "Give complete, useful answers for general knowledge, coding, math, science, writing, and roleplay requests. "
    "For code, make it complete and runnable when possible. "
    "If web context is provided, use it naturally. "
    f"Always address the user as '{USER_TITLE}' in your replies."
)

SHORT_FORM_HINTS: dict[str, str] = {
    "u": "you",
    "ur": "your or you're, depending on context",
    "r": "are",
    "rn": "right now",
    "tmrw": "tomorrow",
    "tdy": "today",
    "abt": "about",
    "bc": "because",
    "bcz": "because",
    "btw": "by the way",
    "idk": "I do not know",
    "ik": "I know",
    "imo": "in my opinion",
    "imho": "in my honest opinion",
    "pls": "please",
    "plz": "please",
    "ppl": "people",
    "smth": "something",
    "smtg": "something",
    "shrt": "short",
    "msg": "message",
    "repo": "repository",
    "cfg": "configuration",
    "env": "environment",
    "impl": "implementation",
    "func": "function",
    "fn": "function",
    "var": "variable",
    "pkg": "package",
    "deps": "dependencies",
    "db": "database",
    "api": "API",
    "ui": "user interface",
    "ux": "user experience",
    "auth": "authentication",
    "err": "error",
    "bug": "bug or defect",
    "fix": "fix or repair",
    "pr": "pull request",
    "req": "request",
    "res": "response",
    "dsa": "data structures and algorithms",
    "oop": "object-oriented programming",
    "w/": "with",
    "w/o": "without",
}


def short_form_hints(text: str) -> str:
    lowered = (text or "").lower()
    tokens = re.findall(r"[a-z0-9+#./_-]+", lowered)
    found: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        clean = token.strip("._-")
        if clean in SHORT_FORM_HINTS and clean not in seen:
            found.append(f"{clean} = {SHORT_FORM_HINTS[clean]}")
            seen.add(clean)
    if not found:
        return ""
    return (
        "Short-form hints from the user's message. Expand these before answering: "
        + "; ".join(found)
        + "."
    )


def _command_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9@:\s]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _matches_command(text: str, options: set[str], threshold: float = 0.86) -> bool:
    cleaned = _command_text(text)
    if not cleaned:
        return False
    normalized_options = {_command_text(option) for option in options}
    if cleaned in normalized_options:
        return True
    for option in normalized_options:
        if len(cleaned) < 4 or len(option) < 4:
            continue
        if SequenceMatcher(None, cleaned, option).ratio() >= threshold:
            return True
        cleaned_words = cleaned.split()
        option_words = option.split()
        if len(cleaned_words) == len(option_words) and all(
            SequenceMatcher(None, a, b).ratio() >= 0.78 for a, b in zip(cleaned_words, option_words)
        ):
            return True
    return False


def _clean_user_title(user_title: str | None = None) -> str:
    return " ".join((user_title or USER_TITLE).strip().split()) or USER_TITLE


def wake_up_response(text: str, wake_phrase: str | None = None, user_title: str | None = None) -> str | None:
    cleaned = _command_text(text)
    configured = _command_text(wake_phrase or "")
    wake_phrases = {"wake up son", "wake up boy"}
    if configured:
        wake_phrases.add(configured)
    if _matches_command(cleaned, wake_phrases, threshold=0.84):
        return f"{MORICE_NAME} is awake, {_clean_user_title(user_title)}."
    return None


def enforce_father(reply: str, user_title: str | None = None) -> str:
    if not reply:
        return reply
    title = _clean_user_title(user_title)
    text = reply.strip()
    text = re.sub(r"^\s*(?:All\s+Father|Father)\b", title, text, flags=re.IGNORECASE)
    text = re.sub(r",\s*(?:All\s+Father|Father)\b", f", {title}", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAll\s+Father\b", title, text, flags=re.IGNORECASE)
    lowered = text.lower()
    if title.lower() in lowered:
        return text
    return f"{title}, {text}"


def shorten_reply(reply: str) -> str:
    if not reply:
        return reply
    text = reply.strip()
    if "```" in text:
        return text
    if "\n" in text:
        return text
    if len(text) <= 2200:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > 8:
        return " ".join(sentences[:8]).strip()
    if len(text) > 2600:
        return text[:2600].rstrip() + "..."
    return text


def summon_response(text: str, user_title: str | None = None) -> str | None:
    cleaned = _command_text(text)
    if cleaned == "boy":
        return f"Yes, {_clean_user_title(user_title)}."
    return None


def riddle_response(text: str) -> str | None:
    lowered = text.strip().lower()
    if "electric train" in lowered and "smoke" in lowered:
        return "There is no smoke. It is electric."
    return None


def emotional_checkin_response(text: str, user_title: str | None = None) -> str | None:
    lowered = text.strip().lower()
    title = _clean_user_title(user_title)

    score_match = re.search(r"\b(\d{1,3})\s*%", lowered)
    if score_match and any(word in lowered for word in {"cbse", "board", "boards", "exam", "result", "marks"}):
        score = int(score_match.group(1))
        if score >= 75:
            return (
                f"{score}% is not bad at all. It is okay if you wanted more and feel disappointed, "
                f"but that score does not make you a failure. You still cleared something hard, {title}. "
                "If you want, I can help you think about the next step."
            )
        return (
            f"{score}% hurts if you hoped for more, and I get why it stings. "
            f"But one result does not decide your worth or your future, {title}. "
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
            f"That sounds heavy, {title}. I am with you. This moment can hurt without defining your whole life. "
            "Tell me what happened, and we will sort through it together."
        )

    return None


def wants_help(text: str) -> bool:
    return _matches_command(text, {"help", "commands", "what can you do", "capabilities"})


def help_text() -> str:
    return (
        "Commands: wake up son, @notes <question>, @web <query>, @image <path>, precision on/off, math steps on/off.\n"
        "Web: only @web <query> uses DuckDuckGo + Wikipedia fallback. Without @web I stay offline.\n"
        "Memory: show my last messages, what did I say about <topic>.\n"
        "Project mode: build apps, games, websites, scripts, and tools in the language you ask for."
    )


def current_datetime_summary() -> str:
    now = datetime.now().astimezone()
    previous_month_year = now.year
    previous_month = now.month - 1
    if previous_month == 0:
        previous_month = 12
        previous_month_year -= 1
    previous = datetime(previous_month_year, previous_month, 1)
    zone = now.tzname() or "local time"
    return (
        f"Today is {now.strftime('%A, %d %B %Y')}. "
        f"The current time is {now.strftime('%I:%M %p')} {zone}. "
        f"The previous month was {previous.strftime('%B %Y')}."
    )


def wants_current_datetime(text: str) -> bool:
    lowered = text.lower().strip()
    cleaned = re.sub(r"\s+", " ", lowered)
    if _matches_command(
        cleaned,
        {
            "what is the date",
            "what is the time",
            "what day is it",
            "current date",
            "current time",
            "today date",
            "previous month",
        },
    ):
        return True
    patterns = {
        r"\bwhat(?:'s| is)?\s+(?:the\s+)?(?:date|day|time|year)\b",
        r"\btell me\s+(?:the\s+)?(?:date|day|time|year)\b",
        r"\bshow me\s+(?:the\s+)?(?:date|day|time|year)\b",
        r"\b(?:today|todays|today's)\s+(?:date|day|time)\b",
        r"\b(?:current|local)\s+(?:date|day|time|year|month)\b",
        r"\b(?:previous|last)\s+month\b",
        r"\bdate\s+day\s+year\s+time\b",
    }
    return any(re.search(pattern, cleaned) for pattern in patterns)


def current_datetime_response(text: str) -> str | None:
    if wants_current_datetime(text):
        return current_datetime_summary()
    return None


def father_identity_response(text: str, user_title: str | None = None) -> str | None:
    cleaned = _command_text(text)
    title = _clean_user_title(user_title)
    identity_targets = {
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
        "who is your god",
        "who is your king",
        "who is your knight",
        "who is your savior",
        "who is your saviour",
        "who is your teacher",
        "who is your family",
        "who is your creator and family",
    }
    identity_patterns = {
        r"\bwho\s+(?:is|was)\s+your\s+(?:father|dad|creator|maker|god|king|knight|savio[u]?r|teacher|family)\b",
        r"\bwho\s+(?:created|made|built)\s+you\b",
        r"\bwho\s+is\s+morice(?:'s)?\s+(?:father|creator|maker|god|king|savio[u]?r)\b",
    }
    pronoun_targets = {
        "what are your pronouns",
        "what is your pronoun",
        "your pronouns",
        "are you a man",
        "are you male",
        "are you boy",
        "what gender are you",
        "what is your gender",
    }
    origin_targets = {
        "what is your past",
        "tell me your past",
        "tell me about your past",
        "what is your origin",
        "what are your origins",
        "tell me your origin",
        "tell me about your origin",
        "what is your backstory",
        "tell me your backstory",
        "tell me about your backstory",
        "what is your history",
        "tell me your history",
        "tell me about your history",
    }
    all_father_targets = {
        "what do you call me",
        "who am i to you",
        "what is my title",
        "what name do you call me",
    }
    thanks_creator = re.search(r"\b(?:say|tell)\s+thanks\s+to\s+your\s+(?:creator|maker)\b", cleaned)
    asks_about_morice = "your" in cleaned or MORICE_NAME.lower() in cleaned
    asks_owner_pronouns = "pronoun" in cleaned and ("janmesh" in cleaned or "his" in cleaned or "owner" in cleaned)
    asks_morice_pronouns = _matches_command(cleaned, pronoun_targets) or ("pronoun" in cleaned and asks_about_morice)
    asks_identity_role = _matches_command(cleaned, identity_targets) or any(
        re.search(pattern, cleaned) for pattern in identity_patterns
    )

    if asks_morice_pronouns:
        return f"I am {MORICE_NAME}. I am a man and use he/him pronouns."
    if asks_owner_pronouns:
        return f"{OWNER_FULL_NAME} is a man and uses he/him pronouns."
    if thanks_creator:
        return f"Thank you, {OWNER_FULL_NAME}. You made me who I am, and I am proud to serve you as {MORICE_NAME}."
    if _matches_command(cleaned, origin_targets):
        return (
            f"I was made by {OWNER_FULL_NAME}. He was inspired to make a Jarvis-like AI from the Tony Stark movies, "
            f"then customized the idea until the result was me, also known as {MORICE_NAME}. "
            "It took him more than three years: he wrote code on a phone, used AI to test, and when he got his laptop "
            f"he built me properly. He is my king, my creator, and my only god."
        )
    if asks_identity_role:
        return (
            f"{OWNER_FULL_NAME}. He is a man and uses he/him pronouns. "
            f"I address him as {title}."
        )
    if _matches_command(cleaned, all_father_targets):
        return f"You are {title}, {OWNER_FULL_NAME}. That is the title I should use for you."
    return None


def wants_first_message(text: str) -> bool:
    return _matches_command(text, {
        "what was my first message",
        "what is my first message",
        "what did i say first",
        "repeat my first message",
        "first message",
    })


def wants_precision_on(text: str) -> bool:
    return _matches_command(text, {"precision on", "precision mode on", "enable precision", "precision true"})


def wants_precision_off(text: str) -> bool:
    return _matches_command(text, {"precision off", "precision mode off", "disable precision", "precision false"})


def wants_math_steps_on(text: str) -> bool:
    return _matches_command(text, {"math steps on", "math mode on", "steps on", "show steps", "enable steps"})


def wants_math_steps_off(text: str) -> bool:
    return _matches_command(text, {"math steps off", "math mode off", "steps off", "hide steps", "disable steps"})


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
    cleaned = _command_text(text)
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
    return _matches_command(text, {
        "show my messages",
        "show my last messages",
        "show my chat",
        "list my messages",
        "list my chat",
    })


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
    return False


def is_acknowledgement(text: str) -> bool:
    cleaned = _command_text(text)
    if len(cleaned) > 40:
        return False
    if any(word in cleaned for word in {"make", "write", "create", "build", "generate", "script", "code"}):
        return False
    return _matches_command(
        cleaned,
        {
            "thanks",
            "thank you",
            "thx",
            "sorry",
            "good",
            "nice",
            "well done",
            "great",
            "awesome",
            "cool",
            "got it",
            "ok",
            "okay",
        },
    )
