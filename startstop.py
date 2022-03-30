from typing import List, Dict
import sys
from datetime import datetime
import json
import os
from os.path import join, abspath
import asyncio
from pathlib import Path
import subprocess
from multiprocessing.dummy import Pool as ThreadPool
import shutil
import signal
import fcntl



# TODO raise error if OS is not unix
CACHE_DIR = Path.home() / ".startstop"
os.makedirs(CACHE_DIR, exist_ok=True)
LOCK_PATH = Path(CACHE_DIR / "lock")
LOCK_PATH.touch(exist_ok=True)


class StartstopException(Exception):
    pass

class AtomicOpen:
    """ https://stackoverflow.com/a/46407326/3705710 """
    def __init__(self, path, *args, noop=False, **kwargs):
        if noop is False:
            self.file = open(path,*args, **kwargs)
            self.lock_file(self.file)
        self.noop = noop

    def lock_file(self, f):
        if f.writable():
            fcntl.lockf(f, fcntl.LOCK_EX)

    def unlock_file(self, f):
        if f.writable():
            fcntl.lockf(f, fcntl.LOCK_UN)

    def __enter__(self, *args, **kwargs):
        if self.noop is False:
            return self.file

    def __exit__(self, exc_type=None, exc_value=None, traceback=None):
        if self.noop is False:
            self.file.flush()
            os.fsync(self.file.fileno())
            self.unlock_file(self.file)
            self.file.close()
            if (exc_type is not None):
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

def arg_requires_value(arg: str, option=None):
    if option is None:
        if arg in ["v", "verbose"]:
            return False
        raise StartstopException(f"Unrecognized argument --{arg}")
    elif option == "run":
        if arg in ["a", "attach", "split-output"]:
            return False
        if arg in ["n", "name"]:
            return True
        raise StartstopException(f"Unrecognized argument --{arg}")
    elif option == "start":
        raise StartstopException(f"Unrecognized argument --{arg}")
    elif option == "stop":
        if arg in ["k"]:
            return False
        raise StartstopException(f"Unrecognized argument --{arg}")
    elif option == "rm":
        raise StartstopException(f"Unrecognized argument --{arg}")


def is_value_next(args: List[str], pos: int):
    return pos + 1 < len(args) and not args[pos + 1].startswith("-")


def parse_args(argv: List[str]):
    args = argv[1:]
    global_args = {}
    option = None
    pos = 0
    while True:
        if pos >= len(args):
            break
        current_arg = args[pos]
        if current_arg in ["run", "start", "stop", "rm"]:
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
        if pos >= len(args):
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


def find_task_by_name(name: str, lock=True) -> Dict:
    with AtomicOpen(LOCK_PATH, noop=not lock):
        for filename in os.listdir(CACHE_DIR):
            if filename.split("-")[0] == name:
                path = abspath(join(CACHE_DIR, filename, "task.json"))
                with open(path) as f:
                    return json.load(f)
        return None


def find_task_by_id(task_id: str, lock=True) -> Dict:
    with AtomicOpen(LOCK_PATH, noop=not lock):
        for filename in os.listdir(CACHE_DIR):
            try:
                if filename.split("-")[1] == task_id:
                    path = abspath(join(CACHE_DIR, filename, "task.json"))
                    with open(path) as f:
                        return json.load(f)
            except IndexError as e:
                pass
        return None


def create_task_cache(task: Dict, split_output=False):
    dirname = f"{task['name']}-{task['id']}"
    dirpath = CACHE_DIR / dirname
    os.makedirs(dirpath, exist_ok=True)
    filepath = dirpath / "task.json"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if split_output:
        stdoutpath = dirpath / f"{dirname}-{timestamp}.out"
        stderrpath = dirpath / f"{dirname}-{timestamp}.err"
    else:
        logspath = dirpath / f"{dirname}-{timestamp}.log"
    shellpath = str(dirpath / task["id"])
    try:
        os.symlink("/bin/sh", shellpath)
    except FileExistsError:
        pass
    if split_output:
        task.update({
            "shell": str(shellpath),
            "stdout": str(stdoutpath),
            "stderr": str(stderrpath),
        })
    else:
        task.update({
            "shell": str(shellpath),
            "logs": str(logspath),
        })
    with open(filepath, "w") as f:
        json.dump(task, f)
    return task


