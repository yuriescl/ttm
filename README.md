Tiny task manager for Linux, MacOS and Unix-like systems.  
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

Running Django server:
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
curl https://raw.githubusercontent.com/yuriescl/startstop/0.1.3/startstop.py -o startstop
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
poetry env use python3.9
poetry install
poetry shell
```
