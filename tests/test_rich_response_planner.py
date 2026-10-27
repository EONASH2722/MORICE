"""Presentation follows actual outputs and leaves simple conversation untouched."""
from morice.nlui.contracts import ActiveContext,NaturalLanguageResult
from morice.rich_response.planner import ResponsePlanner,parse_user_table,numeric_columns


def test_trivial_answers_and_generated_numerical_claims_do_not_become_verified_cards():
    planner=ResponsePlanner()
    for message in ({'role':'user','content':'What is 5 + 5?','message_id':'u'},
        {'role':'assistant','content':'A made-up benchmark: 9999 tests passed.','message_id':'a'}):
        assert planner.from_user_message(message,'chat') is None
    assert planner.from_nlui(NaturalLanguageResult('r','completed','10.'),ActiveContext('chat','w')) is None


def test_actual_experiment_result_gets_chart_table_calculator_and_owner_controls():
    result=NaturalLanguageResult('r','completed','Saved results',executions=({'success':True,'capability_id':'nlui.research.result','output':{
        'experiment':{'id':'real','updated':'revision','completed_runs':2,'runs':[{'run_index':0},{'run_index':1}],
            'spec':{'metric':'density','parameter_ranges':{'fraction_a':{}}},'summary':{}}}},))
    plan=ResponsePlanner().from_nlui(result,ActiveContext('chat','w'))
    assert {c.kind for c in plan.components}=={'metrics','chart','calculator','simulation'}
    chart=next(c for c in plan.components if c.kind=='chart')
    assert chart.config=={'x':'input_fraction_a','ys':['output_density'],'table':True}
    assert chart.source.id=='real' and chart.source.scope=='chat'


def test_source_table_is_literal_user_data_and_nonfinite_values_stay_text():
    content='Plot these actual user supplied observations for the experiment, with no independently verified instrument accuracy.\n\n| Input | Output |\n| --- | --- |\n| 1 | 2.5 |\n| 2 | 6 |\n| 3 | 9 |\n'
    rows=parse_user_table(content)
    assert rows==[{'Input':1.0,'Output':2.5},{'Input':2.0,'Output':6.0},{'Input':3.0,'Output':9.0}]
    plan=ResponsePlanner().from_user_message({'role':'user','message_id':'u','content':content},'chat')
    assert [c.kind for c in plan.components]==['chart']
    assert plan.components[0].config['table'] is True
    assert all(c.source.kind=='chat_dataset' for c in plan.components)
    assert numeric_columns(parse_user_table('x,y\n1,nan\n2,inf'))==['x']


def test_failed_tool_result_has_no_success_layout_or_download():
    result=NaturalLanguageResult('r','failed','Missing provider',executions=({'success':False,'output':{'generation_id':'not-real'}},))
    assert ResponsePlanner().from_nlui(result,ActiveContext('chat','w')) is None


def test_input_tables_and_requested_written_comparisons_are_not_interactive_results():
    table='\n| Parameter | Value |\n| --- | --- |\n| Motor speed | 600 rpm |\n| Battery input | 2.5 W |\n'
    for profile in ('auto','compact','detailed','visual','technical'):
        for request in ('Independently assess this tabletop generator. Give calculations and a comparison table.',
                        'Explain the assumptions in this data.', 'Do not make interactive charts. Explain the losses.'):
            assert ResponsePlanner().from_user_message({'role':'user','message_id':'u','content':request+table},'chat',profile) is None


def test_short_explicit_plot_request_is_supported_without_arbitrary_length_threshold():
    message={'role':'user','message_id':'u','content':'Plot these values.\nx,y\n1,2\n2,4'}
    plan=ResponsePlanner().from_user_message(message,'chat')
    assert plan and plan.components[0].kind=='chart'
    message['content']='Explain this example:\n```\nPlot these values.\nx,y\n1,2\n2,4\n```'
    assert ResponsePlanner().from_user_message(message,'chat') is None
