**This project is a Work In Progress. First version will be available soon.**

Tiny process manager for Linux/Unix.  
Written in Python, compiled to a ~300K standalone executable binary (download
[here](https://raw.githubusercontent.com/yuriescl/startstop/dev/startstop)).

Features:
- No root access required
- Start, watch, and stop processes easily

In action:
```
startstop run "python manage.py runserver"
```


# Development

## Environment
```
poetry env use python3.7
poetry install
poetry shell
```

## Building the standalone binary

```
sudo apt install python3-dev
cython -3 --embed -o startstop.c startstop.py
gcc -Os -I /usr/include/python3.9 -o startstop startstop.c -lpython3.9 -lpthread -lm -lutil -ldl
```
Replace `python3.9` with the target python version.

Todo:
    - update project description
    - start/stop/rm accept multiple names/id
    - start -a only works when starting a single process
    - add -q global flag
    - add some sort of execution log history to easily see logs
    - add requirements (python3, ps, etc)
    - add --help
    - print --help when command is in invalid format
    - allow specifying cache dir
    - allow start/stop/rm non-parallel
    - test in pure Unix
    - what is user has no home dir?
    - add doc explaining how processes are tracked
    - add busy interval parameter used in busy loops
    - add timeout to stop(), and also maybe a -9 param to send kill -9
    - add JSON CLI input/output support
    - decide column widths for ls template
    - add --long to ls
    - add support for non-shell commands
    - add logs command
