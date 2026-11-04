from __future__ import annotations

import importlib.util
from pathlib import Path

source = (Path(__file__).resolve().parents[1] / 'payload' / 'backend' / 'app' /
          'routers' / 'project_tracking_progress.py')
spec = importlib.util.spec_from_file_location('project_tracking_progress', source)
assert spec and spec.loader
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


def test_complete_only_after_delivery():
    assert progress.stage_score(production='completed', qc='passed', qa='passed')[0] == 90
    assert progress.stage_score(production='completed', qc='passed', qa='passed', delivered=True)[0] == 100


def test_rework_is_not_counted_as_delivered():
    percentage, state = progress.stage_score(production='completed', qc='rejected')
    assert state == 'rework'
    assert percentage < 100


def test_unknown_status_does_not_inflate_percent():
    assert progress.weighted_progress([{'weight': 1, 'score': 100}, {'weight': 1, 'score': None}]) == 50
    assert progress.weighted_progress([{'weight': 1, 'score': None}]) is None


def test_survey_work_has_progress_even_without_file_items():
    assert progress.stage_score(production='completed', qc='pending', qa='pending')[0] == 45


def test_software_does_not_use_heatmap():
    assert progress.is_software('software_team')
    assert not progress.is_software('laser_scanning')


def test_file_qa_not_a_false_100_percent():
    assert progress.file_score('qa_completed')[0] == 90
    assert progress.file_score('delivered')[0] == 100


def test_file_activity_sorting_and_stage_check():
    from types import SimpleNamespace
    from datetime import datetime
    a = SimpleNamespace(created_at=datetime(2026, 1, 2), id=2, stage='qc', status='passed')
    b = SimpleNamespace(created_at=datetime(2026, 1, 1), id=1, stage='production', status='completed')
    score, state = progress.file_score('in_progress', activities=[a, b])
    assert score == 70 and state == 'working'
