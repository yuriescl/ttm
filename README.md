Tiny process manager for Linux, MacOS and Unix-like systems.  
Written as a single Python script (download [here](https://github.com/yuriescl/startstop/releases/download/0.1.0/startstop)).

Requirements:
- `python` (3.8+)
- `ps` (usually available by default)

Features:
- No root access required
- Start, watch, and stop tasks
- Single script built using the Python standard library - easy to audit and run
- Daemon-less

Alternative to:
- [supervisord](http://supervisord.org/)
- [pm2](https://pm2.keymetrics.io/)
- [docker](https://www.docker.com/)

**Examples**

Running a script:
```
$ startstop run ./backup-database.sh --output /backups/database.sql
$ startstop ls
ID   NAME COMMAND                                              UPTIME PID    
1    -    ./backup-database.sh --output /backups/database.sql  2s     742537 
$ startstop stop 1
$ startstop rm 1
```

Running Django server :
```
$ startstop run --name mydjangoserver python manage.py runserver
$ startstop rm mydjangoserver
Cannot remove task while it's running.
To stop it, run:
startstop stop mydjangoserver
$ startstop logs mydjangoserver
$ startstop rm mydjangoserver
```

## Installation

Download the script directly (recommended):
```
curl https://github.com/yuriescl/startstop/releases/download/0.1.0/startstop -o startstop
chmod +x startstop
./startstop
```

### Alternative installation methods

#### Installing through pip
```
pip install startstop
startstop  # or python -m startstop
```

## Development

### Environment
```
poetry env use python3.7
poetry install
poetry shell
```

Todo:
- add -q global flag
- add some sort of execution log history to easily see logs
- add --help
- print --help when command is in invalid format
- allow specifying cache dir
- allow start/stop/rm non-parallel
- test in pure Unix
- what is user has no home dir?
- add busy interval parameter used in busy loops
- add timeout to stop(), and also maybe a -9 param to send kill -9
- add JSON CLI input/output support
- add --long to ls
- add support for non-shell commands
- add logs command
