import logging
from contextlib import contextmanager

import amqp

from kuyruk import exceptions
from kuyruk.task import Task
from kuyruk.config import Config
from kuyruk.worker import Worker

__version__ = '7.0.0'
__all__ = ['Kuyruk', 'Config', 'Task', 'Worker']


logger = logging.getLogger(__name__)


# Add NullHandler to prevent logging warnings on startup
null_handler = logging.NullHandler()
logger.addHandler(null_handler)


class Kuyruk(object):
    """
    Provides :func:`~kuyruk.Kuyruk.task` decorator to convert a function
    into a :class:`~kuyruk.Task`.

    Provides :func:`~kuyruk.Kuyruk.channel` context manager for opening a
    new channel on the connection.
    Connection is opened when the first channel is created.

    :param config: Must be an instance of :class:`~kuyruk.Config`.
                   If ``None``, default config is used.
                   See :class:`~kuyruk.Config` for default values.

    """
    # Aliases for raising from tasks
    Reject = exceptions.Reject
    Discard = exceptions.Discard

    def __init__(self, config=None):
        if config is None:
            config = Config()
        if not isinstance(config, Config):
            raise TypeError
        self.config = config
        self.extensions = {}

    def task(self, queue='kuyruk', retry=0, max_run_time=None):
        """
        Wrap functions with this decorator to convert them to *tasks*.
        After wrapping, calling the function will send a message to
        a queue instead of running the function.

        :param queue: Queue name for the tasks.
        :param retry: Retry this times before give up.
            The failed task will be retried in the same worker.
        :param max_run_time: Maximum allowed time in seconds for task to
            complete.
        :return: Callable :class:`~kuyruk.Task` object wrapping the original
            function.

        """
        def decorator():
            def inner(f):
                # Function may be wrapped with no-arg decorator
                queue_ = 'kuyruk' if callable(queue) else queue

                return Task(
                    f, self, queue=queue_,
                    retry=retry, max_run_time=max_run_time)
            return inner

        if callable(queue):
            # task without args
            return decorator()(queue)
        else:
            # task with args
            return decorator()

    @contextmanager
    def channel(self):
        """Returns a new channel from a new connection as a context manager.
        """
        with self.connection() as conn:
            ch = conn.channel()
            logger.info('Opened new channel')
            try:
                yield ch
            finally:
                if ch.is_open:
                    try:
                        ch.close()
                    except IOError:
                        pass

    @contextmanager
    def connection(self):
        """Returns a new connection as a context manager."""
        conn = amqp.Connection(
            host="%s:%s" % (self.config.RABBIT_HOST, self.config.RABBIT_PORT),
            userid=self.config.RABBIT_USER,
            password=self.config.RABBIT_PASSWORD,
            virtual_host=self.config.RABBIT_VIRTUAL_HOST)

        # from amqp==2.0.0 explicit connect is required.
        try:
            conn.connect()
        except AttributeError:
            pass

        logger.info('Connected to RabbitMQ')
        try:
            yield conn
        finally:
            if _is_alive(conn):
                conn.close()


def _is_alive(conn):
    try:
        conn.send_heartbeat()
    except IOError:
        return False
    else:
        return True
