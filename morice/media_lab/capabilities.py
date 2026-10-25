"""Lightweight registration only; the service, ML and hardware remain lazy."""
from __future__ import annotations

from ..kernel import Availability,CapabilityDescriptor,CapabilityHealth,ResourceClaim


INTENTS={
    'media.image.generate':'TEXT_TO_IMAGE','media.image.edit':'IMAGE_TO_IMAGE','media.image.variation':'IMAGE_VARIATION',
    'media.image.inpaint':'INPAINT','media.image.outpaint':'OUTPAINT','media.image.upscale':'UPSCALE',
    'media.image.background_remove':'BACKGROUND_REMOVE','media.video.generate':'TEXT_TO_VIDEO',
    'media.video.image_to_video':'IMAGE_TO_VIDEO','media.video.upscale':'VIDEO_UPSCALE'}


def register_media_capabilities(kernel,factory):
    for capability,intent in INTENTS.items():
        kernel.registry.register(CapabilityDescriptor(capability,capability.replace('.',' ').title(),category='media',
            description='Local verified generation; workflow availability depends on an inspected compatible model.',
            status=Availability.DEGRADED,supported_resources=(ResourceClaim('GPU',exclusive=True),ResourceClaim('LOCAL_MODEL',exclusive=True),ResourceClaim('CPU'),ResourceClaim('DISK')),
            supports_cancellation=True,supports_verification=True,timeout=1800,
            input_schema={'type':'object','required':['request'],'properties':{'request':{'type':'object'}}}),
            lambda args,ctx,workflow=intent:factory().execute(args,ctx,workflow),
            resource_resolver=lambda args,ctx,workflow=intent:factory().resource_claims(args,ctx,workflow),
            verifier=lambda result,expected,ctx:factory().verify_result(result,ctx),
            permission_check=lambda args,ctx:factory().file_permission(args,ctx),
            on_completed=lambda result,ctx:factory().completed(result,ctx))
    kernel.registry.register(CapabilityDescriptor('media.model.status','Media models and queue',category='media',inline=True),
        lambda args,ctx:factory().status_result())
    kernel.registry.register(CapabilityDescriptor('media.artifact.export','Export a verified media artifact',category='media',
        required_permissions=('file_write',),supported_resources=(ResourceClaim('DISK'),),supports_verification=True,timeout=10),
        lambda args,ctx:factory().export_handler(args,ctx),verifier=lambda result,expected,ctx:factory().verify_export(result,ctx),
        permission_check=lambda args,ctx:factory().export_permission(args,ctx))
    kernel.registry.register(CapabilityDescriptor('media.model.benchmark','Benchmark Generative Media',category='media',inline=True,timeout=1800),
        lambda args,ctx:factory().start_benchmark(args,ctx))
    kernel.registry.register(CapabilityDescriptor('media.artifact.contact_sheet','Preview verified generations',category='media',supported_resources=(ResourceClaim('CPU'),ResourceClaim('DISK')),supports_verification=True,timeout=10),
        lambda args,ctx:factory().preview_handler(args,ctx),verifier=lambda result,expected,ctx:factory().verify_export(result,ctx))
    kernel.registry.register(CapabilityDescriptor('media.cache.clear','Clear derived media previews',category='media',supported_resources=(ResourceClaim('DISK'),),timeout=5),
        lambda args,ctx:factory().cache_clear_handler(args,ctx))
