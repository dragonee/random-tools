"""
Run things inside the docker container described by .container.ini.

Usage:
    h [COMMAND] [ARGUMENTS ...]
    h init [FILE]
    h -h | --help
    h --version

Examples:
    h sh                   a shell in the container
    h mix test             a configured command, with arguments
    h logs                 follow its output
    h cp local.txt         copy a file in
    h init                 write a starter .container.ini here

`h` on its own lists the commands the config file defines, alongside the
built-in ones: id, logs, cp, start, stop, restart and init.

The config file is looked up in the current directory, then its parents;
$CONTAINER_INI overrides all of that.

    [General]
    name = ^myapp-app-1$      ; docker's name filter, which it reads as a regex
    workdir = /app            ; default cwd for exec, default target for cp

    [sh]
    program = bash            ; h sh -> docker exec -it <id> bash
    help = a shell in the container

Every section other than [General] names a command. `program` is the only
required key; `help`, `tty`, `user`, `workdir` and `env` are optional, and
`user`, `workdir` and `env` may also be set in [General] as defaults.

`tty` is auto by default: the -t flag is passed only when this script is
itself attached to a terminal, so `h mix test` is interactive at a prompt
and pipes cleanly from cron or CI without needing a second no-tty command.

Options:
    -h, --help     Show this message.
    --version      Show version information.
"""

VERSION = '1.0'

import configparser
import os
import shlex
import shutil
import subprocess
import sys

try:
    from importlib.resources import files as resource_files
except ImportError:  # Python 3.8 and older
    resource_files = None

CONFIG_NAME = ".container.ini"
PROG = os.path.basename(sys.argv[0])

BUILTINS = (
    ("id", "print the container id"),
    ("logs", "follow the container's output (extra args go to docker logs)"),
    ("cp", "copy a file in: cp SRC [DEST]; or out: cp :/path/in/container [DEST]"),
    ("start", "start the container"),
    ("stop", "stop the container"),
    ("restart", "restart the container"),
    ("init", "write a starter %s here: init [FILE]" % CONFIG_NAME),
)


def die(message, code=1):
    sys.stderr.write("%s: %s\n" % (PROG, message))
    raise SystemExit(code)


def config_path():
    override = os.environ.get("CONTAINER_INI")
    if override:
        if not os.path.isfile(override):
            die("$CONTAINER_INI is %s, which does not exist" % override)
        return override

    here = os.getcwd()
    while True:
        candidate = os.path.join(here, CONFIG_NAME)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    die("no %s here or in any parent directory.\n"
        "%s  `%s init` writes one to start from."
        % (CONFIG_NAME, " " * (len(PROG) + 2), PROG))


def load_config():
    path = config_path()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(path) as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error) as error:
        die("%s: %s" % (path, error))
    if not parser.has_section("General"):
        die("%s has no [General] section" % path)
    if not parser.get("General", "name", fallback="").strip():
        die("%s has no name = ... in [General]" % path)
    return path, parser


def example_path():
    """The packaged .container.ini to copy from, wherever pip put it."""
    if resource_files is not None:
        packaged = resource_files("randomtools") / "examples" / "container.ini"
        if packaged.is_file():
            return packaged
    beside = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "examples", "container.ini"
    )
    if os.path.isfile(beside):
        return beside
    die("the packaged example is missing from this installation")


def setting(parser, section, key, default=None):
    """A key from the command's section, falling back to [General]."""
    value = parser.get(section, key, fallback="").strip()
    if not value:
        value = parser.get("General", key, fallback="").strip()
    return value or default


