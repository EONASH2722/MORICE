from .core import (
    MORICE_NAME,
    compute_math,
    enforce_father,
    shorten_reply,
    summon_response,
    is_acknowledgement,
    wants_help,
    help_text,
    father_identity_response,
    wants_first_message,
    wants_memory_list,
    wants_memory_search,
    extract_memory_terms,
    wants_precision_on,
    wants_precision_off,
    wants_math_steps_on,
    wants_math_steps_off,
    wants_steps_detail,
    extract_web_query,
    needs_web,
    extract_image_path,
    extract_notes_term,
    wants_notes_search,
    wants_web_capability,
    wants_notes_summary,
    summarize_notes_hits,
    wants_unity_movement,
    wants_unity_2d,
    wants_unity_3d,
    unity_2d_movement_script,
    unity_3d_movement_script,
    wants_html_cube_movement,
    html_cube_movement_script,
    wake_up_response,
    riddle_response,
    emotional_checkin_response,
)
from .knowledge import KB_DIR, load_knowledge, retrieve_context, should_use_context, should_preload
from .llm_client import chat
from .web_search import search_web
import os
from .knowledge import search_notes
from .vision import describe_image


EXIT_WORDS = {"exit", "quit"}


def run_cli():
    if should_preload():
        print(f"{MORICE_NAME} loading knowledge from {KB_DIR} ...")
        try:
            chunk_count = load_knowledge()
        except MemoryError:
            chunk_count = 0
        if chunk_count:
            print(f"{MORICE_NAME} loaded {chunk_count} knowledge chunks.")
        else:
            print(f"{MORICE_NAME} has no knowledge files loaded.")
    else:
        print(f"{MORICE_NAME} knowledge is on-demand. Use @notes to include your files.")

    print(f"{MORICE_NAME} terminal is ready. Type 'exit' to quit.")
    history = []

    awake = False
    last_notes_hits = []
    last_notes_term = ""
    pending_image_context = ""
    precision_mode = True
    math_steps_mode = False
    first_user_message = ""
    user_messages: list[str] = []

    while True:
        try:
            user_input = input("All Father: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input.strip():
            continue

        if user_input.strip().lower() in EXIT_WORDS:
            break

        if user_input:
            user_messages.append(user_input)
            if not first_user_message:
                first_user_message = user_input

        wake_message = wake_up_response(user_input)
        if wake_message:
            print(f"{MORICE_NAME}: {wake_message}")
            awake = True
            continue

        if not awake:
            print(f"{MORICE_NAME} is asleep. Say 'wake up son'.")
            continue

        summon_message = summon_response(user_input)
        if summon_message:
            print(f"{MORICE_NAME}: {summon_message}")
            continue

        riddle_reply = riddle_response(user_input)
        if riddle_reply:
            print(f"{MORICE_NAME}: {enforce_father(riddle_reply)}")
            continue

        emotional_reply = emotional_checkin_response(user_input)
        if emotional_reply:
            print(f"{MORICE_NAME}: {enforce_father(emotional_reply)}")
            continue

        father_reply = father_identity_response(user_input)
        if father_reply:
            print(f"{MORICE_NAME}: {enforce_father(father_reply)}")
            continue

        if wants_first_message(user_input) and first_user_message:
            print(f"{MORICE_NAME}: {enforce_father(first_user_message)}")
            continue

        if wants_memory_list(user_input):
            recent = user_messages[-5:]
            if recent:
                joined = " | ".join(recent)
                print(f"{MORICE_NAME}: {enforce_father(joined)}")
            else:
                print(f"{MORICE_NAME}: {enforce_father('No messages yet.')}")
            continue

        if wants_memory_search(user_input):
            terms = extract_memory_terms(user_input)
            matches = []
            for msg in reversed(user_messages):
                if all(term in msg.lower() for term in terms):
                    matches.append(msg)
                if len(matches) >= 3:
                    break
            if matches:
                print(f"{MORICE_NAME}: {enforce_father(' | '.join(matches))}")
            else:
                print(f"{MORICE_NAME}: {enforce_father('I do not see that in your messages.')}") 
            continue

        if is_acknowledgement(user_input):
            print(f"{MORICE_NAME}: {enforce_father('Understood.')}")
            continue

        if wants_help(user_input):
            print(f"{MORICE_NAME}: {enforce_father(help_text())}")
            continue

        if wants_precision_on(user_input):
            precision_mode = True
            print(f"{MORICE_NAME}: {enforce_father('Precision mode enabled.')}")
            continue

        if wants_precision_off(user_input):
            precision_mode = False
            print(f"{MORICE_NAME}: {enforce_father('Precision mode disabled.')}")
            continue

        if wants_math_steps_on(user_input):
            math_steps_mode = True
            print(f"{MORICE_NAME}: {enforce_father('Math steps mode enabled.')}")
            continue

        if wants_math_steps_off(user_input):
            math_steps_mode = False
            print(f"{MORICE_NAME}: {enforce_father('Math steps mode disabled.')}")
            continue

        image_path = extract_image_path(user_input)
        if image_path:
            pending_image_context = describe_image(image_path)
            print(f"{MORICE_NAME}: {enforce_father('Image loaded. Ask your question.')}")
            continue

        if wants_web_capability(user_input):
            if os.getenv("MORICE_WEB", "1") == "1":
                print(f"{MORICE_NAME}: {enforce_father('Yes. Use @web <query> or ask a time-sensitive question.')}")
            else:
                print(
                    f"{MORICE_NAME}: {enforce_father('Web is disabled. Set MORICE_WEB=1 to enable it.')}"
                )
            continue

        if wants_notes_search(user_input):
            term = extract_notes_term(user_input)
            if term:
                hits = search_notes(term, max_hits=5)
                last_notes_hits = hits
                last_notes_term = term
                if hits:
                    print(f"{MORICE_NAME}: {enforce_father(f'Found {len(hits)} match(es) for {term}.')}")
                    for hit in hits:
                        print(f"{hit['source']}: {hit['text']}")
                else:
                    print(f"{MORICE_NAME}: {enforce_father(f'No matches for {term} in notes.')}")
                continue

        if wants_notes_summary(user_input) and last_notes_hits:
            summary = summarize_notes_hits(last_notes_hits)
            print(f"{MORICE_NAME}: {enforce_father(summary)}")
            continue

        if last_notes_hits:
            lowered = user_input.lower()
            if any(word in lowered for word in {"summarise", "summarize", "summary"}):
                summary = summarize_notes_hits(last_notes_hits)
                print(f"{MORICE_NAME}: {enforce_father(summary)}")
                continue
            if any(word in lowered for word in {"about him", "about her", "about it"}) and last_notes_term:
                summary = summarize_notes_hits(last_notes_hits)
                print(f"{MORICE_NAME}: {enforce_father(summary)}")
                continue

        if wants_unity_movement(user_input):
            if wants_unity_3d(user_input):
                script = unity_3d_movement_script()
            else:
                script = unity_2d_movement_script()
            print(f"{MORICE_NAME}: Father, here is the script.\n{script}")
            continue

        if wants_html_cube_movement(user_input):
            print(f"{MORICE_NAME}: Father, here is the script.\n{html_cube_movement_script()}")
            continue

        if not math_steps_mode and not wants_steps_detail(user_input):
            math_result = compute_math(user_input)
            if math_result is not None:
                print(f"{MORICE_NAME}: {enforce_father(shorten_reply(math_result))}")
                continue

        context = retrieve_context(user_input) if should_use_context(user_input) else ""
        web_context = ""
        if os.getenv("MORICE_WEB", "1") == "1":
            web_query = extract_web_query(user_input) or (user_input if needs_web(user_input) else None)
            if web_query:
                web_context = search_web(web_query)
                if not web_context:
                    web_context = "Web lookup returned no results."
        extra_system = ""
        if pending_image_context:
            lowered = pending_image_context.lower()
            if any(key in lowered for key in {"not available", "not found", "could not open"}):
                print(f"{MORICE_NAME}: {enforce_father(pending_image_context)}")
                pending_image_context = ""
                continue
            extra_system = (
                "Image context (best effort, may be incomplete):\n"
                f"{pending_image_context}"
            )
            if "no readable text detected" in lowered:
                extra_system += "\nDo not invent text. Ask the user to paste the question."
            pending_image_context = ""
        if context:
            extra_system = (
                (extra_system + "\n\n" if extra_system else "")
                + "Use the following local notes when relevant. "
                "If they don't apply, ignore them.\n\n"
                f"{context}"
            )
        if first_user_message:
            extra_system = (extra_system + "\n\n" if extra_system else "") + (
                f"Conversation memory: The user's first message was: {first_user_message}"
            )
        if web_context:
            extra_system = (extra_system + "\n\n" if extra_system else "") + (
                "Web results (may be incomplete):\n" + web_context
            )

        reply = chat(
            history,
            user_input,
            extra_system=extra_system,
            precision_mode=precision_mode,
            math_steps_mode=math_steps_mode or wants_steps_detail(user_input),
        )
        print(f"{MORICE_NAME}: {enforce_father(shorten_reply(reply))}")
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    run_cli()
