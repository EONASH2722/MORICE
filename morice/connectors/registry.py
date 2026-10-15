"""Connector capabilities use the kernel's existing permission controller."""
from __future__ import annotations

import time
from dataclasses import asdict
from ..kernel import (Availability, CapabilityDescriptor, ErrorCode, EventType, ExecutionResult,
                      KernelEvent, ResourceClaim)
from ..unified_intelligence import PermissionState, RiskClass
from .contracts import ConnectorState
from .http import ProviderHTTPError
from ..kernel.registry import CapabilityHealth


class ConnectorRegistry:
    def __init__(self, kernel, store, *, ambient=None):
        self.kernel, self.store, self.ambient = kernel, store, ambient
        self.providers = {}
        self.receiver = None

    def start_webhooks(self,*,user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Starting a webhook listener requires explicit configuration.")
        if self.receiver is None:
            from .webhooks import WebhookReceiver
            self.receiver=WebhookReceiver(self)
        return self.receiver.url

    def close(self):
        if self.receiver:self.receiver.close();self.receiver=None

    def register(self, provider):
        cid = provider.descriptor.connector_id
        if cid in self.providers:
            raise ValueError("Connector already registered.")
        if len(self.providers) >= 32:
            raise ValueError("Connector limit reached.")
        bindings=provider.operations()
        if set(bindings)!=set(provider.descriptor.capabilities) or any(not callable(b.handler) for b in bindings.values()):
            raise ValueError("Advertised connector operations must all be implemented.")
        if any(self.kernel.registry.lookup("connector."+cid+"."+op) for op in bindings):
            raise ValueError("Connector capability namespace is already registered.")
        provider.cursor_get = lambda key: self.store.cursor(key)
        provider.cursor_set = lambda key,value: self.store.cursor(key,value)
        provider.emit = lambda event: self.ambient.publish(event) if self.ambient else False
        self.providers[cid] = provider
        for operation, binding in bindings.items():
            method,write=binding.handler,binding.write
            cap = "connector." + cid + "." + operation
            group = "connector." + cid + "." + binding.scope
            def handle(arguments, context, method=method, provider=provider):
                try:
                    return method(arguments, context)
                except ProviderHTTPError as exc:
                    return ExecutionResult.failure(ErrorCode.CAPABILITY_UNAVAILABLE,
                        "Provider authentication expired." if exc.status == 401 else "Provider rate limit; scheduled retry required." if exc.retry_at else "Provider request failed.",
                        retryable=exc.status in {500,502,503,504})
                except (TimeoutError, OSError):
                    if provider.state not in {ConnectorState.DISABLED,ConnectorState.AUTH_EXPIRED}:
                        provider.state = ConnectorState.UNAVAILABLE
                    return ExecutionResult.failure(ErrorCode.TIMEOUT, "Provider did not respond within its network budget.")
                except (ValueError, KeyError, TypeError):
                    return ExecutionResult.failure(ErrorCode.INVALID_INPUT, "Invalid provider input or response.")
            descriptor = CapabilityDescriptor(cap, provider.descriptor.name + ": " + operation,
                provider="connector:" + cid, category="connector", required_permissions=("network",group),input_schema=binding.input_schema,
                risk_level=RiskClass.HIGH if write else RiskClass.LOW, supports_cancellation=True,
                supports_verification=True, supports_retry=False, timeout=8, supported_resources=(ResourceClaim("IO"),))
            self.kernel.registry.register(descriptor, handle, verifier=provider.verify,
                health_check=lambda p=provider,op=operation: CapabilityHealth(Availability.AVAILABLE if op.startswith("auth.") else Availability.DISABLED if p.state == ConnectorState.DISABLED else Availability.AVAILABLE
                    if p.state in {ConnectorState.CONNECTED,ConnectorState.DEGRADED,ConnectorState.RATE_LIMITED} else
                    Availability.DEGRADED if p.state == ConnectorState.UNAVAILABLE else Availability.UNAVAILABLE,p.state.value))
        configuration=provider.configuration()
        if configuration is not None:
            catalog = self.store.cursor("connector.catalog") or {}
            catalog[cid] = configuration
            self.store.cursor("connector.catalog",catalog)

    def begin_authorization(self,cid,*,user_confirmed=False):
        if not user_confirmed:
            raise PermissionError("Account authorization requires explicit user confirmation.")
        if self.kernel.permissions.controller.state("network") != PermissionState.GRANTED:
            raise PermissionError("Grant the existing network permission before starting account authorization.")
        challenge = self.providers[cid].begin_authorization(user_confirmed=True)
        self.kernel.permissions.controller.set_state(f"connector.{cid}.auth",PermissionState.GRANTED)
        self.store.cursor("connector.pending_scopes."+cid,["read"])
        return challenge

    def complete_authorization(self,cid):
        if self.providers[cid].state == ConnectorState.CONNECTED:
            scopes = self.store.cursor("connector.pending_scopes."+cid)
            if scopes:
                self.authorize_scopes(cid,scopes,user_confirmed=True)
                self.store.cursor("connector.pending_scopes."+cid,[])

    def authorize_scopes(self, cid, scopes=("read",), *, user_confirmed=False):
        if not user_confirmed or not set(scopes).issubset({"read", "write"}):
            raise PermissionError("Connector scope grants require explicit user authorization.")
        provider = self.providers[cid]
        if provider.state != ConnectorState.CONNECTED:
            raise PermissionError("Authorize the provider account before granting local scopes.")
        for scope in ("read", "write"):
            granted = scope in scopes
            self.kernel.permissions.controller.set_state(f"connector.{cid}.{scope}", PermissionState.GRANTED if granted else PermissionState.ASK)
        self.store.cursor("connector.scopes." + cid, list(scopes))
        self.kernel.permissions.controller.set_state(f"connector.{cid}.auth",PermissionState.GRANTED)
        for operation in provider.descriptor.capabilities:
            self.kernel.registry.set_status("connector."+cid+"."+operation,Availability.AVAILABLE)
        self.kernel.events.publish(KernelEvent(EventType.CONNECTOR_CHANGED, source="connectors", payload={"connector_id":cid,"state":provider.state.value}))

    def restore(self, cid):
        provider = self.providers[cid]
        provider.resume_auth()
        if provider.state == ConnectorState.CONNECTED:
            self.authorize_scopes(cid, self.store.cursor("connector.scopes." + cid) or (), user_confirmed=True)

    def disable(self, cid):
        provider = self.providers[cid]
        provider.disconnect()
        for scope in ("read", "write", "auth"):
            self.kernel.permissions.controller.set_state(f"connector.{cid}.{scope}", PermissionState.DENIED)
        self.store.cursor("connector.scopes." + cid, [])
        if self.ambient:
            self.ambient.disconnect_source(cid)
        self.kernel.events.publish(KernelEvent(EventType.CONNECTOR_CHANGED, source="connectors", payload={"connector_id":cid,"state":"DISABLED"}))

    def snapshot(self):
        return [{**asdict(p.descriptor),"state":p.state.value,"retry_at":p.retry_at,"network_calls":getattr(getattr(p,"http",None),"calls",0)}
                for p in self.providers.values()]
