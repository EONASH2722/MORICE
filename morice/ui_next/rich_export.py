"""Selectable report text and actual data through the existing Qt PDF backend."""
from dataclasses import replace
import html
from pathlib import Path
import tempfile

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument,QPdfWriter,QImage

from ..rich_response.exports import ResponseRender


def capture_report(host,plan,snapshots):
    if host.plan.to_dict()!=plan:raise ValueError('The response changed while preparing the report. Try again.')
    if not snapshots:raise ValueError('This response has no actual source data to report.')
    root=Path(host.runtime.directory)/'response-cache';root.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='report-',dir=root);path=Path(temporary.name)/'report.pdf'
    escape=lambda value:html.escape(str(value))
    document=QTextDocument();document.setDefaultStyleSheet('body { color: #101820; background: white; font-family: sans-serif; } table { border-collapse: collapse; } td,th { padding: 4px; border: 1px solid #999; }')
    sections=['<h1>MORICE response report</h1>','<h2>Conversation summary</h2><p>Summary text is not independent verification.</p><p>'+escape(plan.get('summary','')).replace('\n','<br>')+'</p>']
    remaining=1000
    try:
        for number,snapshot in enumerate(snapshots):
            sections.append('<h2>'+escape(snapshot.title)+'</h2><p>'+escape(snapshot.provenance)+' · '+escape(snapshot.limitation)+'</p>')
            sections.append('<p>Source: '+escape(snapshot.source.kind)+':'+escape(snapshot.source.id)+'<br>Revision: '+escape(snapshot.revision)+'</p>')
            for state in host.sections.values():
                component=state['component'];view=state['view']
                if component.kind=='chart' and component.source and (component.source.kind,component.source.id)==(snapshot.source.kind,snapshot.source.id):
                    if view is not None and view.context.snapshot.revision==snapshot.revision:
                        image_path=Path(temporary.name)/('chart-'+str(number)+'.png')
                        if not view.canvas.export_png(str(image_path)):raise ValueError('Actual chart capture failed.')
                        name='morice-report-chart-'+str(number);document.addResource(QTextDocument.ImageResource,QUrl(name),QImage(str(image_path)))
                        sections.append('<p><img src="'+name+'" width="600"></p>')
                    else:sections.append('<p>Chart figure omitted: expand and refresh its actual source before export. The current source data is listed below.</p>')
                    break
            rows=snapshot.rows[:min(200,remaining)];remaining-=len(rows)
            if rows:
                fields=[k for k in dict.fromkeys(k for row in rows for k in row) if not k.startswith('__source_row_id')][:12]
                sections.append('<p>'+str(len(rows))+' source rows shown; tables are bounded to 200 rows per source and 1,000 overall.</p><table><tr>'+''.join('<th>'+escape(k)+(' ['+escape(snapshot.units[k])+']' if snapshot.units.get(k) else '')+'</th>' for k in fields)+'</tr>')
                sections.extend('<tr>'+''.join('<td>'+escape(str(row.get(k,''))[:500])+'</td>' for k in fields)+'</tr>' for row in rows)
                sections.append('</table>')
            else:
                sections.append('<pre>'+escape(str(snapshot.data)[:10000])+'</pre>')
            if snapshot.artifacts:
                sections.append('<h3>Actual artifact references</h3>')
                for artifact in snapshot.artifacts[:30]:sections.append('<p>'+escape(artifact.name)+' · '+escape(artifact.sha256)+' · '+('available' if artifact.available else escape(artifact.reason))+'</p>')
        document.setHtml(''.join(sections));writer=QPdfWriter(str(path));writer.setResolution(120);document.print_(writer);del writer
        return ResponseRender(host.sources,replace(snapshots[0].source,revision=snapshots[0].revision),path,'pdf',temporary,
            tuple(replace(snapshot.source,revision=snapshot.revision) for snapshot in snapshots))
    except BaseException:temporary.cleanup();raise
