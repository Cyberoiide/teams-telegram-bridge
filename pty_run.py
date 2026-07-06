#!/usr/bin/env python3
# ponytail: minimal PTY driver so intune-container's rpassword (opens /dev/tty)
# and interactive subcommands work from a non-tty harness. Feeds PW_ANSWER to any
# "assword" prompt; streams everything else through. Usage: pty_run.py CMD ARGS...
import pty, os, sys, subprocess, select, time, fcntl, termios

os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ["PATH"]
answer = os.environ.get("PW_ANSWER", "ponytail-pw").encode() + b"\n"
timeout = int(os.environ.get("PTY_TIMEOUT", "900"))

mfd, sfd = pty.openpty()
def setup():
    os.setsid()
    fcntl.ioctl(sfd, termios.TIOCSCTTY, 0)

p = subprocess.Popen(sys.argv[1:], stdin=sfd, stdout=sfd, stderr=sfd,
                     close_fds=True, preexec_fn=setup)
os.close(sfd)
buf = b""; pw = 0; deadline = time.time() + timeout
while True:
    if p.poll() is not None:
        while True:
            r, _, _ = select.select([mfd], [], [], 0.3)
            if not r: break
            try: buf += os.read(mfd, 4096)
            except OSError: break
        break
    r, _, _ = select.select([mfd], [], [], 1.0)
    if r:
        try: c = os.read(mfd, 4096)
        except OSError: break
        if not c: break
        buf += c
        sys.stdout.buffer.write(c); sys.stdout.flush()
        if b"assword" in c and pw < 2:
            os.write(mfd, answer); pw += 1
    if time.time() > deadline:
        p.kill(); break
sys.exit(p.returncode or 0)
