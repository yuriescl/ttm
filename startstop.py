# Functions and classes are imported directly to get a smaller compiled binary
from typing import List, Dict, Optional, Tuple, Union
from re import match
from sys import exit, stderr, argv
from datetime import datetime
from shlex import join as shlex_join
from time import sleep
from json import load, dump
from json.encoder import encode_basestring
from os import makedirs, fsync, listdir, symlink, getuid, kill
from os.path import join, abspath
from asyncio import run as asyncio_run, create_subprocess_shell
from asyncio.subprocess import Process
from pathlib import Path
from subprocess import check_output, Popen
from multiprocessing.dummy import Pool as ThreadPool
from shutil import rmtree, get_terminal_size
from signal import SIGINT, SIGTERM, signal
from fcntl import lockf, LOCK_EX, LOCK_UN


CACHE_DIR = Path.home() / ".startstop"
makedirs(CACHE_DIR, exist_ok=True)
LOCK_PATH = Path(CACHE_DIR / "lock")
LOCK_PATH.touch(exist_ok=True)

BUSY_LOOP_INTERVAL = 0.1  # seconds
TIMESTAMP_FMT = "%Y%m%d%H%M%S"

Task = dict


class StartstopException(Exception):
    pass


class AtomicOpen:
    """ https://stackoverflow.com/a/46407326/3705710 """
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
            fsync(self.file.fileno())
            self.unlock_file(self.file)
            self.file.close()
            if exc_type is not None:
                return False
            else:
                return True


class bcolors:
    """ https://stackoverflow.com/a/287944/3705710 """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


##############
# ARG PARSING

def arg_requires_value(arg: str, option=None) -> bool:
    def dashes(a: str):
        return "-" if len(a) == 1 else "--"

    if option is None:
        if arg in ["v", "verbose"]:
            return False
    elif option == "run":
        if arg in ["a", "attach", "split-output"]:
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
    raise StartstopException(f"Unrecognized argument {dashes(arg)}{arg}")


def is_value_next(args: List[str], pos: int) -> bool:
    return pos + 1 < len(args) and not args[pos + 1].startswith("-")


def parse_args(args_to_parse: List[str]) -> Tuple[Dict, Optional[str], Dict, Optional[List[str]]]:
    args = args_to_parse[1:]
    global_args = {}
    option = None
    pos = 0
    while True:
        if pos >= len(args):
            break
        current_arg = args[pos]
        if current_arg in ["run", "start", "stop", "rm", "ls"]:
            option = current_arg
            pos += 1
            break
        elif current_arg.startswith("--"):
            current_arg = current_arg[2:]
            if arg_requires_value(current_arg, option):
                if not is_value_next(args, pos):
                    raise StartstopException(f"Argument --{current_arg} requires a value")
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
                        raise StartstopException(f"Argument -{current_arg} requires a value")
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

    option_args = {}
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
                        raise StartstopException(f"Argument --{current_arg} requires a value")
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


def create_task_cache(task: Task, split_output=False) -> Task:
    if task["name"] is not None:
        dir_name = f"{task['name']}-{task['id']}"
    else:
        dir_name = task["id"]
    dir_path = CACHE_DIR / dir_name
    makedirs(dir_path, exist_ok=True)
    filepath = dir_path / "task.json"
    timestamp = datetime.now().strftime(TIMESTAMP_FMT)
    shell_path = str(dir_path / task["id"])
    try:
        symlink("/bin/sh", shell_path)
    except FileExistsError:
        pass
    if split_output:
        stdout_path = dir_path / f"{dir_name}-{timestamp}.out"
        stderr_path = dir_path / f"{dir_name}-{timestamp}.err"
        task.update({
            "shell": str(shell_path),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "started_at": timestamp,
        })
    else:
        logs_path = dir_path / f"{dir_name}-{timestamp}.log"
        task.update({
            "shell": str(shell_path),
            "logs": str(logs_path),
            "started_at": timestamp,
        })
    with open(filepath, "w") as f:
        dump(task, f)
    return task


def update_task_cache(task: Task):
    if task["name"] is not None:
        dir_name = f"{task['name']}-{task['id']}"
    else:
        dir_name = task["id"]
    dir_path = CACHE_DIR / dir_name
    filepath = dir_path / "task.json"
    with open(filepath, "w") as f:
        dump(task, f)


def is_task_running(task: Task) -> bool:
    output = check_output(['ps', '-u', str(getuid()), '-o', 'pid,args'])
    for line in output.splitlines():
        decoded = line.decode().strip()
        ps_pid, cmdline = decoded.split(' ', 1)
        if ps_pid == task["pid"]:
            if cmdline.startswith(f"{task['shell']} -c"):
                return True
    return False


def find_task_by_name(name: str) -> Optional[Dict]:
    for filename in listdir(CACHE_DIR):
        if filename.split("-")[0] == name:
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            with open(path) as f:
                return load(f)
    return None


