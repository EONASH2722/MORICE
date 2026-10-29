"""Bounded, public execution receipts for the chat's expandable activity view."""
from collections import OrderedDict
from dataclasses import dataclass
import time


@dataclass
class ActivityStep:
    label: str
    detail: str = ''
    state: str = 'active'
    started: float = 0.
    elapsed: float | None = None


class ActivityLedger:
    def __init__(self):self.steps=OrderedDict();self.closed=False

    def update(self,identifier,label,detail='',state='active'):
        if self.closed:return
        if state not in {'active','done','failed','cancelled'}:raise ValueError('Unknown activity state.')
        identifier=str(identifier)[:160];now=time.monotonic()
        step=self.steps.get(identifier)
        if step is None:step=ActivityStep(str(label)[:120],str(detail)[:600],state,now);self.steps[identifier]=step
        else:step.label=str(label)[:120];step.detail=str(detail)[:600];step.state=state
        if state!='active':step.elapsed=max(0.,now-step.started)
        while len(self.steps)>24:self.steps.popitem(last=False)

    def finish(self):
        for identifier,step in tuple(self.steps.items()):
            if step.state=='active' and identifier.startswith('phase:'):self.update(identifier,step.label,step.detail,'done')
        self.closed=True

    def text(self):
        symbols={'active':'●','done':'✓','failed':'!','cancelled':'−'}
        return '\n\n'.join(symbols[step.state]+'  '+step.label+
            (f'  ·  {step.elapsed:.1f}s' if step.elapsed is not None else '')+
            ('\n    '+step.detail if step.detail else '') for step in self.steps.values())
