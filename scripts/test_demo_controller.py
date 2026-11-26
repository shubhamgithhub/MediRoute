"""Offline tests of the AWS controller's launch and shutdown safety boundaries."""
import copy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import Mock

import demo_controller as controller


NOW = datetime(2026, 11, 26, 2, 30, tzinfo=timezone.utc)
TASK = controller.TASK_PREFIX + "a" * 32
RELEASE = {"sha": "b" * 40, "task_definition": controller.DEFINITION_PREFIX + "17",
           "backend": "sha256:" + "c" * 64, "frontend": "sha256:" + "d" * 64}
DEFINITION = {
    "taskDefinitionArn": RELEASE["task_definition"], "status": "ACTIVE",
    "family": controller.CLUSTER, "cpu": "1024", "memory": "4096",
    "networkMode": "awsvpc", "requiresCompatibilities": ["FARGATE"],
    "executionRoleArn": f"arn:aws:iam::{controller.ACCOUNT}:role/mediroute-demo-task-execution",
    "taskRoleArn": f"arn:aws:iam::{controller.ACCOUNT}:role/mediroute-demo-task",
    "containerDefinitions": [
        {"name": "api", "image": controller.REGISTRY + "/mediroute-backend@" + RELEASE["backend"]},
        {"name": "frontend", "image": controller.REGISTRY + "/mediroute-frontend@" + RELEASE["frontend"],
         "environment": [{"name": "MEDIROUTE_DUCKDNS_LABEL", "value": "mediroute-demo"}],
         "portMappings": [{"containerPort": 443, "protocol": "tcp"}]},
    ],
}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.ecs, self.scheduler, self.ssm = Mock(), Mock(), Mock()
        self.ecs.get_paginator.return_value.paginate.return_value = [{"taskArns": []}]
        self.ecs.describe_task_definition.return_value = {"taskDefinition": copy.deepcopy(DEFINITION)}
        self.ecs.run_task.return_value = {"tasks": [{"taskArn": TASK, "lastStatus": "PROVISIONING"}]}
        self.ssm.get_parameter.return_value = {"Parameter": {"Value": json.dumps(RELEASE)}}
        class Conflict(Exception):
            pass
        self.scheduler.exceptions.ConflictException = Conflict
        self.scheduler.get_schedule.side_effect = lambda **kwargs: self.scheduler.create_schedule.call_args.kwargs.copy()

    def call(self, event=None, now=NOW):
        return controller.execute(event or {"operation": "start", "request_id": "unit-test"},
                                  self.ecs, self.scheduler, self.ssm, now)

    def test_launch_pins_release_and_verifies_exact_midnight_stop(self):
        result = self.call()
        self.assertEqual(result["status"], "started")
        self.assertEqual(result["source_sha"], RELEASE["sha"])
        self.assertEqual(result["stop_time_utc"], "2026-11-26T18:30:00+00:00")
        self.assertEqual(self.ecs.run_task.call_args.kwargs["taskDefinition"], RELEASE["task_definition"])
        schedule = self.scheduler.create_schedule.call_args.kwargs
        self.assertEqual(schedule["ScheduleExpression"], "at(2026-11-26T18:30:00)")
        self.assertEqual(json.loads(schedule["Target"]["Input"])["Task"], TASK)
        self.ecs.stop_task.assert_not_called()

    def test_existing_task_is_not_duplicated_and_receives_a_verified_stop(self):
        self.ecs.get_paginator.return_value.paginate.return_value = [{"taskArns": [TASK]}]
        self.assertEqual(self.call()["status"], "already_running")
        self.ecs.run_task.assert_not_called()
        self.ssm.get_parameter.assert_not_called()
        self.scheduler.get_schedule.assert_called_once()

    def test_multiple_tasks_refuse_new_start(self):
        self.ecs.get_paginator.return_value.paginate.return_value = [{"taskArns": [TASK, TASK + "b"]}]
        with self.assertRaisesRegex(ValueError, "More than one"):
            self.call()
        self.ecs.run_task.assert_not_called()

    def test_cutoff_early_hours_and_final_midnight(self):
        for stamp in ["2026-11-26T02:29:59+00:00", "2026-12-06T18:29:00+00:00",
                      "2026-12-07T02:30:00+00:00", "2027-11-26T02:30:00+00:00"]:
            with self.subTest(stamp=stamp):
                self.assertEqual(self.call(now=datetime.fromisoformat(stamp))["status"], "skipped")
        self.ecs.run_task.assert_not_called()
        result = self.call(now=datetime.fromisoformat("2026-12-06T02:30:00+00:00"))
        self.assertEqual(result["stop_time_utc"], "2026-12-06T18:30:00+00:00")

    def test_stop_verification_failure_rolls_back_launched_task(self):
        self.scheduler.get_schedule.return_value = {}
        self.scheduler.get_schedule.side_effect = RuntimeError("simulated permission failure")
        with self.assertRaisesRegex(RuntimeError, "permission"):
            self.call()
        self.ecs.stop_task.assert_called_once()
        self.assertEqual(self.ecs.stop_task.call_args.kwargs["task"], TASK)

    def test_lost_run_response_recovers_task_for_emergency_stop(self):
        self.ecs.run_task.side_effect = TimeoutError("lost response")
        self.ecs.list_tasks.return_value = {"taskArns": [TASK]}
        with self.assertRaises(TimeoutError):
            self.call()
        self.ecs.list_tasks.assert_called_once()
        self.ecs.stop_task.assert_called_once()

    def test_invalid_release_fails_before_compute_starts(self):
        for key, value in [("cpu", "2048"), ("executionRoleArn", "unexpected-role"),
                           ("taskDefinitionArn", controller.DEFINITION_PREFIX + "18")]:
            with self.subTest(key=key):
                broken = copy.deepcopy(DEFINITION)
                broken[key] = value
                self.ecs.describe_task_definition.return_value = {"taskDefinition": broken}
                with self.assertRaises(ValueError):
                    self.call()
        self.ecs.run_task.assert_not_called()

    def test_wrong_image_digest_is_rejected(self):
        broken = copy.deepcopy(DEFINITION)
        broken["containerDefinitions"][0]["image"] += "wrong"
        self.ecs.describe_task_definition.return_value = {"taskDefinition": broken}
        with self.assertRaisesRegex(ValueError, "image"):
            self.call()
        self.ecs.run_task.assert_not_called()

    def test_retry_token_is_stable_and_stale_scheduled_events_do_nothing(self):
        event = {"operation": "start", "scheduled": True, "scheduled_time": NOW.isoformat()}
        self.call(event)
        token = self.ecs.run_task.call_args.kwargs["clientToken"]
        self.call(event)
        self.assertEqual(token, self.ecs.run_task.call_args.kwargs["clientToken"])
        self.ecs.run_task.reset_mock()
        delayed = datetime.fromisoformat("2026-11-26T02:46:00+00:00")
        self.assertEqual(self.call(event, delayed)["status"], "skipped")
        self.ecs.run_task.assert_not_called()

    def test_manual_stop_and_final_midnight_sweep(self):
        self.ecs.get_paginator.return_value.paginate.return_value = [{"taskArns": [TASK]}]
        midnight = datetime.fromisoformat("2026-12-06T18:30:00+00:00")
        result = self.call({"operation": "stop", "scheduled": True,
                            "scheduled_time": midnight.isoformat()}, midnight)
        self.assertEqual(result["status"], "stopped")
        self.ecs.stop_task.assert_called_once()
        self.ecs.run_task.assert_not_called()

    def test_verification_does_not_mutate_cloud_state(self):
        self.assertEqual(self.call({"operation": "verify"})["status"], "verified")
        self.ecs.run_task.assert_not_called()
        self.ecs.stop_task.assert_not_called()
        self.scheduler.create_schedule.assert_not_called()

    def test_wrong_required_sha_refuses_launch(self):
        with self.assertRaisesRegex(ValueError, "Requested release"):
            self.call({"operation": "start", "request_id": "test", "required_sha": "e" * 40})
        self.ecs.run_task.assert_not_called()


