"""Device mentions in engineering prose never authorize remote tasks."""
import pytest

from morice.node_intents import is_node_command, mentions_device


@pytest.mark.parametrize('text',[
    'Evaluate a battery-powered tabletop generator.',
    'Explain tablet battery chemistry.',
    'Compare the phone battery with our generator output.',
    'An engineering audit of ARC: inspect the motor, battery and tablet interface.',
    '# PROJECT ARC-0.3\nAct as an independent engineering team.\n' + 'Tabletop battery generator assumptions. '*30,
])
def test_engineering_and_explanatory_requests_are_not_device_commands(text):
    assert not is_node_command(text, ('ARC','Phone'))


@pytest.mark.parametrize('text',[
    'What is my phone battery?', 'What is the battery level on my phone?',
    'Is my phone charging?', 'Please pause playback on my tablet.',
    'Set the volume on my phone to 40 percent.', 'Open Chrome on my phone.',
    'Could you take a photo with my tablet?', 'Check Phone One status',
])
def test_explicit_device_commands_and_status_queries_still_match(text):
    assert is_node_command(text, ('Phone One',))


def test_device_references_use_word_boundaries():
    assert not mentions_device('tabletop battery generator','tablet')
    assert not mentions_device('department report','art')
    assert mentions_device('open chrome on my tablet','tablet')
    assert mentions_device('check Phone One status','Phone One')
