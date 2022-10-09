#!/usr/bin/env python

# startstop
# MIT License
# Copyright (c) 2022 Yuri Escalianti <yuriescl@gmail.com>
# Homepage: https://github.com/yuriescl/startstop

import asyncio
from asyncio.subprocess import Process
from datetime import datetime
from fcntl import LOCK_EX, LOCK_UN, lockf
import io
from io import SEEK_END, SEEK_SET
import json
from multiprocessing.dummy import Pool as ThreadPool
import os
from os.path import abspath, join
from pathlib import Path
import re
import shlex
from shutil import get_terminal_size, rmtree
from signal import SIGINT, SIGTERM, signal
from subprocess import Popen, check_output
from sys import argv, exit, stdout, stderr, version_info
import time
from time import sleep
from typing import Dict, List, Optional, Tuple, Union

if version_info[0] < 3 or version_info[1] < 8:
    raise Exception("Python 3.8+ is required to run this program")


CACHE_DIR = Path.home() / ".startstop"
os.makedirs(CACHE_DIR, exist_ok=True)
TMP_DIR = Path(f"/var/run/user/{str(os.getuid())}/startstop")
os.makedirs(TMP_DIR, exist_ok=True)
LOCK_FILE_NAME = "lock"
LOCK_PATH = Path(CACHE_DIR / LOCK_FILE_NAME)
LOCK_PATH.touch(exist_ok=True)

RESERVED_FILE_NAMES = [LOCK_FILE_NAME]

VERSION = "0.6.0"
BUSY_LOOP_INTERVAL = 0.1  # seconds
TIMESTAMP_FMT = "%Y%m%d%H%M%S"

Task = dict


class StartstopException(Exception):
    pass