def update_task_cache(task: Dict):
    dirname = f"{task['name']}-{task['id']}"
    dirpath = CACHE_DIR / dirname
    filepath = dirpath / "task.json"
    with open(filepath, "w") as f:
        json.dump(task, f)


def signal_handler(process):
    def wrapper(signum, frame):
        process.send_signal(signum)
        if signum == signal.SIGINT:
            print("Interrupted", file=sys.stderr)
            sys.exit(1)
        if signum == signal.SIGTERM:
            print("Terminated", file=sys.stderr)
            sys.exit(1)
    return wrapper


def generate_id():
    return "i1821jn2m"


def generate_name():
    return "test_name"

def is_task_running(task):
    output = subprocess.check_output(['ps', '-u' , str(os.getuid()), '-o', 'pid,args'])
    for line in output.splitlines():
        decoded = line.decode().strip()
        ps_pid, cmdline = decoded.split(' ', 1)
        if ps_pid == task["pid"]:
            if cmdline.startswith(task["shell"]):
                return True
    return False

def remove_task_by_name(name: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            if filename.split("-")[0] == name:
                task = find_task_by_name(name, lock=False)
                if is_task_running(task):
                    raise StartstopException(
                        "Cannot remove task while it's running.\n"
                        "To stop it, run:\n"
                        f"startstop stop {name}"
                    )
                dirpath = abspath(join(CACHE_DIR, filename))
                shutil.rmtree(dirpath)
                return True
        return False

def remove_task_by_id(task_id: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            try:
                if filename.split("-")[1] == task_id:
                    task = find_task_by_id(task_id, lock=False)
                    if is_task_running(task):
                        raise StartstopException(
                            "Cannot remove task while it's running.\n"
                            "To stop it, run:\n"
                            f"startstop stop {task_id}"
                        )
                    dirpath = abspath(join(CACHE_DIR, filename))
                    shutil.rmtree(dirpath)
                    return True
            except IndexError as e:
                pass
        return False

async def run(command: List[str], name=None, attached=False, split_output=False):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task:
                if is_task_running(task):
                    raise StartstopException(f"A task with this name already exists with PID {task.get('pid')}")
                raise StartstopException(
                    "A task with this name already exists but it's not running.\n"
                    "To remove it, run:\n"
                    f"startstop rm {name}"
                )
        else:
            name = generate_name()
        task = {
            "id": generate_id(),
            "name": name,
            "command": command,
        }
        if split_output:
            task = create_task_cache(task, split_output=split_output)
            shellpath = task["shell"]
            stdoutpath = task["stdout"]
            stderrpath = task["stderr"]
        else:
            task = create_task_cache(task, split_output=split_output)
            shellpath = task["shell"]
            logspath = task["logs"]
        command = [shellpath, "-c"] + command
        if not attached:
            if split_output:
                with open(stdoutpath, "wb") as stdout:
                    with open(stderrpath, "wb") as stderr:
                        proc = subprocess.Popen(
                            command,
                            start_new_session=True,
                            stdout=stdout,
                            stderr=stderr,
                        )
            else:
                with open(logspath, "wb") as output:
                    proc = subprocess.Popen(
                        command,
                        start_new_session=True,
                        stdout=output,
                        stderr=output,
                    )
            task["pid"] = str(proc.pid)
            update_task_cache(task)
            return task
    if attached:
        await asyncio.create_subprocess_shell(*command)


async def run_attached(command: List[str], name=None):
    proc = await run(command, name=name, attached=True)
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, signal_handler(proc))
    await proc.wait()


def start_task(task_id=None, name=None):
    with AtomicOpen(LOCK_PATH):
        if name is not None:
            task = find_task_by_name(name)
            if task is not None:
                if is_task_running(task):
                    raise StartstopException(f"A task with this name already exists with PID {task.get('pid')}")
            else:
                raise StartstopException(f"No task with name {name}")
        else:
            task = find_task_by_id(task_id)
            if task is None:
                raise StartstopException(f"No task with ID {task_id}")

        dirname = f"{task['name']}-{task['id']}"
        dirpath = CACHE_DIR / dirname
        command = [task["shell"], "-c"] + task["command"]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        if task.get("stdout") is not None:
            task["stdout"] = str(dirpath / f"{dirname}-{timestamp}.out")
            task["stderr"] = str(dirpath / f"{dirname}-{timestamp}.err")
            with open(task["stdout"], "wb") as stdout:
                with open(task["stderr"], "wb") as stderr:
                    proc = subprocess.Popen(
                        command,
                        start_new_session=True,
                        stdout=stdout,
                        stderr=stderr,
                    )
        else:
            task["logs"] = str(dirpath / f"{dirname}-{timestamp}.log")
            with open(task["logs"], "wb") as output:
                proc = subprocess.Popen(
                    command,
                    start_new_session=True,
                    stdout=output,
                    stderr=output,
                )
        task["pid"] = str(proc.pid)
        update_task_cache(task)
        return task

def print_error(msg: str, *args, **kwargs):
    print(f"{bcolors.FAIL}{msg}{bcolors.ENDC}", *args, **kwargs)

def print_warning(msg: str, *args, **kwargs):
    print(f"{bcolors.WARNING}{msg}{bcolors.ENDC}", *args, **kwargs)

def print_success(msg: str, *args, **kwargs):
    print(f"{bcolors.OKGREEN}{msg}{bcolors.ENDC}", *args, **kwargs)

def rm(task_name_or_id: str):
    try:
        task_id = str(int(task_name_or_id))
        name = None
    except (ValueError, TypeError):
        task_id = None
        name = task_name_or_id

    try:
        if task_id is not None:
            result = remove_task_by_id(task_id)
            if result is True:
                print_success(task_id)
            else:
                print_error(f"No task with ID {task_id}", file=sys.stderr)
        else:
            result = remove_task_by_name(name)
            if result is True:
                print_success(name)
            else:
                print_error(f"No task with name {name}", file=sys.stderr)
    except StartstopException as e:
        print_error(str(e))
        return False
    return result

def start(task_name_or_id: str):
    try:
        task_id = str(int(task_name_or_id))
        name = None
    except (ValueError, TypeError):
        task_id = None
        name = task_name_or_id

    try:
        task = start_task(task_id=task_id, name=name)
        print_success(task["id"])
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
        TODO
        print_success(task["id"])
        return True
    except StartstopException as e:
        print_error(str(e))
        return False

def main():
    try:
        if len(sys.argv) == 1:
            sys.exit(1)
        global_args, option, option_args, command = parse_args(sys.argv)
        #print(global_args, option, option_args, command)
        if option == "run":
            name = option_args.get("n") or option_args.get("name") or None
            attached = option_args.get("a") or option_args.get("attached")
            if attached:
                asyncio.run(run_attached(command, name=name))
            else:
                task = asyncio.run(run(command, name=name))
                print_success(task["id"])
        elif option == "rm":
            errors = False
            pool = ThreadPool(len(command))
            results = pool.map(rm, command)
            if not all(results):
                sys.exit(1)

        elif option == "start":
            results = pool.map(start, command)
            if not all(results):
                sys.exit(1)

        elif option == "stop":
            results = pool.map(stop, command)
            if not all(results):
                sys.exit(1)

    except StartstopException as e:
        print_error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
