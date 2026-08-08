"""Generation, validation, and the constants the frontend must not hardcode."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..codegen.context import GenerationError, assemble
from ..codegen.render import render_all
from ..models.settings import EnvironmentConfig, GeneralSettings
from ..storage import project_store
from ..storage.paths import output_dir
from ..trafficmath.rho_sigma import suggest
from ..validation.runner import run_validation
from .projects import get_project_or_404

router = APIRouter(prefix="/api", tags=["generate"])


@router.get("/constants")
def get_constants():
    """Values the browser needs for live rho/sigma prefill.

    The arithmetic is duplicated in JS for instant feedback while typing; serving the constants
    from here means the two copies cannot drift apart on the numbers that matter.
    """
    defaults = GeneralSettings()
    return {
        "phy_overhead_bits": defaults.phy_overhead_bits,
        "default_sigma_margin_factor": defaults.sigma_margin_factor,
        "default_frame_header_length_bytes": defaults.frame_header_length_bytes,
    }


class SuggestRequest(BaseModel):
    payload_bytes: int
    bag_s: float
    frame_header_bytes: int | None = None
    phy_overhead_bits: int | None = None
    margin_factor: float | None = None


@router.post("/suggest-traffic")
def suggest_traffic(request: SuggestRequest):
    defaults = GeneralSettings()
    try:
        result = suggest(
            payload_bytes=request.payload_bytes,
            bag_s=request.bag_s,
            frame_header_bytes=(
                request.frame_header_bytes
                if request.frame_header_bytes is not None
                else defaults.frame_header_length_bytes
            ),
            phy_overhead_bits=(
                request.phy_overhead_bits
                if request.phy_overhead_bits is not None
                else defaults.phy_overhead_bits
            ),
            margin_factor=request.margin_factor or defaults.sigma_margin_factor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"rho_bps": result.rho_bps, "sigma_bits": result.sigma_bits, "lmax_bits": result.lmax_bits}


@router.post("/projects/{project_id}/generate")
def generate(project_id: str):
    project = get_project_or_404(project_id)
    try:
        context = assemble(project)
    except GenerationError as exc:
        raise HTTPException(status_code=400, detail={"problems": exc.problems})

    target = output_dir() / project.output_dir_name
    result = render_all(context, target)

    return {
        "directory": str(result.directory),
        "files": [p.name for p in result.all_files],
        "warnings": result.warnings,
        "virtual_links": [
            {
                "label": plan.label,
                "route_key": plan.route_key,
                "route": plan.path_description,
                "rho_bps": plan.rho_bps,
                "sigma_bits": plan.sigma_bits,
                "lmax_bits": plan.lmax_bits,
                "auto_rho": plan.rho_was_auto,
                "auto_sigma": plan.sigma_was_auto,
            }
            for plan in context.vl_plans
        ],
    }


@router.get("/environment")
def get_environment():
    return project_store.load_environment()


@router.put("/environment")
def update_environment(config: EnvironmentConfig):
    project_store.save_environment(config)
    return config


@router.post("/projects/{project_id}/validate")
def validate(project_id: str):
    """Generate, then actually run the simulator and report what it says.

    Always regenerates first so the run can never reflect stale files.
    """
    project = get_project_or_404(project_id)
    try:
        context = assemble(project)
    except GenerationError as exc:
        raise HTTPException(status_code=400, detail={"problems": exc.problems})

    target = output_dir() / project.output_dir_name
    generated = render_all(context, target)

    result = run_validation(
        config=project_store.load_environment(),
        generated_dir=generated.directory,
        ini_filename=generated.ini_file.name,
        config_name=project.ini_config_name,
        sim_time_limit_s=project.general_settings.validation_sim_time_limit_s,
    )
    payload = result.model_dump()
    payload["generation_warnings"] = generated.warnings
    payload["summary"] = result.summary
    return payload