class Tailer(object):
    """
    Code obtained from https://github.com/GreatFruitOmsk/tailhead/blob/master/tailhead/__init__.py
    Copyright (c) 2012 Mike Thornton
    Implements tailing and heading functionality like GNU tail and head
    commands.
    """

    LINE_TERMINATORS = (b"\r\n", b"\n", b"\r")

    def __init__(self, file, read_size=1024, end=False):
        if not isinstance(file, io.IOBase) or isinstance(file, io.TextIOBase):
            raise ValueError("io object must be in the binary mode")

        self.read_size = read_size
        self.file = file

        if end:
            self.file.seek(0, SEEK_END)

    def splitlines(self, data):
        return re.split(b"|".join(self.LINE_TERMINATORS), data)

    def read(self, read_size=-1):
        read_str = self.file.read(read_size)
        return len(read_str), read_str

    def prefix_line_terminator(self, data):
        for t in self.LINE_TERMINATORS:
            if data.startswith(t):
                return t

        return None

    def suffix_line_terminator(self, data):
        for t in self.LINE_TERMINATORS:
            if data.endswith(t):
                return t

        return None

    def seek_next_line(self):
        where = self.file.tell()
        offset = 0

        while True:
            data_len, data = self.read(self.read_size)
            data_where = 0

            if not data_len:
                break

            # Consider the following example: Foo\r | \nBar where " | " denotes current position,
            # 'Foo\r' is the read part and '\nBar' is the remaining part.
            # We should completely consume terminator "\r\n" by reading one extra byte.
            if b"\r\n" in self.LINE_TERMINATORS and data[-1] == b"\r"[0]:
                terminator_where = self.file.tell()
                terminator_len, terminator_data = self.read(1)

                if terminator_len and terminator_data[0] == b"\n"[0]:
                    data_len += 1
                    data += b"\n"
                else:
                    self.file.seek(terminator_where)

            while data_where < data_len:
                terminator = self.prefix_line_terminator(data[data_where:])
                if terminator:
                    self.file.seek(where + offset + data_where + len(terminator))
                    return self.file.tell()
                else:
                    data_where += 1

            offset += data_len
            self.file.seek(where + offset)

        return -1

    def seek_previous_line(self):
        where = self.file.tell()
        offset = 0

        while True:
            if offset == where:
                break

            read_size = self.read_size if self.read_size <= where else where
            self.file.seek(where - offset - read_size, SEEK_SET)
            data_len, data = self.read(read_size)

            # Consider the following example: Foo\r | \nBar where " | " denotes current position,
            # '\nBar' is the read part and 'Foo\r' is the remaining part.
            # We should completely consume terminator "\r\n" by reading one extra byte.
            if b"\r\n" in self.LINE_TERMINATORS and data[0] == b"\n"[0]:
                terminator_where = self.file.tell()
                if terminator_where > data_len + 1:
                    self.file.seek(where - offset - data_len - 1, SEEK_SET)
                    terminator_len, terminator_data = self.read(1)

                    if terminator_data[0] == b"\r"[0]:
                        data_len += 1
                        data = b"\r" + data

                    self.file.seek(terminator_where)

            data_where = data_len

            while data_where > 0:
                terminator = self.suffix_line_terminator(data[:data_where])
                if terminator and offset == 0 and data_where == data_len:
                    # The last character is a line terminator that finishes current line. Ignore it.
                    data_where -= len(terminator)
                elif terminator:
                    self.file.seek(where - offset - (data_len - data_where))
                    return self.file.tell()
                else:
                    data_where -= 1

            offset += data_len

        if where == 0:
            # Nothing more to read.
            return -1
        else:
            # Very first line.
            self.file.seek(0)
            return 0

    def tail(self, lines=10):
        self.file.seek(0, SEEK_END)

        for i in range(lines):
            if self.seek_previous_line() == -1:
                break

        data = self.file.read()

        for t in self.LINE_TERMINATORS:
            if data.endswith(t):
                # Only terminators _between_ lines should be preserved.
                # Otherwise terminator of the last line will be treated as separtaing line and empty line.
                data = data[: -len(t)]
                break

        if data:
            return self.splitlines(data)
        else:
            return []

    def head(self, lines=10):
        if lines < 0:
            self.file.seek(0, SEEK_END)
            for i in range(-lines):
                if self.seek_previous_line() == -1:
                    break
        else:
            self.file.seek(0)
            for i in range(lines):
                if self.seek_next_line() == -1:
                    break

        end_pos = self.file.tell()

        self.file.seek(0)
        data = self.file.read(end_pos)

        for t in self.LINE_TERMINATORS:
            if data.endswith(t):
                # Only terminators _between_ lines should be preserved.
                # Otherwise terminator of the last line will be treated as separtaing line and empty line.
                data = data[: -len(t)]
                break

        if data:
            return self.splitlines(data)
        else:
            return []

    def follow(self):
        trailing = True

        while True:
            where = self.file.tell()

            if where > os.fstat(self.file.fileno()).st_size:
                # File was truncated.
                where = 0
                self.file.seek(where)

            line = self.file.readline()

            if line:
                if trailing and line in self.LINE_TERMINATORS:
                    # This is just the line terminator added to the end of the file
                    # before a new line, ignore.
                    trailing = False
                    continue

                terminator = self.suffix_line_terminator(line)
                if terminator:
                    line = line[: -len(terminator)]

                trailing = False
                yield line
            else:
                trailing = True
                self.file.seek(where)
                yield None


class AtomicOpen:
    """https://stackoverflow.com/a/46407326/3705710"""

    def __init__(self, path, *args, noop=False, **kwargs):
        if noop is False:
            self.file = open(path, *args, **kwargs)
            self.lock_file(self.file)
        self.noop = noop

    @staticmethod
    def lock_file(f):
        if f.writable():
            lockf(f, LOCK_EX)

    @staticmethod
    def unlock_file(f):
        if f.writable():
            lockf(f, LOCK_UN)

    def __enter__(self, *args, **kwargs):
        if self.noop is False:
            return self.file

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        if self.noop is False:
            self.file.flush()
            os.fsync(self.file.fileno())
            self.unlock_file(self.file)
            self.file.close()
            if exc_type is not None:
                return False
            else:
                return True


