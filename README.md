# zbpf

I took a stab at a quick and dirty prototype to see what it was like to
emit BPF-collected data directly in the super-structured Zed format
and stream updates live into a Zed lake.

> TBD: add link to pending Zed arch doc

> Zed's super-structured approach allows data to be completely self describing using
> its comprehensive type system so that external schemas do not need to be
> defined and declared for richly typed data.

## Setup

To get going,
I followed [the instructions here](https://codeboten.medium.com/bpf-experiments-on-macos-9ad0cf21ea83)
for setting up a VirtualBox linux kernel on my Mac with BPF enabled.

> This setup resulted in an older version of the BCC tools to be installed
> that use Python2.  If we take a more serious stab at this project, we'll
> make it all work with the latest versions of BPF tooling.

I think copy two tools from `/usr/sbin` to this repo:
`stackcount-bpfcc` and `execsnoop-bpfcc`.
I hacked in a change to output events as ZSON lines of text.

Also, since the Zed Python client assumes Python3, I created a
separate "loader" script to bundle lines of ZSON with a timeout
and commit each bundle to a Zed server on running on `localhost`.

Install `zed` on your linux host by following
the instructions in the
[Zed repository Releases section](https://github.com/brimdata/zed/releases).

## Running Experiments

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

## Sample Output
