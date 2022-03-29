from typing import List, Dict
import sys
from datetime import datetime
import json
import tempfile
import os
from os.path import join, abspath
import asyncio
from pathlib import Path
import subprocess
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


def find_process_by_name(name: str, lock=True) -> Dict:
    with AtomicOpen(LOCK_PATH, noop=not lock):
        for filename in os.listdir(CACHE_DIR):
            if filename.split("-")[0] == name:
                path = abspath(join(CACHE_DIR, filename, "process.json"))
                with open(path) as f:
                    return json.load(f)
        return None


def find_process_by_id(identifier: str, lock=True) -> Dict:
    with AtomicOpen(LOCK_PATH, noop=not lock):
        for filename in os.listdir(CACHE_DIR):
            try:
                if filename.split("-")[1] == identifier:
                    path = abspath(join(CACHE_DIR, filename, "process.json"))
                    with open(path) as f:
                        return json.load(f)
            except IndexError as e:
                pass
        return None


def create_process_cache(proc_info: Dict, split_output=False):
    dirname = f"{proc_info['name']}-{proc_info['id']}"
    dirpath = CACHE_DIR / dirname
    os.makedirs(dirpath, exist_ok=True)
    filepath = dirpath / "process.json"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    if split_output:
        stdoutpath = dirpath / f"{dirname}-{timestamp}.out"
        stderrpath = dirpath / f"{dirname}-{timestamp}.err"
    else:
        logspath = dirpath / f"{dirname}-{timestamp}.log"
    shellpath = str(dirpath / proc_info["id"])
    try:
        os.symlink("/bin/sh", shellpath)
    except FileExistsError:
        pass
    if split_output:
        proc_info.update({
            "shell": str(shellpath),
            "stdout": str(stdoutpath),
            "stderr": str(stderrpath),
        })
    else:
        proc_info.update({
            "shell": str(shellpath),
            "logs": str(logspath),
        })
    with open(filepath, "w") as f:
        json.dump(proc_info, f)
    return proc_info


def update_process_cache(proc_info: Dict):
    dirname = f"{proc_info['name']}-{proc_info['id']}"
    dirpath = CACHE_DIR / dirname
    filepath = dirpath / "process.json"
    with open(filepath, "w") as f:
        json.dump(proc_info, f)


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

def is_process_running(proc_info):
    output = subprocess.check_output(['ps', '-u' , str(os.getuid()), '-o', 'pid,args'])
    for line in output.splitlines():
        decoded = line.decode().strip()
        ps_pid, cmdline = decoded.split(' ', 1)
        if ps_pid == proc_info["pid"]:
            if cmdline.startswith(proc_info["shell"]):
                return True
    return False

def remove_process_by_name(name: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            if filename.split("-")[0] == name:
                proc_info = find_process_by_name(name, lock=False)
                if is_process_running(proc_info):
                    raise StartstopException(
                        "Cannot remove process while it's running.\n"
                        "To stop it, run:\n"
                        f"startstop stop {name}"
                    )
                dirpath = abspath(join(CACHE_DIR, filename))
                shutil.rmtree(dirpath)
                return True
        return False

def remove_process_by_id(identifier: str):
    with AtomicOpen(LOCK_PATH):
        for filename in os.listdir(CACHE_DIR):
            try:
                if filename.split("-")[1] == identifier:
                    proc_info = find_process_by_id(identifier, lock=False)
                    if is_process_running(proc_info):
                        raise StartstopException(
                            "Cannot remove process while it's running.\n"
                            "To stop it, run:\n"
                            f"startstop stop {identifier}"
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
            proc_info = find_process_by_name(name)
            if proc_info:
                if is_process_running(proc_info):
                    raise StartstopException(f"A process with this name already exists with PID {proc_info.get('pid')}")
                raise StartstopException(
                    "A process with this name already exists but it's not running.\n"
                    "To remove it, run:\n"
                    f"startstop rm {name}"
                )
        else:
            name = generate_name()
        proc_id = generate_id()
        info = {
            "id": proc_id,
            "name": name,
            "command": command,
        }
        if split_output:
            proc_info = create_process_cache(info, split_output=split_output)
            shellpath = proc_info["shell"]
            stdoutpath = proc_info["stdout"]
            stderrpath = proc_info["stderr"]
        else:
            proc_info = create_process_cache(info, split_output=split_output)
            shellpath = proc_info["shell"]
            logspath = proc_info["logs"]
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
            info["pid"] = str(proc.pid)
            update_process_cache(info)
            return proc_info
    if attached:
        await asyncio.create_subprocess_shell(*command)


async def run_attached(command: List[str], name=None):
    proc = await run(command, name=name, attached=True)
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, signal_handler(proc))
    await proc.wait()


def print_error(msg: str, *args, **kwargs):
    print(f"{bcolors.FAIL}{msg}{bcolors.ENDC}", *args, **kwargs)

def print_warning(msg: str, *args, **kwargs):
    print(f"{bcolors.WARNING}{msg}{bcolors.ENDC}", *args, **kwargs)

def print_success(msg: str, *args, **kwargs):
    print(f"{bcolors.OKGREEN}{msg}{bcolors.ENDC}", *args, **kwargs)

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
                proc_info = asyncio.run(run(command, name=name))
                print_success(proc_info["id"])
        elif option == "rm":
            errors = False
            for c in command:
                try:
                    identifier = str(int(c))
                    name = None
                except (ValueError, TypeError):
                    identifier = None
                    name = c

                if identifier is not None:
                    result = remove_process_by_id(identifier)
                    if result is True:
                        print_success(identifier)
                    else:
                        print_error(f"No process with ID {identifier}", file=sys.stderr)
                        errors = True
                else:
                    result = remove_process_by_name(name)
                    if result is True:
                        print_success(name)
                    else:
                        print_error(f"No process with name {name}", file=sys.stderr)
                        errors = True
            if errors is True:
                sys.exit(1)

    except StartstopException as e:
        print_error(str(e))
        sys.exit(1)
        #print(is_process_running(proc_info["pid"], proc_info["shell"]))


if __name__ == "__main__":
    main()
