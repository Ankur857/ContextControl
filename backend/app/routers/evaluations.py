from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.models import (
    EvalRunRequest,
    EvalRunResponse,
    ModeComparisonSummary,
    EvalResultItem,
)
from app.eval_dataset import DATASET_METADATA, EVALUATION_QUESTIONS
from app.eval_service import run_evaluation_suite
from app.storage import storage

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("/dataset")
def get_evaluation_dataset():
    """
    Returns the evaluation benchmark metadata and test cases.
    """
    return {
        "metadata": DATASET_METADATA,
        "questions": [
            {
                "id": q["id"],
                "category": q["category"],
                "question": q["question"],
                "scoped_context": q["scoped_context"],
                "reference_answer": q["reference_answer"],
                "reference_facts": q["reference_facts"],
                "expect_insufficient_context": q["expect_insufficient_context"],
                "notes": q["notes"],
            }
            for q in EVALUATION_QUESTIONS
        ],
    }


@router.post("/run", response_model=EvalRunResponse, status_code=status.HTTP_200_OK)
async def run_evaluation(payload: EvalRunRequest):
    """
    Executes an evaluation run across Baseline, Context Lock, and Citation Validation modes.
    """
    if not payload.modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one evaluation mode must be selected.",
        )

    valid_modes = {"baseline", "context_lock", "context_lock_citations"}
    for m in payload.modes:
        if m not in valid_modes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid evaluation mode '{m}'. Allowed: {list(valid_modes)}",
            )

    try:
        run_data = await run_evaluation_suite(
            dataset_id=payload.dataset_id,
            modes=payload.modes,
            use_mock=payload.use_mock,
        )
        return run_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation execution failed: {str(e)}",
        )


@router.get("/runs", response_model=List[dict])
def list_evaluation_runs():
    """
    Lists historical evaluation runs.
    """
    return storage.list_evaluation_runs()


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
def get_evaluation_run(run_id: str):
    """
    Retrieves full metrics and individual test results for an evaluation run.
    """
    run = storage.get_evaluation_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation run '{run_id}' not found.",
        )
    return run