def docker(args, check=True):
    try:
        result = subprocess.run(
            ["docker"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError:
        die("docker is not on your PATH")
    if check and result.returncode != 0:
        die(result.stderr.strip() or "docker %s failed" % " ".join(args))
    return result.stdout


def matching_containers(name, include_stopped):
    args = ["ps", "--filter", "name=" + name, "--format", "{{.ID}}\t{{.Names}}"]
    if include_stopped:
        args.insert(1, "-a")
    rows = []
    for line in docker(args).splitlines():
        if line.strip():
            container_id, _, container_name = line.partition("\t")
            rows.append((container_id, container_name))
    return rows


def container_id(name, include_stopped=False):
    rows = matching_containers(name, include_stopped)
    if len(rows) > 1:
        names = ", ".join(row[1] for row in rows)
        die(
            "name = %s matches %d containers (%s).\n"
            "%s  docker reads the filter as a regex, so anchor it: name = ^%s$"
            % (name, len(rows), names, " " * (len(PROG) + 2), rows[0][1])
        )
    if rows:
        return rows[0][0]
    if not include_stopped:
        stopped = matching_containers(name, True)
        if stopped:
            die("container %s is not running — `%s start` it first" % (stopped[0][1], PROG))
    die("no container matches name = %s" % name)


def wants_tty(parser, section):
    value = setting(parser, section, "tty", "auto").lower()
    if value == "auto":
        return sys.stdin.isatty() and sys.stdout.isatty()
    if value in ("yes", "true", "on", "1"):
        return True
    if value in ("no", "false", "off", "0"):
        return False
    die("[%s] tty = %s: expected auto, yes or no" % (section, value))


def exec_command(parser, section, cid, argv):
    program = parser.get(section, "program", fallback="").strip()
    if not program:
        die("[%s] has no program = ..." % section)

    command = ["docker", "exec", "-i"]
    if wants_tty(parser, section):
        command.append("-t")
    user = setting(parser, section, "user")
    if user:
        command += ["--user", user]
    workdir = setting(parser, section, "workdir")
    if workdir:
        command += ["--workdir", workdir]
    for variable in shlex.split(setting(parser, section, "env", "")):
        command += ["--env", variable]
    return command + [cid] + shlex.split(program) + argv


def copy_command(parser, cid, argv):
    if not argv or len(argv) > 2:
        die("usage: %s cp SRC [DEST]   (a leading ':' marks a path in the container)" % PROG)
    source = argv[0]
    destination = argv[1] if len(argv) > 1 else None

    if source.startswith(":"):
        return ["docker", "cp", cid + ":" + source[1:], destination or "."]

    if destination is None:
        destination = setting(parser, "General", "workdir")
        if not destination:
            die("cp needs a destination, or a workdir = ... in [General]")
    return ["docker", "cp", source, cid + ":" + destination.lstrip(":")]


def init_config(argv):
    """Write the packaged example somewhere it will be found, then say where."""
    if len(argv) > 1:
        die("usage: %s init [FILE]" % PROG)
    destination = argv[0] if argv else CONFIG_NAME
    if os.path.isdir(destination):
        destination = os.path.join(destination, CONFIG_NAME)
    if os.path.exists(destination):
        die("%s already exists — remove it, or name another file" % destination)

    source = example_path()
    try:
        if hasattr(source, "read_text"):
            with open(destination, "w") as handle:
                handle.write(source.read_text())
        else:
            shutil.copyfile(source, destination)
    except OSError as error:
        die("could not write %s: %s" % (destination, error))

    print("wrote %s — set name = ... in [General] to your container,\n"
          "  then `%s` lists what you can run in it." % (destination, PROG))
    return 0


def usage(path, parser):
    name = parser.get("General", "name").strip()
    sections = [s for s in parser.sections() if s != "General"]
    lines = [
        "usage: %s <command> [arguments...]" % PROG,
        "",
        "%s  ->  container %s" % (path, name),
    ]
    if sections:
        lines += ["", "commands:"]
        width = max(len(s) for s in sections)
        for section in sections:
            described = parser.get(section, "help", fallback="").strip()
            if not described:
                described = parser.get(section, "program", fallback="").strip()
            lines.append("  %-*s  %s" % (width, section, described))
    width = max(len(command) for command, _ in BUILTINS)
    lines += ["", "built in:"]
    for command, described in BUILTINS:
        if command in sections:
            continue
        lines.append("  %-*s  %s" % (width, command, described))
    print("\n".join(lines))


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # init and --help are what you reach for when there is no config yet,
    # so neither of them may insist on finding one.
    if argv and argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    if argv and argv[0] == "--version":
        print(VERSION)
        return 0
    if argv and argv[0] == "init":
        return init_config(argv[1:])

    path, parser = load_config()
    if not argv:
        usage(path, parser)
        return 0

    command, arguments = argv[0], argv[1:]
    name = parser.get("General", "name").strip()

    if parser.has_section(command):
        run = exec_command(parser, command, container_id(name), arguments)
    elif command == "id":
        print(container_id(name, include_stopped=True))
        return 0
    elif command == "logs":
        run = ["docker", "logs"] + (arguments or ["-f"]) + [container_id(name, True)]
    elif command in ("start", "stop", "restart"):
        run = ["docker", command] + arguments + [container_id(name, True)]
    elif command == "cp":
        run = copy_command(parser, container_id(name, True), arguments)
    else:
        die("no command %r in %s, and no built-in by that name.\n"
            "%s  `%s` on its own lists what there is."
            % (command, os.path.basename(path), " " * (len(PROG) + 2), PROG))

    # Hand the terminal straight to docker: signals, the tty and the exit
    # status are then its business rather than something to relay.
    os.execvp(run[0], run)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
