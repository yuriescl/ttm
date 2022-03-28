from typing import List
import sys
import os
from os.path import join, abspath
import asyncio
from pathlib import Path
import signal

if linux:
    if os.geteuid() == 0: # if root
        PID_DIR = Path("/var", "run", "startstop")
    else:
        PID_DIR = Path('/var/run/user/{os.geteuid()}/startstop"
    os.makedirs(PID_DIR, exist_ok=True)



def arg_requires_value(arg: str, option=None):
    if option is None:
        if arg in ["v", "verbose"]:
            return False
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
    pos + 1 < len(args) and not args[pos + 1].startswith("-")

def parse_args(argv: List[str]):
    args = argv[1:]
    global_args = {}
    option = None
    for pos, arg in enumerate(args):
        current_arg = arg
        if current_arg in ["start", "stop"]:
            option = current_arg
            pos += 1
            break
        elif current_arg.startswith("--"):
            current_arg = current_arg[2:]
            if arg_requires_value(current_arg, option) and not is_value_next(args, pos):
                raise ValueError(f"Argument --{current_arg} requires a value")
            global_args[current_arg] = args[pos + 1]
        elif current_arg.startswith("-"):
            current_arg = current_arg[1:]
            if len(current_arg) == 1:
                if arg_requires_value(current_arg, option) and not is_value_next(args, pos):
                    raise ValueError(f"Argument -{current_arg} requires a value")
                global_args[current_arg] = True
            else:
                for letter in current_arg:
                    if arg_requires_value(letter, option):
                        raise ValueError(f"Argument -{letter} cannot be grouped with other arguments")
                    global_args[letter] = True

    option_args = {}
    command = None

    if option is not None:
        args = args[pos:]
        if len(args) == 0:
            raise ValueError(f"Missing arguments for option '{option}'")
        for pos, arg in enumerate(args):
            current_arg = arg
            if current_arg.startswith("--"):
                if pos + 1 == len(args) or args[pos + 1].startswith("-"):
                    raise ValueError(f"Argument {current_arg} requires a value")
                current_arg = current_arg[2:]
                validate_argument(current_arg, option=option)
                option_args[current_arg] = args[pos + 1]
            elif current_arg.startswith("-"):
                current_arg = current_arg[1:]
                if len(current_arg) == 1:
                    validate_argument(current_arg, option=option)
                    option_args[current_arg] = True
                else:
                    for letter in current_arg:
                        validate_argument(letter, option=option)
                        option_args[letter] = True
            else:
                command = args[pos:]
                break

    return global_args, option, option_args, command

def main():
    if len(sys.argv) == 1:
        sys.exit(1)
    try:
        global_args, option, option_args, command = parse_args(sys.argv)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    print(global_args, option, option_args, command)

#if __name__ == "__main__":
#    main()

def get_process_by_id(identifier: str):
    for filename in os.listdir(PID_DIR):
        if filename.split("-")[0] == identifier:
            path = abspath(join(PID_DIR, filename))
            with open(path) as f:
                return json.load(f)
    return None

def get_process_by_name(name: str):
    for filename in os.listdir(PID_DIR):
        try:
            if filename.split("-")[1] == name:
                path = abspath(join(PID_DIR, filename))
                with open(path) as f:
                    return json.load(f)
        except IndexError as e:
            pass
    return None

def signal_handler(process):
    def wrapper(signum, frame):
        process.send_signal(signum)
        signal.raise_signal(signum)
    return wrapper

async def run_attached(command: List[str]):
    for sig in [
        signal.SIGINT,
        signal.SIGABRT,
        signal.SIGFPE,
        signal.SIGILL,
        signal.SIGINT,
        signal.SIGSEGV,
        signal.SIGTERM,
        signal.SIGBREAK,
    ]:
        signal.signal(sig, signal_handler(proc))
    sys.modules[__name__].proc = await asyncio.create_subprocess_exec(command)
    await proc.wait()
