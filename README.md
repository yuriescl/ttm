**This project is a Work In Progress. First version will be available soon.**

Tiny process manager for Linux/Unix.  
Written in Python, compiled to a ~300K standalone executable binary.

Features
- No root access required
- Start, watch, and stop processes easily

How to setup development environment:
```
poetry env use python3.7
poetry install
poetry shell
```

```
cython -3 --embed -o startstop.c startstop.py
gcc -Os -I /usr/include/python3.9 -o startstop startstop.c -lpython3.9 -lpthread -lm -lutil -ldl
```

Todo:
    - update project description
    - allow matching partial id
    - start/stop/rm accept multiple names/id
    - start -a only works when starting a single process
    - add -q global flag
    - add some sort of execution log history to easily see logs
    - add requirements (python3, ps, etc)
    - add --help
    - print --help when command is in invalid format
    - allow specifying cache dir
