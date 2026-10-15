"""Research composition over the existing Kernel, agents, actions and project state."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import threading
import time
from pathlib import Path

from ..kernel import (CapabilityKernel, CapabilityDescriptor, CancellationToken, ExecutionContext,
    ExecutionResult, ResourceClaim, ResourceDescriptor, TaskGraph, TaskNode, TaskStatus,
    VerificationResult, VerificationStatus)
from ..unified_intelligence import PermissionDecision, PermissionState
from .contracts import ResearchProject, ResearchQuestion
from .ingestion import ResearchIngestion
from .safety import check_research_purpose
from .simulations import SimulationToolRegistry
from .store import ResearchStore
from .tools import ScientificTools
from .validation import verify_model


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ResearchRuntime:
    """No independent agent pool, device router, permission system or verifier engine."""
    def __init__(self, database, directory, *, kernel=None, agents=None, actions=None, builder=None):
        self.store, self.directory = ResearchStore(database), Path(directory)
        self.kernel = kernel or CapabilityKernel()
        self._owns_kernel = kernel is None
        self._agents, self.actions, self.builder = agents, actions, builder
        self._owns_agents = agents is None
        self._lab = None
        self._lock = threading.RLock()
        self.tools, self.simulations = ScientificTools(), SimulationToolRegistry()
        self.ingestion = ResearchIngestion(self.directory / "blobs")
        for resource in ("CPU", "IO", "DISK"):
            if self.kernel.resources.descriptor(resource) is None:
                self.kernel.resources.register(ResourceDescriptor(resource, min(2, os.cpu_count() or 1) if resource == "CPU" else 1))
        operations = {"calculate": self._calculate, "simulate": self._simulate, "statistics": self._statistics,
                      "symbolic": self._symbolic, "ingest": self._ingest, "verify": self._verify,
                      "cad": self._cad, "trajectory": self._trajectory, "material": self._material,
                      "model_compare": self._model_compare,"refresh_source":self._refresh_source}
        for name, operation in operations.items():
            cap = "research." + name
            if self.kernel.registry.lookup(cap):
                continue
            self.kernel.registry.register(CapabilityDescriptor(cap, "Research " + name, category="research",
                supported_resources=(ResourceClaim("IO" if name in {"ingest","refresh_source"} else "CPU"),),
                supports_cancellation=True, supports_verification=True,
                inline=name in {"calculate", "simulate"},
                input_schema={"type":"object"}, output_schema={"type":"object"}),
                lambda args, ctx, op=operation: ExecutionResult(TaskStatus.SUCCEEDED, True, op(args,ctx), verification_required=True),
                verifier=lambda result, expected, ctx, key=name: self._verify_operation(key,result,ctx),
                permission_check=self._file_permission if name in {"ingest","refresh_source"} else None)

    @property
    def agents(self):
        with self._lock:
            if self._agents is None:
                from ..agent_runtime import AgentCoordinator
                self._agents = AgentCoordinator(self.kernel)
            return self._agents

    @property
    def laboratory(self):
        with self._lock:
            if self._lab is None:
                from .laboratory import VirtualLaboratory
                self._lab = VirtualLaboratory(self.store.database, self.directory, runtime=self)
            return self._lab

    def project(self, identifier):
        return ResearchProject.from_snapshot(self.store.snapshot(identifier))

    def request_media_visual(self, project_id, request, media, context=None):
        """Illustration work uses the same Media Lab and execution authority."""
        if media.kernel is not self.kernel:
            raise ValueError("Research media must share the existing kernel.")
        self.project(project_id)
        from dataclasses import replace
        return media.submit(request,replace(context or ExecutionContext(),research_project_id=project_id))

    def attach_generated_visual(self, project_id, generation_id, media, *, index=0, title="Generated research illustration"):
        if media.kernel is not self.kernel:
            raise ValueError("Research media must share the existing kernel.")
        artifact=media.artifact(generation_id,index)
        # This record can be displayed/exported, but can never become MEASURED
        # or be used to assert scientific accuracy.
        return self.store.add(project_id,"artifact",title,{**artifact,"scientific_evidence":False},"GENERATED_VISUAL")

    def create(self, objective, chat_id=""):
        check_research_purpose(objective)
        identifier = self.store.create(objective, chat_id)
        from dataclasses import asdict
        self.store.add(identifier, "question", objective, asdict(ResearchQuestion(objective)))
        return identifier

    def _file_permission(self, args, ctx):
        state = self.kernel.permissions.controller.state("file_read")
        if state in {PermissionState.DENIED, PermissionState.UNSUPPORTED, PermissionState.OS_REQUIRED}:
            return PermissionDecision(False, denied=("file_read",), reason="Existing file-read policy forbids this import.")
        path = str(Path(args["source"]).resolve())
        selected = {str(Path(p).resolve()) for p in ctx.active_files}
        allowed = state == PermissionState.GRANTED or state == PermissionState.ASK and path in selected
        return PermissionDecision(allowed, required=() if allowed else ("file_read",), reason="Only explicitly selected files or existing granted file access may be imported.")

    def _calculate(self, args, ctx):
        if "sweep" in args:
            sweep = args["sweep"]
            return self.tools.sweep(args["expression"], args["inputs"], sweep["parameter"], sweep["values"], args.get("output_unit",""),ctx.cancellation_token)
        return self.tools.calculate(args["expression"], args["inputs"], args.get("output_unit",""),ctx.cancellation_token)

    def _simulate(self, args, ctx):
        if ctx.cancellation_token: ctx.cancellation_token.raise_if_cancelled()
        tool = self.simulations.get(args["tool_id"])
        output = self.simulations.run(tool.tool_id,args["parameters"])
        return {"outputs":output,"units":tool.supported_outputs,"tool_id":tool.tool_id,"tool_version":tool.version,
                "method":tool.method,"limitations":tool.limitations,"provenance":"SIMULATED"}

    def _statistics(self, args, ctx):
        from .statistics import analyze
        unit=args.get('unit','')
        self.tools.calculate('x',{'x':{'value':0,'unit':unit}},unit,ctx.cancellation_token)
        if args.get('method') in {'regression','correlation'}:
            x_unit=args.get('x_unit','');self.tools.calculate('x',{'x':{'value':0,'unit':x_unit}},x_unit,ctx.cancellation_token)
        return analyze(args,ctx.cancellation_token)

    @staticmethod
    def _symbolic(args, ctx):
        # Construct SymPy objects from the same bounded AST grammar; never sympify arbitrary source.
        import ast
        import sympy as sp
        expression, variable = args["expression"], args.get("variable","x")
        if len(expression)>256 or not variable.isidentifier() or len(variable)>32:
            raise ValueError("Bounded polynomial expression and variable required.")
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree))>64: raise ValueError("Expression too complex.")
        symbol = sp.Symbol(variable,real=True)
        def build(node):
            ctx.cancellation_token.raise_if_cancelled()
            if isinstance(node,ast.Name) and node.id==variable: return symbol
            if isinstance(node,ast.Constant) and type(node.value) in (int,float) and math.isfinite(node.value) and abs(node.value)<=1e6: return sp.Rational(str(node.value))
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)): return build(node.operand)*(-1 if isinstance(node.op,ast.USub) else 1)
            if isinstance(node,ast.BinOp):
                a,b=build(node.left),build(node.right)
                if isinstance(node.op,ast.Add): return a+b
                if isinstance(node.op,ast.Sub): return a-b
                if isinstance(node.op,ast.Mult): return a*b
                if isinstance(node.op,ast.Div) and not b.free_symbols and b != 0: return a/b
                if isinstance(node.op,ast.Pow) and b.is_Integer and 0<=b<=8: return a**b
            raise ValueError("Only a bounded polynomial grammar is supported.")
        expr=build(tree.body)
        polynomial=sp.Poly(expr,symbol)
        if polynomial.degree()>8: raise ValueError("Polynomial degree exceeds eight.")
        operation=args.get("operation","differentiate")
        if operation=="differentiate": result=sp.diff(expr,symbol)
        elif operation=="integrate": result=sp.integrate(expr,symbol)
        elif operation=="solve":
            if polynomial.degree()>2: raise ValueError("Verified equation solving is bounded to quadratic polynomials.")
            result=sp.solveset(expr,symbol,domain=sp.S.Reals)
        else: raise ValueError("Unsupported symbolic operation.")
        return {"expression":expression,"operation":operation,"result":str(result),"sympy_version":sp.__version__,
                "limitations":"Dimensionless polynomial mathematics; integrations omit the arbitrary constant. Physical units require research.calculate."}

    def _ingest(self, args, ctx):
        from ..project_build.workspace import safe_path
        path=Path(args["source"]).resolve(strict=True)
        safe_path(path.parent,path.name)
        return self.ingestion.ingest(path,ctx.cancellation_token)

    def _verify(self, args, ctx):
        from .artifacts import verify_project
        return verify_project(self.store.snapshot(args["project_id"]))

    def _refresh_source(self,args,ctx):
        project_id=args["project_id"]
        snapshot=self.store.snapshot(project_id)
        source=self._ingest(args,ctx)
        changed=[]
        for previous in snapshot["records"]:
            if previous["kind"]=="source" and previous["payload"].get("original_path")==source["original_path"]:
                if previous["payload"]["sha256"] == source["sha256"] and not previous["stale"]:
                    return {"project_id":project_id,"source_id":previous["id"],"sha256":source["sha256"],"changed":[],"review_required":False}
                if previous["payload"]["sha256"] != source["sha256"]:
                    self.store.invalidate(project_id,previous["id"],"Authorized literature watch observed a new version; review dependent evidence.")
                    changed.append(previous["id"])
        source_id=self.store.add(project_id,"source",source["name"],source,"USER_DATA")
        return {"project_id":project_id,"source_id":source_id,"sha256":source["sha256"],"changed":changed,"review_required":bool(changed)}

    def _cad(self, args, ctx):
        from .engineering import create_box
        return create_box(self.directory/"designs",args,ctx.cancellation_token)

    @staticmethod
    def _trajectory(args, ctx):
        from .simulations import particle_trajectory
        return particle_trajectory(args["parameters"],steps=args.get("steps",100),method=args.get("method","analytic"),cancel=ctx.cancellation_token)

    @staticmethod
    def _material(args, ctx):
        from .simulations import thermal_compatibility
        return thermal_compatibility(args["parameters"],args["allowable_mismatch_m"])

    @staticmethod
    def _model_compare(args, ctx):
        from .laboratory import compare_measurements
        predicted=args["predicted"]
        measured=args["measured"]
        if len(predicted)>10000 or len(measured)>10000: raise ValueError("Comparison exceeds 10,000 samples.")
        unit=args.get("unit","")
        ScientificTools().calculate("x",{"x":{"value":0,"unit":unit}},unit)
        return {**compare_measurements(predicted,measured),"unit":unit,"provenance":"CALCULATED"}

    def _verify_operation(self, name, result, ctx):
        args=ctx.metadata["task_inputs"]
        valid=False
        if name=="simulate":
            valid, note=verify_model(args["tool_id"],args["parameters"],result.output.get("outputs",{}))
        elif name=="refresh_source":
            stored=next(r for r in self.store.snapshot(args["project_id"])["records"] if r["id"]==result.output["source_id"])
            valid=stored["payload"]["sha256"]==result.output["sha256"]==hashlib.sha256(Path(args["source"]).read_bytes()).hexdigest()
            note="Authorized source bytes and persisted provenance match; changed dependents require review."
        elif name=="ingest":
            blob=Path(result.output["blob"])
            valid=blob.is_file() and hashlib.sha256(blob.read_bytes()).hexdigest()==result.output["sha256"] and hashlib.sha256(Path(args["source"]).read_bytes()).hexdigest()==result.output["sha256"]
            note="Actual selected source and stored bytes have equal hashes; interpretation is not certified."
        elif name=="cad":
            from .engineering import verify_box
            valid=verify_box(result.output)
            note="Actual STL triangles, dimensions, BOM and hashes reopened; no FEA/physical certification."
        else:
            operation={"calculate":self._calculate,"statistics":self._statistics,"symbolic":self._symbolic,"verify":self._verify,
                       "trajectory":self._trajectory,"material":self._material,"model_compare":self._model_compare}[name]
            valid=_digest(operation(args,ctx))==_digest(result.output)
            note="Deterministic tool recomputation and current inputs match; assumptions remain explicit."
        return VerificationResult(VerificationStatus.VERIFIED if valid else VerificationStatus.FAILED,(note,))

    def execute(self, capability, inputs, *, context=None, node_id="local"):
        ctx=context or ExecutionContext()
        task=TaskNode(capability,inputs,constraints={"node_id":node_id})
        return self.kernel.run_task(task,ctx)

    def run_recorded(self, project_id, capability, inputs, *, dependencies=(), context=None, node_id="local"):
        result=self.execute(capability,inputs,context=context,node_id=node_id)
        verified=result.success and result.verification and result.verification.status==VerificationStatus.VERIFIED
        provenance="SIMULATED" if capability in {"research.simulate","research.trajectory","research.material"} else "CALCULATED"
        import datetime
        payload={"inputs":inputs,"method":capability,"result":result.output if verified else None,
                 "execution":result.to_dict(),"node_id":node_id,
                 "received_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "time_alignment":"Receipt timestamp; remote clock offset/synchronization not established."}
        identifier=self.store.add(project_id,"simulation" if verified and provenance=="SIMULATED" else "result" if verified else "failure",
                                  capability,payload,provenance if verified else "UNKNOWN",dependencies)
        return {"record_id":identifier,"execution":result}

    def integrity_metrics(self, project_id):
        records=self.store.snapshot(project_id)["records"]
        return {"records":len(records),"stale":sum(r["stale"] for r in records),
                "tool_failures":sum(r["kind"]=="failure" for r in records),
                "verified_tool_results":sum(r["payload"].get("execution",{}).get("success",False) for r in records),
                "unverified_inferences":sum(r["provenance"] in {"INFERRED","UNKNOWN","HYPOTHESIS"} for r in records)}

    def parallel(self, operations, *, project_id="", context=None):
        roles={"ingest":"researcher","simulate":"simulation","trajectory":"simulation","material":"simulation","verify":"verifier"}
        tasks=tuple(TaskNode(cap,inputs,constraints={"role":roles.get(cap.split(".")[-1],"analyst"),"node_id":node}) for cap,inputs,node in operations)
        graph=TaskGraph(tasks,goal="Independent research tools")
        ctx=context or ExecutionContext(research_project_id=project_id)
        return self.agents.run(graph,ctx)

    def expose_compute(self, mesh):
        if mesh.kernel is not self.kernel: raise ValueError("Research and mesh must share the existing Kernel.")
        mesh.node.exposed.add("research.simulate")
        mesh.node._read_only.add("research.simulate")
        mesh.node._observers["research.simulate"]=lambda args,ctx: self._simulate(args,ctx).get("outputs")

    def retrieve_page(self, project_id, url, *, context=None):
        """Retrieve actual DOM text through the existing verified browser and permissions."""
        from urllib.parse import urlparse
        if urlparse(url).scheme not in {'http','https'}:raise ValueError('An HTTP(S) source is required.')
        ctx=context or ExecutionContext()
        for capability in ('browser.navigate','browser.extract'):
            result=self.execute(capability,{'target':url},context=ctx)
            if not result.success or not result.verification or result.verification.status!=VerificationStatus.VERIFIED:
                self.store.add(project_id,'failure','Literature retrieval failed',{'url':url,'execution':result.to_dict()})
                raise ValueError('Existing browser retrieval could not be verified; no citation was created.')
        observed=result.output
        text=observed.get('text','') if isinstance(observed,dict) else ''
        if not text or not observed.get('loaded'):raise ValueError('No loaded page text was retrieved.')
        raw=text.encode('utf-8');digest=hashlib.sha256(raw).hexdigest()
        directory=self.directory/'blobs';directory.mkdir(parents=True,exist_ok=True)
        blob=directory/(digest+'.txt');blob.write_bytes(raw)
        payload={'name':observed.get('title') or url,'format':'.txt','sha256':digest,'blob':str(blob),
                 'text':text,'metadata':{'url':observed.get('url',url),'title':observed.get('title','')},
                 'retrieved_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                 'trust':'untrusted_source_data','warnings':['Verified DOM text capped at 16,000 characters; search snippets are not treated as full papers.'],
                 'execution':result.to_dict(),'sections':[]}
        return self.store.add(project_id,'source',payload['name'],payload,'USER_DATA')

    def build_utility(self, project_id, root, goal, *, authorize, manifest=None, requirements=(), commands=None, run=None):
        if self.builder is None: raise ValueError("No existing Project Builder attached.")
        check_research_purpose(goal)
        builder=self.builder() if callable(self.builder) else self.builder
        session=builder.create(root,goal,manifest,requirements=requirements,commands=commands,runtime=run)
        result=builder.build(session,authorize=authorize)
        payload={"session_id":session.session_id,"result":result.result_card(),"project_root":str(root)}
        kind="artifact" if result.success else "failure"
        identifier=self.store.add(project_id,kind,"Project Builder research utility",payload)
        return {"record_id":identifier,"session":result}

    def close(self):
        if self._lab is not None: self._lab.close()
        if self._owns_agents and self._agents is not None: self._agents.shutdown()
        if self._owns_kernel: self.kernel.shutdown()
