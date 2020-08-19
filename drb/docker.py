from __future__ import unicode_literals

import pipes

import os
from subprocess import Popen, PIPE
from logging import getLogger

from drb.which import which
from drb.dbc import precondition

class SpawnedProcessError(Exception):

    def __init__(self, returncode, cmd, output="", error=""):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.error = error
        super(SpawnedProcessError, self).__init__(str(self))

    def __str__(self):
        return "Command '%s' returned non-zero exit status %d:\n%s\n%s\n" % (self.cmd, self.returncode, self.output, self.error)

def _ordered_unique(input_iterable):
    """returns an iterable which returns ordered, unique elements from input iterable.
    uses a set internally, so it can be quite slow for large inputs.
    """
    s = set()
    for item in input_iterable:
        if item not in s:
            s.add(item)
            yield item
    s.clear()


class Docker(object):
    def __init__(self,  docker_exec=which("docker")):
        # WARNING: whatever is set here as an instance variable will
        # be then passed to a shell,
        # and MUST be already quoted when set.
        self._docker_exec = pipes.quote(docker_exec)
        self._options = []
        self._image = None
        self._cmd_and_args = None
        self._logger = getLogger(self.__class__.__name__)

    # TODO: this addition is a bit clumsy, since it actually ignores
    # a lot of options, only taking image into account...
    # we should refactor this class to only have docker command
    # methods and returning sub-objects with the right options.
    def do_pull(self, ignore_errors=False):
        precondition(self._image is not None, "image must be set")

        fullcmd = "{docker_exec} pull {image}".format(
            docker_exec=self._docker_exec,
            image=self._image
        )

        self._logger.debug("Now executing:\n%s\n", fullcmd)

        process = Popen(fullcmd, stdout=PIPE, stderr=PIPE, shell=True)
        output, error = process.communicate()
        retcode = process.poll()
        if retcode and not ignore_errors:
            raise SpawnedProcessError(retcode, fullcmd, output=output, error=error)
        return output.strip()

    def do_launch_interactively(self):
        """Launch command in docker container; inherit fds from the parent, hence showing what happens inside the
        container in real time. returns None"""
        self._run(fds={"stdout":1, "stderr":2, "stdin":0})

    def do_run(self):
        """Launch command in docker container and get its stdout as result"""
        return self._run().strip()

    def _run(self, fds={"stdout":PIPE, "stderr":PIPE}):

        precondition(self._image is not None, "image must be set")
        precondition(self._cmd_and_args is not None, "cmd_and_args must be set")

        fullcmd = "{docker_exec} run {options} {image} {cmd_and_args}".format(
            docker_exec=self._docker_exec,
            options=" ".join(_ordered_unique(self._options)),
            image=self._image,
            cmd_and_args=" ".join(self._cmd_and_args)
        )

        self._logger.debug("Now executing:\n%s\n", fullcmd)

        process = Popen(fullcmd, shell=True, **fds)
        output, error = process.communicate()
        retcode = process.poll()
        if retcode:
            raise SpawnedProcessError(retcode, fullcmd, output=output, error=error)
        return output

    def additional_options(self, *options):
        self._options.extend([pipes.quote(opt) for opt in options])
        return self

    def env(self, key, value):
        precondition(isinstance(key, basestring), "key must be str or unicode")
        precondition(isinstance(value, basestring), "value must be str or unicode")

        self._options.append("--env={0}={1}".format(pipes.quote(key), pipes.quote(value)))
        return self

    def image(self, image):
        self._image = pipes.quote(image)
        return self

    def cmd_and_args(self, *caa):
        self._cmd_and_args = [pipes.quote(arg) for arg in caa]
        return self

    def rm(self):
        self._options.append("--rm")
        return self

    def interactive_and_tty(self):
        self._options.extend(["--interactive", "--tty"])
        return self

    def bindmount_dir(self, host_dir, guest_dir, read_only=False):
        precondition(os.access(host_dir, os.R_OK | os.X_OK), "host_dir must be readable and executable")
        precondition(os.path.isdir(host_dir), "host_dir must be a directory")
        precondition(os.path.isabs(guest_dir), "guest_dir must be absolute")

        option = "--volume={0}:{1}:z{2}".format(pipes.quote(os.path.abspath(host_dir)), pipes.quote(guest_dir), ("", ",ro")[read_only])
        self._options.append(option)
        return self

    def bindmount_file(self, host_file, guest_file, read_only=True):
        precondition(os.access(host_file, os.R_OK), "host_file must be readable and executable")
        precondition(os.path.isfile(host_file), "host_file must be a file")
        precondition(os.path.isabs(guest_file), "guest_file must be absolute")

        option = "--volume={0}:{1}:z{2}".format(pipes.quote(os.path.abspath(host_file)), pipes.quote(guest_file), ("", ",ro")[read_only])
        self._options.append(option)
        return self

    def privileged(self):
        self._options.append("--privileged")
        return self

    def tmpfs(self, guest_dir):
        precondition(os.path.isabs(guest_dir), "guest_dir must be absolute")
        option = "--tmpfs={0}".format(pipes.quote(guest_dir))
        self._options.append(option)
        return self

    def workdir(self, guest_dir):
        precondition(os.path.isabs(guest_dir), "guest_dir must be absolute")

        option = "--workdir={0}".format(pipes.quote(guest_dir))
        self._options.append(option)
        return self

    def init(self):
        self._options.append("--init")
        return self