class bcolors:
    """https://stackoverflow.com/a/287944/3705710"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    LIGHTGREY = "\033[0;37m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


##############
# ARG PARSING


def arg_requires_value(arg: str, option: Optional[str] = None) -> bool:
    def dashes(a: str):
        return "-" if len(a) == 1 else "--"

    if option is None:
        if arg in ["v", "verbose", "version"]:
            return False
    elif option == "run":
        if arg in ["s", "shell", "split-output"]:
            return False
        if arg in ["n", "name"]:
            return True
    elif option == "start":
        pass
    elif option == "stop":
        if arg in ["k"]:
            return False
    elif option == "rm":
        if arg in ["a", "all"]:
            return False
    elif option == "ls":
        if arg in ["a", "all"]:
            return False
    elif option == "logs":
        if arg in ["f", "follow", "head"]:
            return False
    raise StartstopException(f"Unrecognized argument {dashes(arg)}{arg}")


def is_value_next(args: List[str], pos: int) -> bool:
    return pos + 1 < len(args) and not args[pos + 1].startswith("-")


def parse_args(
    args_to_parse: List[str],
) -> Tuple[Dict, Optional[str], Dict, Optional[List[str]]]:
    args = args_to_parse[1:]
    global_args: Dict[str, Union[str, bool]] = {}
    option = None
    pos = 0
    while True:
        if pos >= len(args):
            break
        current_arg = args[pos]
        if current_arg in ["run", "start", "stop", "rm", "ls", "logs"]:
            option = current_arg
            pos += 1
            break
        elif current_arg.startswith("--"):
            current_arg = current_arg[2:]
            if arg_requires_value(current_arg, option):
                if not is_value_next(args, pos):
                    raise StartstopException(
                        f"Argument --{current_arg} requires a value"
                    )
                global_args[current_arg] = args[pos + 1]
                pos += 2
                continue
            else:
                global_args[current_arg] = True
                pos += 1
                continue
        elif current_arg.startswith("-"):
            current_arg = current_arg[1:]
            if len(current_arg) == 1:
                if arg_requires_value(current_arg, option):
                    if not is_value_next(args, pos):
                        raise StartstopException(
                            f"Argument -{current_arg} requires a value"
                        )
                    global_args[current_arg] = args[pos + 1]
                    pos += 2
                    continue
                else:
                    global_args[current_arg] = True
                    pos += 1
                    continue
            else:
                for letter in current_arg:
                    if arg_requires_value(letter, option):
                        raise StartstopException(
                            f"Argument -{letter} cannot be grouped with other arguments"
                        )
                    global_args[letter] = True
                    pos += 1
                    continue
        else:
            raise StartstopException(f"Unrecognized option {current_arg}")
        pos += 1

    option_args: Dict[str, Union[str, bool]] = {}
    command = None

    if option is not None:
        if pos >= len(args) and option not in ["ls"]:
            raise StartstopException(f"Missing arguments for option '{option}'")
        while True:
            if pos >= len(args):
                break
            current_arg = args[pos]
            if current_arg.startswith("--"):
                current_arg = current_arg[2:]
                if arg_requires_value(current_arg, option):
                    if not is_value_next(args, pos):
                        raise StartstopException(
                            f"Argument --{current_arg} requires a value"
                        )
                    option_args[current_arg] = args[pos + 1]
                    pos += 2
                    continue
                else:
                    option_args[current_arg] = True
                    pos += 1
                    continue
            elif current_arg.startswith("-"):
                current_arg = current_arg[1:]
                if len(current_arg) == 1:
                    if arg_requires_value(current_arg, option):
                        if not is_value_next(args, pos):
                            raise StartstopException(
                                f"Argument -{current_arg} requires a value"
                            )
                        option_args[current_arg] = args[pos + 1]
                        pos += 2
                        continue
                    else:
                        option_args[current_arg] = True
                        pos += 1
                        continue
                else:
                    for letter in current_arg:
                        if arg_requires_value(letter, option) and not is_value_next(
                            args, pos
                        ):
                            raise StartstopException(
                                f"Argument -{letter} cannot be grouped with other arguments"
                            )
                        option_args[letter] = True
                        pos += 1
                        continue
            else:
                command = args[pos:]
                break

    return global_args, option, option_args, command


##################
# FILE OPERATIONS


def get_task_label(task: Task):
    if task["name"] is not None:
        return f"{task['name']}-{task['id']}"
    else:
        return task["id"]


def parse_task_id_or_name(task_name_or_id: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        task_id = str(int(task_name_or_id))
        name = None
    except (ValueError, TypeError):
        task_id = None
        name = task_name_or_id
    return task_id, name


def create_pidfile(task: Task):
    if task.get("pid") is not None:
        with open(TMP_DIR / f"{get_task_label(task)}.pid", "w") as f:
            f.write(task["pid"])


def create_task_cache(task: Task, split_output=False) -> Task:
    dir_name = get_task_label(task)
    dir_path = CACHE_DIR / dir_name
    os.makedirs(dir_path, exist_ok=True)
    filepath = dir_path / "task.json"
    timestamp = datetime.now().strftime(TIMESTAMP_FMT)
    if split_output:
        stdout_path = dir_path / f"{dir_name}-{timestamp}.out"
        stderr_path = dir_path / f"{dir_name}-{timestamp}.err"
        task.update(
            {
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "started_at": timestamp,
            }
        )
    else:
        logs_path = dir_path / f"{dir_name}-{timestamp}.log"
        task.update(
            {
                "logs": str(logs_path),
                "started_at": timestamp,
            }
        )
    with open(filepath, "w") as f:
        task_to_dump = dict(task)
        task_to_dump.pop("pid", None)
        json.dump(task_to_dump, f)
    create_pidfile(task)
    return task


def update_task_cache(task: Task):
    dir_name = get_task_label(task)
    dir_path = CACHE_DIR / dir_name
    filepath = dir_path / "task.json"
    with open(filepath, "w") as f:
        task_to_dump = dict(task)
        task_to_dump.pop("pid", None)
        json.dump(task_to_dump, f)
    create_pidfile(task)


def is_task_running(task: Task) -> bool:
    output = check_output(["ps", "-u", str(os.getuid()), "-o", "pid,args"])
    for line in output.splitlines():
        decoded = line.decode().strip()
        ps_pid, cmdline = decoded.split(" ", 1)
        if task.get("pid") is not None and ps_pid == task["pid"]:
            return True
    return False


def get_task_from_cache_file(cache_file_path: str):
    with open(cache_file_path) as f:
        task = json.load(f)
    pidfile = TMP_DIR / f"{get_task_label(task)}.pid"
    if pidfile.exists():
        with open(pidfile, "r") as f:
            task["pid"] = f.read()
    return task


def find_task_by_name(name: str) -> Optional[Task]:
    for filename in os.listdir(CACHE_DIR):
        if filename not in RESERVED_FILE_NAMES and filename.split("-")[0] == name:
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            return get_task_from_cache_file(path)
    return None


def find_task_by_id(task_id: str) -> Optional[Dict]:
    for filename in os.listdir(CACHE_DIR):
        if filename in RESERVED_FILE_NAMES:
            continue
        try:
            filename_split = filename.split("-")
            if len(filename_split) == 1:
                filename_task_id = filename_split[0]
            else:
                filename_task_id = filename_split[1]
            if filename_task_id == task_id:
                path = abspath(join(CACHE_DIR, filename, "task.json"))
                return get_task_from_cache_file(path)
        except IndexError:
            pass
    return None


def remove_task_by_name(name: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            filename_split = filename.split("-")
            if len(filename_split) == 1:
                continue
            else:
                filename_task_name = filename_split[0]

            if filename_task_name == name:
                task = find_task_by_name(name)
                if task is None:
                    raise StartstopException("Failed to find task by name")
                if is_task_running(task):
                    raise StartstopException(
                        "Cannot remove task while it's running.\n"
                        "To stop it, run:\n"
                        f"startstop stop {name}"
                    )
                dir_path = abspath(join(CACHE_DIR, filename))
                rmtree(dir_path)
                return
        raise StartstopException(f"No task with name {name}")


def remove_task_by_id(task_id: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            try:
                filename_split = filename.split("-")
                if len(filename_split) == 1:
                    filename_task_id = filename_split[0]
                else:
                    filename_task_id = filename_split[1]

                if filename_task_id == task_id:
                    task = find_task_by_id(task_id)
                    if task is None:
                        raise StartstopException("Failed to find task by id")
                    if is_task_running(task):
                        raise StartstopException(
                            "Cannot remove task while it's running.\n"
                            "To stop it, run:\n"
                            f"startstop stop {task_id}"
                        )
                    dir_path = abspath(join(CACHE_DIR, filename))
                    rmtree(dir_path)
                    return
            except IndexError:
                pass
        raise StartstopException(f"No task with ID {task_id}")


def process_signal_handler(process: Process):
    def wrapper(signum, frame):
        process.send_signal(signum)
        if signum == SIGINT:
            print("Interrupted", file=stderr)
            exit(1)
        if signum == SIGTERM:
            print("Terminated", file=stderr)
            exit(1)

    return wrapper


def generate_id():
    existing_ids = []
    for filename in os.listdir(CACHE_DIR):
        try:
            existing_ids.append(str(int(filename)))
        except ValueError:
            try:
                existing_ids.append(str(int(filename.split("-")[1])))
            except (ValueError, IndexError):
                pass
    for i in range(1, 10000):
        str_i = str(i)
        if str_i not in existing_ids:
            return str_i
    raise StartstopException("Failed to generated task ID")


#############
# OPERATIONS


async def run(
    command: List[str],
    name: Optional[str] = None,
    split_output=False,
    shell=False,
) -> Optional[Union[Task, Process]]:
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task:
                if is_task_running(task):
                    raise StartstopException(
                        f"Task {name} is already running with PID {task['pid']}"
                    )
                raise StartstopException(
                    f"Task {name} already exists and it's not running.\n"
                    "To remove it, run:\n"
                    f"startstop rm {name}"
                )
        task = {
            "id": generate_id(),
            "name": name,
            "command": command,
            "shell": shell,
        }
        if split_output:
            task = create_task_cache(task, split_output=split_output)
            stdout_path = task["stdout"]
            stderr_path = task["stderr"]
            logs_path = ""
        else:
            task = create_task_cache(task, split_output=split_output)
            stdout_path = ""
            stderr_path = ""
            logs_path = task["logs"]
        if split_output:
            with open(stdout_path, "wb") as out:
                with open(stderr_path, "wb") as err:
                    proc = Popen(
                        command if not shell else shlex.join(command),
                        shell=shell,
                        stdout=out,
                        stderr=err,
                    )
        else:
            with open(logs_path, "wb") as output:
                proc = Popen(
                    command if not shell else shlex.join(command),
                    shell=shell,
                    stdout=output,
                    stderr=output,
                )
        task["pid"] = str(proc.pid)
        update_task_cache(task)
        return task
    return None


def start_task(task_id: Optional[str] = None, name: Optional[str] = None):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task is not None:
                if is_task_running(task):
                    raise StartstopException(
                        f"Task {name} is already running with PID {task['pid']}"
                    )
            else:
                raise StartstopException(f"No task with name {name}")
        elif task_id is not None:
            task = find_task_by_id(task_id)
            if task is None:
                raise StartstopException(f"No task with ID {task_id}")
        else:
            raise ValueError("Either task_id or name must be set")

        if task["name"] is not None:
            dir_name = f"{task['name']}-{task['id']}"
        else:
            dir_name = task["id"]
        dir_path = CACHE_DIR / dir_name
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if task.get("stdout") is not None:
            task["stdout"] = str(dir_path / f"{dir_name}-{timestamp}.out")
            task["stderr"] = str(dir_path / f"{dir_name}-{timestamp}.err")
            with open(task["stdout"], "wb") as out:
                with open(task["stderr"], "wb") as err:
                    proc = Popen(
                        (
                            task["command"]
                            if not task["shell"]
                            else shlex.join(task["command"])
                        ),
                        shell=task["shell"],
                        stdout=out,
                        stderr=err,
                    )
        else:
            task["logs"] = str(dir_path / f"{dir_name}-{timestamp}.log")
            with open(task["logs"], "wb") as output:
                proc = Popen(
                    (
                        task["command"]
                        if not task["shell"]
                        else shlex.join(task["command"])
                    ),
                    shell=task["shell"],
                    stdout=output,
                    stderr=output,
                )
        task["pid"] = str(proc.pid)
        task["started_at"] = timestamp
        update_task_cache(task)


def stop_task(task_id: Optional[str] = None, name: Optional[str] = None):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task is not None:
                if not is_task_running(task):
                    raise StartstopException(f"Task {name} is not running")
            else:
                raise StartstopException(f"No task with name {name}")
        elif task_id is not None:
            task = find_task_by_id(task_id)
            if task is None:
                raise StartstopException(f"No task with ID {task_id}")
        else:
            raise ValueError("Either task_id or name must be set")

    # We kill and busy wait outside the above file lock for better parallel performance
    os.kill(int(task["pid"]), SIGTERM)
    while True:
        # TODO add timeout
        with AtomicOpen(LOCK_PATH):
            if not is_task_running(task):
                break
        sleep(BUSY_LOOP_INTERVAL)


def remove_all_tasks():
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            if filename in RESERVED_FILE_NAMES:
                continue
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            try:
                task = get_task_from_cache_file(path)
                if is_task_running(task):
                    print_error(
                        f"Cannot remove task with ID {task['id']} since it's running"
                    )
                else:
                    dir_path = abspath(join(CACHE_DIR, filename))
                    rmtree(dir_path)
            except (NotADirectoryError, FileNotFoundError, ValueError):
                pass


def rm(task_name_or_id: Optional[str], rm_all=False) -> bool:
    try:
        if rm_all:
            remove_all_tasks()
        else:
            if task_name_or_id is None:
                raise ValueError("task_name_or_id is None")
            task_id, name = parse_task_id_or_name(task_name_or_id)
            if task_id is not None:
                remove_task_by_id(task_id)
            elif name is not None:
                remove_task_by_name(name)
    except StartstopException as e:
        print_error(str(e))
        return False
    return True


def logs(task_name_or_id: str, follow=False, head=False):
    def print_lines(lines):
        if isinstance(lines, list):
            for line in lines:
                stdout.buffer.write(line)
                stdout.buffer.write("\n".encode())
        elif isinstance(lines, bytes):
            stdout.buffer.write(lines)
            stdout.buffer.write("\n".encode())
        stdout.buffer.flush()

    if follow and head:
        raise StartstopException("--follow and --head cannot be used together")

    task_id, name = parse_task_id_or_name(task_name_or_id)

    if task_id is not None:
        task = find_task_by_id(task_id)
        if task is None:
            raise StartstopException(f"No task with ID {task_id}")
    elif name is not None:
        task = find_task_by_name(name)
        if task is None:
            raise StartstopException(f"No task with name {name}")
    else:
        raise ValueError("task_id and name are None")

    logs_path = task.get("logs")
    if logs_path is None:
        raise StartstopException(
            "Task was created using --split-output, use 'stdout' or 'stderr' instead of 'logs'"
        )

    line_count = 15

    if not head and follow:
        with open(logs_path, "rb") as file:
            print_grey(f"{logs_path} last {line_count} lines:")
            print_lines(Tailer(file).tail(lines=line_count))

    with open(logs_path, "rb") as file:
        if head:
            print_grey(f"{logs_path} first {line_count} lines:")
            print_lines(Tailer(file).head(lines=line_count))
        elif follow:
            print_grey(f"{logs_path} followed tail:")
            for line in Tailer(file, end=True).follow():
                if line is None:
                    time.sleep(0.01)
                    continue
                print_lines(line)
        else:
            print_grey(f"{logs_path} last {line_count} lines:")
            print_lines(Tailer(file).tail(lines=line_count))

        print_lines([])


def start(task_name_or_id: str) -> bool:
    task_id, name = parse_task_id_or_name(task_name_or_id)

    try:
        start_task(task_id=task_id, name=name)
        return True
    except StartstopException as e:
        print_error(str(e))
        return False


def stop(task_name_or_id: str):
    task_id, name = parse_task_id_or_name(task_name_or_id)

    try:
        stop_task(task_id=task_id, name=name)
        return True
    except StartstopException as e:
        print_error(str(e))
        return False


def ls(ls_all=False, command: Optional[List[str]] = None):
    tasks = []
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            if filename in RESERVED_FILE_NAMES:
                continue
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            force_list = False
            if command:
                for task_name_or_id in command:
                    task_id, name = parse_task_id_or_name(task_name_or_id)
                    filename_split = filename.split("-")
                    if task_id in filename_split or name in filename_split:
                        force_list = True
                if not force_list:
                    continue
            try:
                task = get_task_from_cache_file(path)
                task["started_at"] = datetime.strptime(
                    task["started_at"], TIMESTAMP_FMT
                )
                if is_task_running(task):
                    diff = datetime.now() - task["started_at"]
                    task["uptime"] = format_seconds(int(diff.total_seconds()))
                    tasks.append(task)
                elif ls_all or force_list:
                    task["pid"] = "-"
                    task["uptime"] = "-"
                    tasks.append(task)
            except (NotADirectoryError, FileNotFoundError, ValueError):
                pass

    name_len_max = 4
    for task in tasks:
        if task["name"] is not None and len(task["name"]) > name_len_max:
            name_len_max = len(task["name"])

    tasks = sorted(tasks, key=lambda d: d["started_at"])

    columns = get_terminal_size((80, 20)).columns
    name_size = min(name_len_max, 16)
    command_size = columns - 21 - name_size
    template = r"{0:4} {1:NAME_SIZE} {2:6} {3:7} {4:COMMAND_SIZE}"
    template = template.replace("NAME_SIZE", str(name_size))
    template = template.replace("COMMAND_SIZE", str(command_size))
    print(template.format("ID", "NAME", "UPTIME", "PID", "COMMAND"))
    for task in tasks:
        print(
            template.format(
                task["id"],
                task["name"] or "-",
                task["uptime"],
                task["pid"],
                shlex.join(task["command"]),
            )
        )


#######
# MISC


def format_seconds(seconds, long=False):
    if long:
        raise NotImplementedError()
    else:
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        s = ""
        if days > 0:
            s += f"{days}d"
        elif hours > 0:
            s += f"{hours}h"
        elif minutes > 0:
            s += f"{minutes}m"
        else:
            s += f"{seconds}s"
        return s


def signal_handler(signum, frame):
    if signum == SIGINT:
        exit(1)
    if signum == SIGTERM:
        exit(1)


def print_error(msg: str, *args, **kwargs):
    if "file" not in kwargs:
        kwargs["file"] = stderr
    print(f"{bcolors.FAIL}{msg}{bcolors.ENDC}", *args, **kwargs)


def print_grey(msg: str, *args, **kwargs):
    print(f"{bcolors.LIGHTGREY}{msg}{bcolors.ENDC}", *args, **kwargs)


def print_warning(msg: str, *args, **kwargs):
    if "file" not in kwargs:
        kwargs["file"] = stderr
    print(f"{bcolors.WARNING}{msg}{bcolors.ENDC}", *args, **kwargs)


def print_success(msg: str, *args, **kwargs):
    print(f"{bcolors.OKGREEN}{msg}{bcolors.ENDC}", *args, **kwargs)


def main():
    for sig in [SIGINT, SIGTERM]:
        signal(sig, signal_handler)

    try:
        if len(argv) == 1:
            print_error("No option provided. Use -h for help.")
            exit(1)
        global_args, option, option_args, command = parse_args(argv)

        if option is None:
            version = global_args.get("version")
            if version:
                print(VERSION)
                return
        elif option == "run":
            name = option_args.get("n") or option_args.get("name") or None
            if name is not None:
                if not re.match(r"^[a-zA-Z_]+$", name):
                    raise StartstopException(
                        "Only letters and underscore are allowed in task name"
                    )
            shell = bool(option_args.get("s") or option_args.get("shell"))
            if command is None:
                raise StartstopException("A command must be provided")
            asyncio.run(run(command, name=name, shell=shell))

        elif option == "rm":
            rm_all = option_args.get("a") or option_args.get("all")
            if rm_all is True:
                rm(None, rm_all=rm_all)
            else:
                if command is None:
                    raise StartstopException("Task ID or name must be provided")
                pool = ThreadPool(len(command))
                results = pool.map(rm, command)
                if not all(results):
                    exit(1)

        elif option == "start":
            if command is None:
                raise StartstopException("Task ID or name must be provided")
            pool = ThreadPool(len(command))
            results = pool.map(start, command)
            if not all(results):
                exit(1)

        elif option == "stop":
            if command is None:
                raise StartstopException("Task ID or name must be provided")
            pool = ThreadPool(len(command))
            results = pool.map(stop, command)
            if not all(results):
                exit(1)

        elif option == "ls":
            ls_all = bool(option_args.get("a") or option_args.get("all"))
            if command:
                if ls_all:
                    raise StartstopException(
                        "-a/--all is not allowed when specific tasks are provided"
                    )
            ls(ls_all=ls_all, command=command)

        elif option == "logs":
            if command is None:
                raise StartstopException("Task ID or name must be provided")
            if len(command) > 1:
                raise StartstopException(
                    "A single task ID or name must be provided to 'logs'"
                )
            follow = option_args.get("f") or option_args.get("follow") or False
            head = option_args.get("head") or False
            logs(command[0], follow=follow, head=head)

    except StartstopException as e:
        print_error(str(e))
        exit(1)


if __name__ == "__main__":
    main()
