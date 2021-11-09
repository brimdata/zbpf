import fileinput
import zed

lake = zed.Client()

for line in fileinput.input():
    z = line.strip()
    if len(z) != 0:
        print(line)
        lake.load('bpf', line)
