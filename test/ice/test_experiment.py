import os
import types
import unittest2
import logging
import mock
import tempfile

import fabric.api as fabric_api

from ice import experiment
from ice import tasks


class TestExperimentConstructor(unittest2.TestCase):
    def setUp(self):
        self.old_exp_load = experiment.Experiment.load
        experiment.Experiment.load = mock.MagicMock()

    def tearDown(self):
        experiment.Experiment.load = self.old_exp_load

    def test_file_does_not_exist(self):
        with self.assertRaises(experiment.Experiment.LoadError):
            experiment.Experiment(
                logging.getLogger('testing'),
                '/path/does/not/exist'
            )

    def test_file_is_dir(self):
        with self.assertRaises(experiment.Experiment.LoadError):
            experiment.Experiment(
                logging.getLogger('testing'),
                tempfile.gettempdir()
            )

    def test_file_no_python(self):
        tmp_file = tempfile.NamedTemporaryFile()

        with self.assertRaises(experiment.Experiment.LoadError):
            experiment.Experiment(
                logging.getLogger('testing'),
                tmp_file.name
            )

        tmp_file.close()

    def test_calls_load(self):
        tmp_file = tempfile.NamedTemporaryFile(suffix='.py')

        experiment.Experiment(
            logging.getLogger('testing'),
            tmp_file.name
        )
        self.assertEqual(experiment.Experiment.load.call_count, 1)

        tmp_file.close()

    def test_members(self):
        tmp_file = tempfile.NamedTemporaryFile(suffix='.py')

        exp = experiment.Experiment(
            logging.getLogger('testing'),
            tmp_file.name
        )

        self.assertEqual(exp.mod_file_path, tmp_file.name)
        self.assertEqual(
            exp.mod_name,
            os.path.basename(tmp_file.name).replace('.py', '')
        )
        self.assertIsNone(exp.module)

        tmp_file.close()


class TestLoad(unittest2.TestCase):
    def setUp(self):
        self.assets_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'assets')
        )

    def test_load_empty(self):
        tmp_file = tempfile.NamedTemporaryFile(suffix='.py')

        exp = experiment.Experiment(
            logging.getLogger('testing'),
            tmp_file.name
        )

        self.assertIsInstance(exp.module, types.ModuleType)

        mod_name = os.path.basename(tmp_file.name).replace('.py', '')
        self.assertEqual(exp.module.__name__, mod_name)

        tmp_file.close()

    def test_load_syntax_error(self):
        mod_file_path = os.path.join(self.assets_path, 'exp_syntax_error.py')

        with self.assertRaises(experiment.Experiment.LoadError):
            experiment.Experiment(
                logging.getLogger('testing'),
                mod_file_path
            )

    def test_reload(self):
        tmp_file = tempfile.NamedTemporaryFile(suffix='.py', delete=False)

        exp = experiment.Experiment(
            logging.getLogger('testing'),
            tmp_file.name
        )

        with self.assertRaises(AttributeError):
            exp.module.a_func

        tmp_file.write("""def a_func():
    pass""")
        tmp_file.file.flush()

        # Remove compiled file to speed up things.
        #   This is necessary to make test realistic. It seems that there
        #   is a race between changing the code of the .py file and the
        #   .pyc file becoming invalidated.
        os.remove(tmp_file.name + 'c')

        exp.load()
        self.assertIsInstance(exp.module.a_func, types.FunctionType)

        tmp_file.close()


class TestGetContents(unittest2.TestCase):
    def setUp(self):
        mod_file_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), '..', 'assets',
                'exp_normal.py'
            )
        )

        self.exp = experiment.Experiment(
            logging.getLogger('testing'),
            mod_file_path
        )

    def test_get_runners(self):
        self.assertItemsEqual(
            self.exp.get_runners(),
            [
                '* run_a',
                '* run_b: I am a fast runner'
            ]
        )

    def test_get_tasks(self):
        self.assertItemsEqual(
            self.exp.get_tasks(),
            [
                '* task_a_a',
                '* task_a_b: Hello world',
                '* task_b_a',
                '* task_b_b: A helpful message',
                '* task_b_c'
            ]
        )