class ReleasePreparationTests(unittest.TestCase):
    def test_obsolete_main_build_never_registers_or_changes_pointer(self):
        import os
        import prepare_demo_release
        from unittest.mock import patch
        with patch.dict(os.environ, {"SOURCE_SHA": "a" * 40, "GITHUB_REPOSITORY": "example/repo"}), \
                patch("prepare_demo_release.run", return_value=json.dumps({"sha": "b" * 40})) as run:
            prepare_demo_release.main()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[:2], ("gh", "api"))

    def test_main_advancing_during_registration_does_not_roll_back_pointer(self):
        import os
        import prepare_demo_release
        from unittest.mock import patch
        sha = "a" * 40
        answers = [json.dumps({"sha": sha}), sha,
                   "PASS: Registered " + controller.DEFINITION_PREFIX + "18",
                   json.dumps({"sha": "b" * 40})]
        with patch.dict(os.environ, {"SOURCE_SHA": sha, "GITHUB_REPOSITORY": "example/repo"}), \
                patch("prepare_demo_release.resolve_release", return_value=copy.deepcopy(RELEASE)), \
                patch("prepare_demo_release.run", side_effect=answers) as run:
            prepare_demo_release.main()
        self.assertFalse(any(call.args[:2] == ("aws", "ssm") for call in run.call_args_list))

    def test_preparing_current_main_only_registers_and_publishes_metadata(self):
        import os
        import prepare_demo_release
        from unittest.mock import patch
        sha = RELEASE["sha"]
        answers = [json.dumps({"sha": sha}), sha,
                   "PASS: Registered " + controller.DEFINITION_PREFIX + "18",
                   json.dumps({"sha": sha}), "{}"]
        with patch.dict(os.environ, {"SOURCE_SHA": sha, "GITHUB_REPOSITORY": "example/repo"}), \
                patch("prepare_demo_release.resolve_release", return_value=copy.deepcopy(RELEASE)), \
                patch("prepare_demo_release.run", side_effect=answers) as run:
            prepare_demo_release.main()
        commands = [call.args for call in run.call_args_list]
        self.assertIn(("bash", "scripts/deploy_ecs.sh", "register"), commands)
        self.assertNotIn(("bash", "scripts/deploy_ecs.sh", "deploy"), commands)
        self.assertEqual(commands[-1][:3], ("aws", "ssm", "put-parameter"))

if __name__ == "__main__":
    unittest.main()
