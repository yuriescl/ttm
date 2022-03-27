from typing import List
import sys

def validate_argument(arg: str, option=None):
    if option is None:
        if arg not in [
            "v",
            "verbose",
        ]:
            raise ValueError(f"Unrecognized argument --{arg}")
    elif option == "start":
        pass
    elif option == "stop":
        pass

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
            if pos + 1 == len(args) or args[pos + 1].startswith("-"):
                raise ValueError(f"Argument {current_arg} requires a value")
            current_arg = current_arg[2:]
            validate_argument(current_arg)
            global_args[current_arg] = args[pos + 1]
        elif current_arg.startswith("-"):
            current_arg = current_arg[1:]
            if len(current_arg) == 1:
                validate_argument(current_arg)
                global_args[current_arg] = True
            else:
                for letter in current_arg:
                    validate_argument(letter)
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

if __name__ == "__main__":
    main()
