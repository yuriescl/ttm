Tiny task manager for Linux, MacOS and Unix-like systems.  
Written as a single Python script.

## Installation

Download the script directly (recommended):
```
curl https://raw.githubusercontent.com/yuriescl/ttm/dev/ttm.py -o ttm
chmod +x ttm
./ttm
```

### Alternative installation methods

#### Installing through pip
```
pip install ttm
ttm  # or python -m ttm
```

Requirements:
- `python` >=3.8
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
$ ttm run ./backup-database.sh --output /backups/database.sql
$ ttm ls
ID   NAME COMMAND                                              UPTIME PID    
1    -    ./backup-database.sh --output /backups/database.sql  2s     742537 
$ ttm stop 1
$ ttm rm 1
```

Running Django server:
```
$ ttm run --name mydjangoserver python manage.py runserver
$ ttm rm mydjangoserver
Cannot remove task while it's running.
To stop it, run:
ttm stop mydjangoserver
$ ttm logs mydjangoserver
$ ttm rm mydjangoserver
```

## Development

### Environment
```
poetry env use python3.8
poetry install
poetry shell
```
