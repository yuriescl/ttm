**This project is a Work In Progress. First version will be available soon.**

Tiny process manager for Linux/Unix systems. Written in Python.

How to setup development environment:
```
poetry env use python3.7
poetry install
poetry shell
```

Todo:
    - update project description
    - allow matching partial id
    - add "rm" option, remove cache folder
    - make C version
    - start/stop/rm accept multiple names/id
    - start -a only works when starting a single process
    - add -q global flag
    - add some sort of execution log history to easily see logs
