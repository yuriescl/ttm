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
import signal

if True:  # TODO if linux
    CACHE_DIR = Path.home() / ".startstop"
    os.makedirs(CACHE_DIR, exist_ok=True)


def arg_requires_value(arg: str, option=None):
    if option is None:
        if arg in ["v", "verbose"]:
            return False
        raise ValueError(f"Unrecognized argument --{arg}")
    elif option == "run":
        if arg in ["a", "attach"]:
            return False
        if arg in ["n", "name"]:
            return True
        raise ValueError(f"Unrecognized argument --{arg}")
    elif option == "start":
        if arg in ["a", "attach"]:
            return False
        raise ValueError(f"Unrecognized argument --{arg}")
    elif option == "stop":
        if arg in ["k"]:
            return False
        raise ValueError(f"Unrecognized argument --{arg}")


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
        if current_arg in ["run", "start", "stop"]:
            option = current_arg
            pos += 1
            break
        elif current_arg.startswith("--"):
            current_arg = current_arg[2:]
            if arg_requires_value(current_arg, option):
                if not is_value_next(args, pos):
                    raise ValueError(f"Argument --{current_arg} requires a value")
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
                        raise ValueError(f"Argument -{current_arg} requires a value")
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
                        raise ValueError(
                            f"Argument -{letter} cannot be grouped with other arguments"
                        )
                    global_args[letter] = True
                    pos += 1
                    continue
        else:
            raise ValueError(f"Unrecognized option {current_arg}")
        pos += 1

    option_args = {}
    command = None

    if option is not None:
        if pos >= len(args):
            raise ValueError(f"Missing arguments for option '{option}'")
        while True:
            if pos >= len(args):
                break
            current_arg = args[pos]
            if current_arg.startswith("--"):
                current_arg = current_arg[2:]
                if arg_requires_value(current_arg, option):
                    if not is_value_next(args, pos):
                        raise ValueError(f"Argument --{current_arg} requires a value")
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
                            raise ValueError(
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
                            raise ValueError(
                                f"Argument -{letter} cannot be grouped with other arguments"
                            )
                        option_args[letter] = True
                        pos += 1
                        continue
            else:
                command = args[pos:]
                break

    return global_args, option, option_args, command


def get_process_by_name(name: str) -> Dict:
    for filename in os.listdir(CACHE_DIR):
        if filename.split("-")[0] == name:
            path = abspath(join(CACHE_DIR, filename, "process.json"))
            with open(path) as f:
                return json.load(f)
    return None


def get_process_by_id(identifier: str) -> Dict:
    for filename in os.listdir(CACHE_DIR):
        try:
            if filename.split("-")[1] == identifier:
                path = abspath(join(CACHE_DIR, filename, "process.json"))
                with open(path) as f:
                    return json.load(f)
        except IndexError as e:
            pass
    return None


def create_process_cache(proc_info: Dict):
    dirname = f"{proc_info['name']}-{proc_info['id']}"
    dirpath = CACHE_DIR / dirname
    os.makedirs(dirpath, exist_ok=True)
    filepath = dirpath / "process.json"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    stdoutpath = dirpath / f"{dirname}-{timestamp}.out"
    stderrpath = dirpath / f"{dirname}-{timestamp}.err"
    shellpath = str(dirpath / proc_info["id"])
    try:
        os.symlink("/bin/sh", shellpath)
    except FileExistsError:
        pass
    with open(filepath, "w") as f:
        json.dump(proc_info, f)
    return shellpath, stdoutpath, stderrpath


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


async def run(command: List[str], name=None, attached=False):
    proc_id = generate_id()
    if name is None:
        name = generate_name()
    info = {
        "id": proc_id,
        "name": name,
        "command": command,
    }
    shellpath, stdoutpath, stderrpath = create_process_cache(info)
    command = [shellpath, "-c"] + command
    if attached:
        proc = await asyncio.create_subprocess_shell(*command)
    else:
        with open(stdoutpath, "wb") as stdout:
            with open(stderrpath, "wb") as stderr:
                proc = subprocess.Popen(
                    command,
                    start_new_session=True,
                    stdout=stdout,
                    stderr=stderr,
                )
    info["pid"] = str(proc.pid)
    info["shellpath"] = shellpath
    update_process_cache(info)
    return proc

def is_process_running(pid: str, shellpath: str):
    output = subprocess.check_output(['ps', '-u' , str(os.getuid()), '-o', 'pid,args'])
    for line in output.splitlines():
        decoded = line.decode().strip()
        ps_pid, cmdline = decoded.split(' ', 1)
        if ps_pid == pid:
            if cmdline.startswith(shellpath):
                return True
    return False

async def run_attached(command: List[str], name=None):
    proc = await run(command, name=name, attached=True)
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, signal_handler(proc))
    await proc.wait()


def main():
    if len(sys.argv) == 1:
        sys.exit(1)
    try:
        global_args, option, option_args, command = parse_args(sys.argv)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(global_args, option, option_args, command)


    if option == "run":
        name = option_args.get("n") or option_args.get("name") or None
        attached = option_args.get("a") or option_args.get("attached")
        if attached:
            asyncio.run(run_attached(command, name=name))
        else:
            asyncio.run(run(command, name=name))
        proc_info = get_process_by_name("test1")
        print(is_process_running(proc_info["pid"], proc_info["shellpath"]))


if __name__ == "__main__":
    main()
