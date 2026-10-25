"""Trusted presentation factories; response payloads can select only registered kinds."""
from dataclasses import asdict,dataclass

from .contracts import Component,COMPONENTS,SOURCE_KINDS


@dataclass(frozen=True)
class RendererEntry:
    kind:str
    factory:object
    sources:frozenset
    interactive:bool=True
    version:int=1


class ResponseComponentRegistry:
    def __init__(self):self._entries={}

    def register(self,kind,factory,*,sources=SOURCE_KINDS,interactive=True):
        if kind not in COMPONENTS or kind in self._entries or not callable(factory):raise ValueError('Invalid or duplicate trusted renderer registration.')
        self._entries[kind]=RendererEntry(kind,factory,frozenset(sources),interactive)

    def create(self,component,context):
        # Revalidate after any in-memory mutation and before constructing Qt.
        component=Component.from_dict(asdict(component)) if isinstance(component,Component) else Component.from_dict(component)
        entry=self._entries.get(component.kind)
        if entry is None:raise ValueError('This component renderer is not available in the installed build.')
        if component.source and component.source.kind not in entry.sources:raise ValueError('This renderer cannot use that source owner.')
        return entry.factory(component,context)

    def inventory(self):
        return [{'kind':entry.kind,'schema':entry.version,'sources':sorted(entry.sources),'interactive':entry.interactive}
            for entry in self._entries.values()]
