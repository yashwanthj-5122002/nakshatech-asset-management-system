"""Current BD handoff fixture for focused schema/concurrency verification only.

This changes test setup, never application authorization or workflow behavior.
"""
from datetime import date
from decimal import Decimal


def pytest_collection_modifyitems(items):
    import test_production_master_excel_allocation_v8_3 as allocation
    from test_production_file_tracking_v8_2 import make_user, make_client, full_team
    from app.modules.operations.workflow_service import (
        create_bd_project, submit_project_to_finance, assign_project_manager,
    )
    from app.modules.operations.schemas import WorkflowProjectCreate, WorkflowPMAssignment
    from app.modules.commercial.schemas import ProjectCommercialInput

    def current_project(db, code):
        bd = make_user(db, f'bd.{code}@example.com', 'bd')
        finance = make_user(db, f'finance.{code}@example.com', 'finance')
        pm = make_user(db, f'pm.{code}@example.com', 'lidar', 'LiDAR')
        client = make_client(db, bd, code)
        project, workflow = create_bd_project(db, actor=bd, payload=WorkflowProjectCreate(
            client_id=client.id, project_code=code, project_name='Validation current workflow',
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31),
            scope_text='Survey and deliver', performing_department_code='lidar',
            commercial=ProjectCommercialInput(scope_description='Survey and deliver',
                payment_terms='Net 30', currency_code='INR', estimated_amount=Decimal('10000'),
                estimate_date=date(2026, 10, 1))))
        submit_project_to_finance(db, actor=bd, project_id=project.id)
        assign_project_manager(db, actor=bd, project_id=project.id,
                              payload=WorkflowPMAssignment(project_manager_id=pm.id))
        team = full_team(db, pm, project, code)
        return dict(bd=bd, finance=finance, pm=pm, project=project, workflow=workflow, team=team)

    allocation.setup_project = current_project
