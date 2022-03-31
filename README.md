Tiny process manager for Linux, MacOS and Unix-like systems.  
Written as a single Python script (download [here](https://raw.githubusercontent.com/yuriescl/startstop/dev/startstop)).

Features:
- No root access required
- Start, watch, and stop tasks
- Single script built using the Python standard library - easy to audit and run
- Daemon-less

Alternative to:
- [supervisord](http://supervisord.org/)
- [pm2](https://pm2.keymetrics.io/)
- [docker](https://www.docker.com/)

Examples:
```bash
# Running a script
$ startstop run ./backup-database.sh --output /backups/database.sql
$ startstop ls
ID   NAME COMMAND                                              UPTIME PID    
1    -    ./backup-database.sh --output /backups/database.sql  2s     742537 
$ startstop stop 1
$ startstop rm 1

# Running Django server 
$ startstop run --name mydjangoserver python manage.py runserver
$ startstop rm mydjangoserver
Cannot remove task while it's running.
To stop it, run:
$ startstop stop mydjangoserver
$ startstop logs mydjangoserver
$ startstop rm mydjangoserver
```

## Installation

Download the script directly (recommended):
```bash
curl https://raw.githubusercontent.com/yuriescl/startstop/dev/startstop -o startstop
chmod +x startstop
./startstop
```

### Alternative installation methods

#### Installing through pip
```bash
pip install startstop
startstop  # or python -m startstop
```

## Development

### Environment
```bash
poetry env use python3.7
poetry install
poetry shell
```

### Building the standalone binary

This build worked on Debian 11:
```bash
sudo apt install python3-dev
cython -3 --embed -o startstop.c startstop.py
gcc -Os -I /usr/include/python3.9 -o startstop startstop.c -lpython3.9 -lpthread -lm -lutil -ldl
strip -s -R .comment -R .gnu.version --strip-unneeded startstop
```
Replace `python3.9` with the target python version.


Todo:
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
- add rm -a
