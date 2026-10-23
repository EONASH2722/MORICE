"""Content words must not replace a substantive request with a canned reply."""
from unittest.mock import patch

import pytest

from morice.core import emotional_checkin_response, wants_model_identity
from morice.llm_client import _friendly_backend_reply
from morice.capabilities import detect_capability_topic
from morice.conversation import wants_previous_user_message


ENGINEERING_PROMPT = """Independent engineering audit
You are an engineering advisor. Independently calculate the performance of a
vibration energy harvester. Use your mathematical model to check the results.
The converter is 70% efficient. Distinguish mechanical losses from electrical
loading and show results in milliwatts. An earlier AI model claimed too much.
Explain the assumptions and what measurements would be needed to validate them.
Do not generate code or a PDF. Give calculations and an engineering verdict.
"""


@pytest.mark.parametrize('text', [
    ENGINEERING_PROMPT,
    'Efficiency is 70%. Show the results.',
    'For example, the converter is 70% efficient.',
    'I got 70% efficiency in benchmark results. Explain the losses.',
    'My model scored 70% in the benchmark. Analyze its errors.',
    'I failed to compile the project. Help debug the error.',
    'Translate "I am sad" into French.',
    'Write a scene where I say "I feel worthless" after an exam.',
    'My experiment shows 70% efficiency; report the results.',
    'I got 170% in the exam.',
])
def test_technical_and_quoted_content_is_not_an_emotional_shortcut(text):
    assert emotional_checkin_response(text, 'Sir') is None


@pytest.mark.parametrize('text', [
    'I scored 70% in my exams and feel disappointed.',
    'I got 85% in CBSE boards.',
    'My exam result was 70%.',
    'I feel sad.',
    "I'm stressed about tomorrow.",
    'I failed my physics exam.',
])
def test_brief_personal_checkins_still_work(text):
    assert emotional_checkin_response(text, 'Sir')


@pytest.mark.parametrize('text', [
    ENGINEERING_PROMPT,
    'Explain how you would model a spring with 70% efficiency and report results.',
    'What model are you using to calculate electromagnetic damping?',
    'Which engine are you using to model the heat exchanger?',
    'Build your own AI model for classifying samples.',
])
def test_other_models_are_not_assistant_identity_questions(text):
    assert not wants_model_identity(text)


@pytest.mark.parametrize('text', [
    'What model are you?',
    'Which AI model are you using?',
    'which moderl are you currently running on boy',
    'what is your AI engine?',
])
def test_direct_assistant_model_questions_still_work(text):
    assert wants_model_identity(text)


def test_backend_failure_on_an_engineering_prompt_is_not_exam_consolation():
    with patch('morice.llm_client.address_message', side_effect=lambda text: text):
        reply = _friendly_backend_reply(ENGINEERING_PROMPT, 'selected-model', None)
    assert 'local model stumbled' in reply
    assert '70% hurts' not in reply


def test_embedded_capability_questions_do_not_replace_an_audit():
    prompt = ENGINEERING_PROMPT + '\nExplain what features you can build into the proposed device.'
    assert detect_capability_topic(prompt) is None


def test_references_to_an_earlier_model_are_context_not_a_recall_command():
    prompt = ENGINEERING_PROMPT + '\nI asked an earlier model for advice. Show what was wrong with its response.'
    assert not wants_previous_user_message(prompt)
    assert wants_previous_user_message('what did i say in my previos mesage')


@pytest.mark.parametrize('text',[
    ENGINEERING_PROMPT,
    'Explain scientific research on electromagnetic induction.',
    'Compare these assumptions with experimental measurements.',
    'Explain a simple everyday idea in two paragraphs.',
    'Independent engineering audit\n\nAssess mechanical suspension and numerical simulation.'*10,
])
def test_written_analysis_is_not_an_empty_research_project_or_a_renderer(text):
    from morice.research.service import research_intent
    from morice.visualization import VisualizationManager
    assert not research_intent(text)
    manager=VisualizationManager()
    try:assert manager.decide(text) is None
    finally:manager.shutdown()


@pytest.mark.parametrize('text',[
    'Analyze this dataset', 'Research energy harvesting', 'Calculate: energy',
    'List research projects', 'New research: a controlled experiment',
    '```calculation\n{"expression":"2+2"}\n```',
])
def test_explicit_research_operations_remain_available(text):
    from morice.research.service import research_intent
    assert research_intent(text)
