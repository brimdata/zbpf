# zbpf

Run a service:
```
mkdir scratch
zed lake serve -R scratch
```

Create a pool for BPF:
```
zapi create bpf
```
(note `loader.py` has pool "bpf" hardwired.)


```
sudo ./execsnoop-bpfcc | python3 loader.py
sudo ./stackcount-bpfcc -i 1 -z ip_output | python3 loader.py
zapi use -p bpf
zapi query -Z "sum(count) by kernel,name | sort sum"
```