def find_task_by_id(task_id: str) -> Optional[Dict]:
    for filename in listdir(CACHE_DIR):
        try:
            filename_split = filename.split("-")
            if len(filename_split) == 1:
                filename_task_id = filename_split[0]
            else:
                filename_task_id = filename_split[1]
            if filename_task_id == task_id:
                path = abspath(join(CACHE_DIR, filename, "task.json"))
                with open(path) as f:
                    return load(f)
        except IndexError:
            pass
    return None


def remove_task_by_name(name: str):
    with AtomicOpen(LOCK_PATH):
        for filename in listdir(CACHE_DIR):
            filename_split = filename.split("-")
            if len(filename_split) == 1:
                raise StartstopException(f"No task with name {name}")
            else:
                filename_task_name = filename_split[0]

            if filename_task_name == name:
                task = find_task_by_name(name)
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
        for filename in listdir(CACHE_DIR):
            try:
                filename_split = filename.split("-")
                if len(filename_split) == 1:
                    filename_task_id = filename_split[0]
                else:
                    filename_task_id = filename_split[1]

                if filename_task_id == task_id:
                    task = find_task_by_id(task_id)
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


def signal_handler(process):
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
    for filename in listdir(CACHE_DIR):
        try:
            existing_ids.append(str(int(filename)))
        except ValueError:
            pass
    for i in range(1, 10000):
        str_i = str(i)
        if str_i not in existing_ids:
            return str_i
    raise StartstopException("Failed to generated task ID")


#############
# OPERATIONS

async def run(command: List[str], name=None, attached=False, split_output=False) -> Union[Task, Process]:
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task:
                if is_task_running(task):
                    raise StartstopException(f"Task {name} is already running with PID {task['pid']}")
                raise StartstopException(
                    f"Task {name} already exists and it's not running.\n"
                    "To remove it, run:\n"
                    f"startstop rm {name}"
                )
        task = {
            "id": generate_id(),
            "name": name,
            "command": command,
        }
        if split_output:
            task = create_task_cache(task, split_output=split_output)
            shell_path = task["shell"]
            stdout_path = task["stdout"]
            stderr_path = task["stderr"]
        else:
            task = create_task_cache(task, split_output=split_output)
            shell_path = task["shell"]
            logs_path = task["logs"]
        command = [shell_path, "-c", shlex_join(command)]
        if not attached:
            if split_output:
                with open(stdout_path, "wb") as out:
                    with open(stderr_path, "wb") as err:
                        proc = Popen(
                            command,
                            start_new_session=True,
                            stdout=out,
                            stderr=err,
                        )
            else:
                with open(logs_path, "wb") as output:
                    proc = Popen(
                        command,
                        start_new_session=True,
                        stdout=output,
                        stderr=output,
                    )
            task["pid"] = str(proc.pid)
            update_task_cache(task)
            return task
    if attached:
        return await create_subprocess_shell(*command)


async def run_attached(command: List[str], name=None):
    proc = await run(command, name=name, attached=True)
    for sig in [SIGINT, SIGTERM]:
        signal(sig, signal_handler(proc))
    await proc.wait()


def start_task(task_id=None, name=None):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task is not None:
                if is_task_running(task):
                    raise StartstopException(f"Task {name} is already running with PID {task['pid']}")
            else:
                raise StartstopException(f"No task with name {name}")
        else:
            task = find_task_by_id(task_id)
            if task is None:
                raise StartstopException(f"No task with ID {task_id}")

        if task["name"] is not None:
            dir_name = f"{task['name']}-{task['id']}"
        else:
            dir_name = task["id"]
        dir_path = CACHE_DIR / dir_name
        command = [task["shell"], "-c"] + task["command"]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if task.get("stdout") is not None:
            task["stdout"] = str(dir_path / f"{dir_name}-{timestamp}.out")
            task["stderr"] = str(dir_path / f"{dir_name}-{timestamp}.err")
            with open(task["stdout"], "wb") as out:
                with open(task["stderr"], "wb") as err:
                    proc = Popen(
                        command,
                        start_new_session=True,
                        stdout=out,
                        stderr=err,
                    )
        else:
            task["logs"] = str(dir_path / f"{dir_name}-{timestamp}.log")
            with open(task["logs"], "wb") as output:
                proc = Popen(
                    command,
                    start_new_session=True,
                    stdout=output,
                    stderr=output,
                )
        task["pid"] = str(proc.pid)
        task["started_at"] = timestamp
        update_task_cache(task)


def stop_task(task_id=None, name=None):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task is not None:
                if not is_task_running(task):
                    raise StartstopException(f"Task {name} is not running")
            else:
                raise StartstopException(f"No task with name {name}")
        else:
            task = find_task_by_id(task_id)
            if task is None:
                raise StartstopException(f"No task with ID {task_id}")

    # We kill and busy wait outside the above file lock for better parallel performance
    kill(int(task["pid"]), SIGTERM)
    while True:
        # TODO add timeout
        with AtomicOpen(LOCK_PATH):
            if not is_task_running(task):
                break
        sleep(BUSY_LOOP_INTERVAL)


