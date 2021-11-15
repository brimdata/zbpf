import sys, select, zed

def send(lines):
    lake.load('bpf', '\n'.join(lines))
    print("loaded %d lines" % len(lines))

lake = zed.Client()
lines=[]
while True:
    i, o, e = select.select([sys.stdin], [], [], 1)
    if (i):
        lines.append(sys.stdin.readline().strip())
        if len(lines) >= 500:
            send(lines)
            lines = []
    else:
        if len(lines) > 0:
            send(lines)
            lines = []
