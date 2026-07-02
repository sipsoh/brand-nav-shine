"""Dashboard template definitions (SETUP.md §15).

Templates live in source control for MVP (they version with the planner code
that fills them); they can be mirrored into the dashboard_templates table when
runtime editing is needed.
"""

TEMPLATES: list[dict] = [
    {
        "code": "client_report_v1",
        "name": "Client Report",
        "useCase": "client_report",
        "audiences": ["client", "executive"],
        "tone": "polished",
        "sections": ["hero_summary", "performance_over_time", "breakdown", "insights", "appendix"],
    },
    {
        "code": "marketing_performance_v1",
        "name": "Marketing Performance",
        "useCase": "marketing",
        "audiences": ["client", "executive", "analyst"],
        "tone": "polished",
        "sections": ["hero_summary", "performance_over_time", "breakdown", "insights", "appendix"],
    },
    {
        "code": "sales_pipeline_v1",
        "name": "Sales Pipeline",
        "useCase": "sales",
        "audiences": ["executive", "team", "analyst"],
        "tone": "executive",
        "sections": ["hero_summary", "funnel", "breakdown", "insights", "appendix"],
    },
    {
        "code": "survey_results_v1",
        "name": "Survey Results",
        "useCase": "survey",
        "audiences": ["executive", "team", "client"],
        "tone": "analytical",
        "sections": ["hero_summary", "breakdown", "insights", "appendix"],
    },
    {
        "code": "customer_feedback_v1",
        "name": "Customer Feedback",
        "useCase": "customer_feedback",
        "audiences": ["team", "executive"],
        "tone": "analytical",
        "sections": ["hero_summary", "breakdown", "insights", "appendix"],
    },
    {
        "code": "generic_snapshot_v1",
        "name": "Generic Executive Snapshot",
        "useCase": "generic",
        "audiences": ["executive", "team", "analyst", "client"],
        "tone": "minimal",
        "sections": ["hero_summary", "performance_over_time", "breakdown", "insights", "appendix"],
    },
]


def select_template(use_case: str | None) -> dict:
    for template in TEMPLATES:
        if template["useCase"] == use_case:
            return template
    return next(t for t in TEMPLATES if t["code"] == "generic_snapshot_v1")