def remove_all_tasks():
    with AtomicOpen(LOCK_PATH):
        for filename in listdir(CACHE_DIR):
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            try:
                with open(path) as f:
                    task = load(f)
                    if is_task_running(task):
                        print_error(f"Cannot remove task with ID {task['id']} since it's running")
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
            try:
                task_id = str(int(task_name_or_id))
                name = None
            except (ValueError, TypeError):
                task_id = None
                name = task_name_or_id

            if task_id is not None:
                remove_task_by_id(task_id)
            else:
                remove_task_by_name(name)
    except StartstopException as e:
        print_error(str(e))
        return False
    return True


def start(task_name_or_id: str) -> bool:
    try:
        task_id = str(int(task_name_or_id))
        name = None
    except (ValueError, TypeError):
        task_id = None
        name = task_name_or_id

    try:
        start_task(task_id=task_id, name=name)
        return True
    except StartstopException as e:
        print_error(str(e))
        return False


def stop(task_name_or_id: str):
    try:
        task_id = str(int(task_name_or_id))
        name = None
    except (ValueError, TypeError):
        task_id = None
        name = task_name_or_id

    try:
        stop_task(task_id=task_id, name=name)
        return True
    except StartstopException as e:
        print_error(str(e))
        return False


def ls(ls_all=False):
    tasks = []
    with AtomicOpen(LOCK_PATH):
        for filename in listdir(CACHE_DIR):
            path = abspath(join(CACHE_DIR, filename, "task.json"))
            try:
                with open(path) as f:
                    task = load(f)
                    if is_task_running(task):
                        started_at = datetime.strptime(task["started_at"], TIMESTAMP_FMT)
                        diff = datetime.now() - started_at
                        task["uptime"] = format_seconds(int(diff.total_seconds()))
                        tasks.append(task)
                    elif ls_all:
                        task["pid"] = "-"
                        task["uptime"] = "-"
                        tasks.append(task)
            except (NotADirectoryError, FileNotFoundError, ValueError):
                pass

    name_len_max = 4
    for task in tasks:
        if task["name"] is not None and len(task["name"]) > name_len_max:
            name_len_max = len(task["name"])

    columns = get_terminal_size((80, 20)).columns
    name_size = min(name_len_max, 16)
    command_size = columns - 21 - name_size
    template = r"{0:4} {1:NAME_SIZE} {2:COMMAND_SIZE} {3:6} {4:7}"
    template = template.replace("NAME_SIZE", str(name_size))
    template = template.replace("COMMAND_SIZE", str(command_size))
    print(template.format("ID", "NAME", "COMMAND", "UPTIME", "PID"))
    for task in tasks:
        print(template.format(task["id"], task["name"] or "-", shlex_join(task["command"]), task["uptime"], task["pid"]))

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


def print_error(msg: str, *args, **kwargs):
    print(f"{bcolors.FAIL}{msg}{bcolors.ENDC}", *args, **kwargs)


def print_warning(msg: str, *args, **kwargs):
    print(f"{bcolors.WARNING}{msg}{bcolors.ENDC}", *args, **kwargs)


def print_success(msg: str, *args, **kwargs):
    print(f"{bcolors.OKGREEN}{msg}{bcolors.ENDC}", *args, **kwargs)


def main():
    try:
        if len(argv) == 1:
            print_error("No option provided. Use -h for help.")
            exit(1)
        global_args, option, option_args, command = parse_args(argv)

        if option == "run":
            name = option_args.get("n") or option_args.get("name") or None
            if name is not None:
                if not match(r"^[a-zA-Z_]+$", name):
                    raise StartstopException("Only letters and underscore are allowed in task name")
            attached = option_args.get("a") or option_args.get("attached")
            if attached:
                asyncio_run(run_attached(command, name=name))
            else:
                asyncio_run(run(command, name=name))

        elif option == "rm":
            rm_all = option_args.get("a") or option_args.get("all") or None
            if rm_all is True:
                rm(None, rm_all=rm_all)
            else:
                pool = ThreadPool(len(command))
                results = pool.map(rm, command)
                if not all(results):
                    exit(1)

        elif option == "start":
            pool = ThreadPool(len(command))
            results = pool.map(start, command)
            if not all(results):
                exit(1)

        elif option == "stop":
            pool = ThreadPool(len(command))
            results = pool.map(stop, command)
            if not all(results):
                exit(1)

        elif option == "ls":
            ls_all = option_args.get("a") or option_args.get("all")
            ls(ls_all=ls_all)

    except StartstopException as e:
        print_error(str(e))
        exit(1)


if __name__ == "__main__":
    main()
