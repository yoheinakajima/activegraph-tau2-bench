import argparse
import pathlib
import unittest

from scripts import run_tau2_model_baseline as model_runner
from scripts import run_tau2_runtime_traced_baseline as traced_runner


class Tau2BaselineTaskSelectionTests(unittest.TestCase):
    def _args(self, module, *, task_id=None, num_tasks=None):
        return argparse.Namespace(
            provider="openai",
            model="gpt-4.1-mini",
            domain=module.DEFAULT_DOMAIN,
            task_id=task_id,
            num_tasks=num_tasks,
            max_steps=module.DEFAULT_MAX_STEPS,
            concurrency=module.DEFAULT_CONCURRENCY,
            timeout_seconds=module.DEFAULT_TIMEOUT_SECONDS,
            allow_non_mock_domain=False,
            yes_i_understand_this_may_call_paid_apis=False,
        )

    def _selected_command(self, module, *, task_id=None, num_tasks=None):
        args = self._args(module, task_id=task_id, num_tasks=num_tasks)
        mode, note = module.apply_task_selection(args)
        command = module.build_tau2_command(args, pathlib.Path("/tmp/tau2-output"))
        return args, mode, note, command

    def _assert_has_option_value(self, command, option, value):
        self.assertIn(option, command)
        index = command.index(option)
        self.assertEqual(command[index + 1], value)

    def _assert_lacks_option(self, command, option):
        self.assertNotIn(option, command)

    def test_num_tasks_without_task_id_uses_num_tasks_for_model_runner(self):
        args, mode, note, command = self._selected_command(model_runner, num_tasks=10)

        self.assertIsNone(args.task_id)
        self.assertEqual(mode, "num_tasks")
        self.assertIsNone(note)
        self._assert_has_option_value(command, "--num-tasks", "10")
        self._assert_lacks_option(command, "--task-ids")

    def test_num_tasks_without_task_id_uses_num_tasks_for_traced_runner(self):
        args, mode, note, command = self._selected_command(traced_runner, num_tasks=10)

        self.assertIsNone(args.task_id)
        self.assertEqual(mode, "num_tasks")
        self.assertIsNone(note)
        self._assert_has_option_value(command, "--num-tasks", "10")
        self._assert_lacks_option(command, "--task-ids")

    def test_explicit_task_id_uses_task_ids_for_both_runners(self):
        for module in (model_runner, traced_runner):
            with self.subTest(module=module.__name__):
                args, mode, note, command = self._selected_command(module, task_id="create_task_1", num_tasks=10)

                self.assertEqual(args.task_id, "create_task_1")
                self.assertEqual(mode, "explicit_task_id")
                self.assertIsNone(note)
                self._assert_has_option_value(command, "--task-ids", "create_task_1")
                self._assert_lacks_option(command, "--num-tasks")

    def test_omitted_task_args_default_to_safe_task_id_for_both_runners(self):
        for module in (model_runner, traced_runner):
            with self.subTest(module=module.__name__):
                args, mode, note, command = self._selected_command(module)

                self.assertEqual(args.task_id, module.DEFAULT_TASK_ID)
                self.assertEqual(mode, "default_task_id")
                self.assertIn(module.DEFAULT_TASK_ID, note)
                self._assert_has_option_value(command, "--task-ids", module.DEFAULT_TASK_ID)
                self._assert_lacks_option(command, "--num-tasks")

    def test_numeric_task_id_resolves_to_first_real_mock_task_for_both_runners(self):
        for module in (model_runner, traced_runner):
            with self.subTest(module=module.__name__):
                args, mode, note, command = self._selected_command(module, task_id="0")

                self.assertEqual(args.task_id, "create_task_1")
                self.assertEqual(mode, "numeric_task_index")
                self.assertIn("resolved", note)
                self._assert_has_option_value(command, "--task-ids", "create_task_1")
                self._assert_lacks_option(command, "--num-tasks")


if __name__ == "__main__":
    unittest.main()
