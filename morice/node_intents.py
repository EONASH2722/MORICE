"""Recognize explicit remote-device commands without scanning unrelated prose."""
from __future__ import annotations

import re


def mentions_device(text: str, reference: str) -> bool:
    return bool(reference and re.search(r'(?<!\w)' + re.escape(reference.casefold()) + r'(?!\w)', text.casefold()))


def is_node_command(text: str, device_names=()) -> bool:
    clean = ' '.join(str(text or '').casefold().split()).strip(' .!?')
    if not clean or len(clean) > 500:
        return False
    clean = re.sub(r'^(?:(?:morice[, ]+)|(?:please\s+)|(?:(?:can|could|would) you\s+))+', '', clean)
    references = ('phone', 'android', 'tablet', *device_names)
    if not any(mentions_device(clean, name) for name in references):
        return False
    # A named device or a word such as "battery" inside an explanation is not
    # authority to run a device task. Require a direct command or status query.
    if re.match(r'^(?:open|set|turn|change|adjust|lower|raise|increase|decrease|pause|resume|play|next|skip|previous|take|capture|snap|use|mute|unmute|send|receive|transfer|install|run|start|stop|record|close)\b', clean):
        return True
    reference = r'(?:my |the )?(?:' + '|'.join(re.escape(name.casefold()) for name in references if name) + r')'
    status = r'(?:battery(?: (?:level|percentage|percent|status))?|device status|phone status|status)'
    return any(re.fullmatch(pattern, clean) for pattern in (
        rf"(?:what(?:'s| is)|show|check|tell me) (?:the )?{status} (?:of|on|for) {reference}",
        rf"(?:what(?:'s| is)|show|check|tell me) {reference}(?:'s)? {status}",
        rf'how much battery(?: is)? (?:left|remaining) (?:on|in) {reference}',
        rf'(?:is )?{reference} charging',
        rf'{reference}(?:\'s)? {status}',
    ))
