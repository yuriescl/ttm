Tiny task manager for Linux, MacOS and Unix-like systems.  
Written as a single Python script.

<img src="https://user-images.githubusercontent.com/26092447/224555851-275c66a2-1679-401a-8ca7-a4057406fc77.gif" width="350">

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
- Daemon-less
- Easily start, watch, and stop tasks using very simple and direct CLI commands
- Written as a single script built using only the Python standard library - easy to audit and run

Comparison to other popular server task managers:
- [systemctl](https://www.freedesktop.org/software/systemd/man/systemctl.html)
  - Pros
    - Sophisticated dependency management via `WantedBy`
    - Works well with system services
    - Usually installed by default in any modern server
    - Many advanced options, useful for fine-grained control of system services
  - Cons
    - Unit files are required every time you need to setup a simple background task
    - Difficult to work with when you're not the root user (`systemctl --user` is not so simple to use)
    - If not installed in the system, can be difficult to install and setup as a non-privileged user
    - Difficult for beginners and non-sysadmins
- [supervisord](http://supervisord.org/)
  - Pros
    - Very advanced and fine-grained control of tasks, similar to systemctl
  - Cons
    - Not usually installed by default in modern servers
    - Even if installed, usually requires root access
    - Difficult for beginners and non-sysadmins
- [pm2](https://pm2.keymetrics.io/)
  - Pros
    - Modern codebase (JavaScript)
    - Can be easily installed via `npm install pm2`
    - Has advanced integration with Node.js programs (cluster mode, load balancing, etc)
    - Widely known and used in Node.js ecosystem
  - Cons
    - Not usually installed by default in modern servers
    - Might not work so well with non-Node.js software
    - Requires `node` and `npm` to be installed
    - Might consume more RAM than intended since it's JavaScript
    - Can be a bit difficult to setup and run simple tasks
- [docker](https://www.docker.com/)
  - Pros
    - Quickly spin up a development/production instance given a properly configured Dockerfile
    - Container/Dockerfile can be easily shared accross a development team so everyone can test in same OS environment
    - Widely available and used across many different platforms
    - All dependencies can be installed in the container
  - Cons
    - Requires root access
    - Usually the processes run as the root user, which can lead to major security vulnerabilities
    - Very hard for beginners and non-sysadmins
    - Difficult to run simple tasks that don't need containers

`ttm` was initially an attempt (after painfully having to deal with the existing options like PM2, systemctl, etc) to have a script I could easily copy to a server and manage simple tasks like a `gunicorn` server, or a `celery` worker. After a while, `ttm` became a very useful tool in day-to-day deployments, so it made sense to make it public.

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