class TestRun(unittest2.TestCase):
    def setUp(self):
        # Load placeholder experiment. By doing so, following tests can
        # overwrite functions in this module with mocks.
        mod_file_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), '..', 'assets',
                'exp_normal.py'
            )
        )
        self.exp = experiment.Experiment(
            logging.getLogger('testing'),
            mod_file_path
        )

    def test_not_existing_function(self):
        self.assertFalse(
            self.exp.run([], '', func_name='non_existing')
        )

    def test_not_callable(self):
        self.assertFalse(
            self.exp.run([], '', func_name='a_func')
        )

    def test_fabric_settings(self):
        mock_runner = mock.MagicMock(return_value='runner-return-value')
        self.exp.module.run_a = tasks.Runner(mock_runner)

        with SettingsMock(self) as settings_mock:
            self.exp.run(['host1', 'host2'], 'file.key', func_name='run_a'),
            settings_mock.assert_setting('hosts', ['host1', 'host2'])
            settings_mock.assert_setting('key_filename', 'file.key')

    def test_runner_no_args(self):
        mock_runner = mock.MagicMock(return_value='runner-return-value')
        self.exp.module.run_a = tasks.Runner(mock_runner)

        self.assertEqual(
            self.exp.run(['host1'], '', func_name='run_a'),
            'runner-return-value'
        )
        mock_runner.assert_called_once_with(['host1'])

    def test_runner_with_args(self):
        mock_runner = mock.MagicMock(return_value='runner-return-value')
        self.exp.module.run_a = tasks.Runner(mock_runner)

        self.assertEqual(
            self.exp.run(
                ['host1'], '', func_name='run_a',
                args=[12, 'test_1', 'test_2']
            ), 'runner-return-value'
        )
        mock_runner.assert_called_once_with(
            ['host1'], 12, 'test_1', 'test_2'
        )

    def test_runner_with_dict_arg(self):
        mock_runner = mock.MagicMock(return_value='runner-return-value')
        self.exp.module.run_a = tasks.Runner(mock_runner)

        self.assertEqual(
            self.exp.run(
                ['host1'], '', func_name='run_a', args={'foo': 'bar'}
            ), 'runner-return-value'
        )
        mock_runner.assert_called_once_with(
            ['host1'], {'foo': 'bar'}
        )

    def test_task(self):
        old_fab_execute = fabric_api.execute
        fabric_api.execute = mock.MagicMock(return_value={'test': 12})

        self.assertEqual(
            self.exp.run(['host1', 'host2'], '', func_name='task_a_a',
                         args=[12, 'test_1', 'test_2']),
            {'test': 12}
        )
        fabric_api.execute.assert_called_once_with(
            self.exp.module.task_a_a,
            ['host1', 'host2'], 12, 'test_1', 'test_2'
        )

        fabric_api.execute = old_fab_execute

    def test_parallel_runner(self):
        mock_runner = mock.MagicMock(return_value='runner-return-value')
        self.exp.module.run_a = tasks.ParallelRunner(mock_runner)

        with SettingsMock(self) as settings_mock:
            self.exp.run([], '', func_name='run_a'),
            settings_mock.assert_setting('parallel', True)


class SettingsMock(object):
    def __init__(self, test):
        self.test = test
        self.logged_settings = {}
        self.old_fab_settings = None

    def _log_settings(self, **kwargs):
        for key, value in kwargs.items():
            self.logged_settings[key] = value
        return self

    def __enter__(self):
        self.old_fab_settings = fabric_api.settings

        fabric_api.settings = mock.MagicMock(
            side_effect=self._log_settings
        )
        fabric_api.settings.__enter__ = mock.MagicMock()
        fabric_api.settings.__exit__ = mock.MagicMock(return_value=True)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        fabric_api.settings = self.old_fab_settings

    def assert_setting(self, key, value):
        self.test.assertEqual(self.logged_settings[key], value)
