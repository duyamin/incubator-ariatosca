# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
from datetime import datetime

from . import exceptions
from .context.workflow import WorkflowContext
from .workflows import builtin
from .workflows.core import graph_compiler
from .workflows.executor.process import ProcessExecutor
from ..modeling import models
from ..modeling import utils as modeling_utils
from ..utils.imports import import_fullname


DEFAULT_TASK_MAX_ATTEMPTS = 30
DEFAULT_TASK_RETRY_INTERVAL = 30


class ExecutionCompiler(object):
    def __init__(
            self,
            model,
            resource,
            plugin,
            service,
            workflow_name,
            task_max_attempts=None,
            task_retry_interval=None
    ):
        self._model = model
        self._resource = resource
        self._plugin = plugin
        self._service = service
        self._workflow_name = workflow_name
        self._workflow_context = None
        self._execution = None
        self._task_max_attempts = task_max_attempts or DEFAULT_TASK_MAX_ATTEMPTS
        self._task_retry_interval = task_retry_interval or DEFAULT_TASK_RETRY_INTERVAL

    @property
    def workflow_ctx(self):
        if self._workflow_context is None:
            self._workflow_context = WorkflowContext(
                name=self.__class__.__name__,
                model_storage=self._model,
                resource_storage=self._resource,
                service_id=self._execution.service.id,
                execution_id=self._execution.id,
                workflow_name=self._execution.workflow_name,
                task_max_attempts=self._task_max_attempts,
                task_retry_interval=self._task_retry_interval,
            )
        return self._workflow_context

    def compile(self, execution_inputs=None, executor=None, execution_id=None):
        assert not (execution_inputs and executor and execution_id)

        if execution_id is None:
            # If the execution is new
            self._execution = self._create_execution_model(execution_inputs)
            self._model.execution.put(self._execution)
            self._create_tasks(executor)
            self._model.execution.update(self._execution)
        else:
            # If resuming an execution
            self._execution = self._model.execution.get(execution_id)

        return self.workflow_ctx

    def _create_tasks(self, executor=None):

        # Set default executor and kwargs
        executor = executor or ProcessExecutor(plugin_manager=self._plugin)

        # transforming the execution inputs to dict, to pass them to the workflow function
        execution_inputs_dict = dict(inp.unwrapped for inp in self._execution.inputs.itervalues())

        if len(self._execution.tasks) == 0:
            workflow_fn = self._get_workflow_fn(self._execution.workflow_name)
            tasks_graph = workflow_fn(ctx=self.workflow_ctx, **execution_inputs_dict)
            compiler = graph_compiler.GraphCompiler(self.workflow_ctx, executor.__class__)
            compiler.compile(tasks_graph)

    def _create_execution_model(self, inputs=None):
        self._validate_workflow_exists_for_service()
        self._validate_no_active_executions()

        execution = models.Execution(
            created_at=datetime.utcnow(),
            service_fk=self._service.id,
            workflow_name=self._workflow_name,
            inputs={})

        if self._workflow_name in builtin.BUILTIN_WORKFLOWS:
            workflow_inputs = dict()  # built-in workflows don't have any inputs
        else:
            workflow_inputs = self._service.workflows[self._workflow_name].inputs

        modeling_utils.validate_no_undeclared_inputs(declared_inputs=workflow_inputs,
                                                     supplied_inputs=inputs or {})
        modeling_utils.validate_required_inputs_are_supplied(declared_inputs=workflow_inputs,
                                                             supplied_inputs=inputs or {})
        execution.inputs = modeling_utils.merge_parameter_values(
            inputs, workflow_inputs, model_cls=models.Input)

        return execution

    def _validate_no_active_executions(self):
        active_executions = [e for e in self._service.executions if
                             e.is_active()]
        if active_executions:
            raise exceptions.ActiveExecutionsError(
                "Can't start execution; Service {0} has an active execution with ID {1}"
                .format(self._service.name, active_executions[0].id))

    def _validate_workflow_exists_for_service(self):
        if self._workflow_name not in self._service.workflows and \
                        self._workflow_name not in builtin.BUILTIN_WORKFLOWS:
            raise exceptions.UndeclaredWorkflowError(
                'No workflow policy {0} declared in service {1}'
                .format(self._workflow_name, self._service.name))

    def _get_workflow_fn(self, workflow_name):
        if workflow_name in builtin.BUILTIN_WORKFLOWS:
            return import_fullname('{0}.{1}'.format(builtin.BUILTIN_WORKFLOWS_PATH_PREFIX,
                                                    workflow_name))

        workflow = self._service.workflows[workflow_name]

        # TODO: Custom workflow support needs improvement, currently this code uses internal
        # knowledge of the resource storage; Instead, workflows should probably be loaded
        # in a similar manner to operation plugins. Also consider passing to import_fullname
        # as paths instead of appending to sys path.
        service_template_resources_path = os.path.join(
            self._resource.service_template.base_path,
            str(self._service.service_template.id))
        sys.path.append(service_template_resources_path)

        try:
            workflow_fn = import_fullname(workflow.function)
        except ImportError:
            raise exceptions.WorkflowImplementationNotFoundError(
                'Could not find workflow {0} function at {1}'.format(
                    workflow_name, workflow.function))

        return workflow_fn
