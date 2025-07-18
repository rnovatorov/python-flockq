import dataclasses
import datetime
import traceback
import uuid
from typing import Generator, Optional

from .cleanup_policy import CleanupPolicy
from .errors import TaskHandlerNotFound
from .retry_policy import RetryPolicy
from .task import Task
from .task_args import TaskArgs
from .task_handler import TaskHandler
from .task_handler_registry import TaskHandlerRegistry
from .task_repository import TaskRepository
from .task_specification import TaskIsDeletable, TaskIsExecutable


@dataclasses.dataclass
class TaskService:

    task_repository: TaskRepository
    task_handler_registry: TaskHandlerRegistry

    def register_task_handler(self, task_handler: TaskHandler) -> None:
        self.task_handler_registry.register_task_handler(task_handler)

    def create_task(
        self, kind: str, args: TaskArgs, delay: float, retry_policy: RetryPolicy
    ) -> Task:
        """
        Raises:
            IOError: IO error occurred during the operation.
        """
        task = Task.create(
            now=self._now(),
            id=str(uuid.uuid4()),
            kind=kind,
            args=args,
            delay=delay,
            retry_policy=retry_policy,
        )
        self.task_repository.add_task(task)
        return task

    def task(self, task_id: str) -> Task:
        """
        Raises:
            IOError: IO error occurred during the operation.
            TaskNotFoundError: Task was not found.
        """
        return self.task_repository.get_task(task_id)

    def deletable_tasks(self, cleanup_policy: CleanupPolicy) -> Generator[Task]:
        return self.task_repository.list_tasks(
            spec=TaskIsDeletable(self._now(), cleanup_policy)
        )

    def delete_task(self, task_id: str) -> None:
        """
        Raises:
            IOError: IO error occurred during the operation.
            TaskNotFoundError: Task was not found.
        """
        self.task_repository.delete_task(task_id)

    def executable_tasks(self) -> Generator[Task]:
        """
        Raises:
            IOError: IO error occurred during the operation.
        """
        return self.task_repository.list_tasks(
            spec=TaskIsExecutable(self._now(), self.task_handler_registry.task_kinds())
        )

    def execute_task(self, task_id: str) -> Task:
        """
        Raises:
            IOError: IO error occurred during the operation.
            TaskNotActiveError: Task is not in active state.
            TaskNotReadyError: Task is not ready yet.
            TaskLockedError: Task is currently locked by another thread.
            TaskNotFoundError: Task was not found.
            TaskHandlerNotFound: Task handler was not found.
        """
        with self.task_repository.update_task(task_id) as task:
            try:
                task_handler = self.task_handler_registry.task_handler(task.kind)
            except KeyError:
                raise TaskHandlerNotFound(task.kind)
            task.begin_execution(now=self._now())
            error: Optional[str] = None
            try:
                task_handler.handle_task(task)
            except Exception:
                error = traceback.format_exc()
            task.end_execution(now=self._now(), error=error)
            return task

    def _now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)
