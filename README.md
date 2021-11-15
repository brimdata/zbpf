# zbpf

I took a stab at a quick and dirty prototype to see what it was like to
emit BPF-collected data directly in the
[super-structured Zed format](https://github.com/brimdata/zed/blob/zed-update/docs/formats/zdm.md)
and stream updates live into a Zed lake.

> Zed's super-structured approach allows data to be completely self describing using
> its comprehensive type system so that external schemas do not need to be
> defined and declared for richly typed data.

> TBD: update Zed arch doc after branch is merged.

## Setup on Mac

I set up tooling on my Mac with VirtualBox but a similar pattern should work on
other systems or native linux instances.

I adjusted a few thing in [the instructions here](https://codeboten.medium.com/bpf-experiments-on-macos-9ad0cf21ea83),
mainly to use a newer version of Ubuntu Hirsute (21.04) (which should work on Windows WSL2)
along with the more up-to-date BPF tooling referencing in
[BCC issue #2678](https://github.com/iovisor/bcc/issues/2678#issuecomment-883203478).

Since the latest tools in the `bcc` repo didn't run for me on this kernel,
I just copied two tools from `/usr/sbin` to this repo:
`stackcount-bpfcc` and `execsnoop-bpfcc`.
I hacked each of these tools to output events as ZSON lines of text
instead of text sent to st.

Also, since the Zed Python client assumes Python3, I created a
separate "loader" script to bundle lines of ZSON with a timeout
and commit each bundle to a Zed server on running on `localhost`
instead of bundling this logic in the bcc tooling.

Install `zed` on your linux host by following
the instructions in the
[Zed repository Releases section](https://github.com/brimdata/zed/releases).

## Running Experiments

Run a Zed lake service on your bcc-enabled linux host:
```
mkdir scratch
zed lake serve -R scratch
```
On the same host, create a Zed data pool for BPF:
```
zapi create bpf
```

Then run any experiments you'd like with this tooling and various options,
hitting ctrl-C to terminate, e.g.,
```
sudo ./execsnoop-bpfcc | python3 loader.py
sudo ./stackcount-bpfcc -i 1 -z ip_output | python3 loader.py
```

>Note the `loader.py` program has the pool "bpf" hardwired.

 Now, you can look at the data in the pool with `zapi query`:
```
zapi use bpf@main
zapi query -Z "sum(count) by stack,name | sort sum"
```

> Note that Zed lakes have branching and merging just like `git`.  We are going
> to simplify the commitish so you can say `bpf` instead of `bpf@main` where the
> commitish will default to the `main` branch.

## The Brim App

The [Brim app](https://github.com/brimdata/brim) is a nice way to look at Zed data.
Brim is a desktop app based on Electron, similar to the Slack desktop model.

For my Mac/vagrant setup, I configured a port forwarding rule in the
Vagrantfile that came with the `bpftracing` repo by adding the
"forwarded_port" rule below:
```
Vagrant.configure("2") do |config|
  ...
  config.vm.network "forwarded_port", guest: 9867, host: 8098
```
Then, in the Brim app, I added a lake connection to `localhost:8098`.

## Examples

With your BPF trace data in a Zed lake, searching and analyzing your data
is a piece of cake.  You can also slice and dice the data in the lake
and export it in most any format you'd like (JSON, Parquet, CSV, or any Zed format).

First, make sure zapi query uses the "bpf" pool for your queries, as above,
by running
```
zapi use bpf@main
```
Here is a simple query that counts the number of times the
string "__tcp_transmit_skb" appears in a stack trace (from `stackcount-bpfcc`):
```
zapi query '"__tcp_transmit_skb" in stack | count()'
```
and you'll get a result that looks like this as the default format is ZSON:
```
{count:650(uint64)}
```
If you want JSON output, just add `-f json`:
```
% zapi query -f json '"__tcp_transmit_skb" in stack | count()'
{"count":650}
```
Here's another cool one.  This counts up stuff by the `name` field where
the name could be in either a stack record or a process record...
```
zapi query "from bpf | count() by name"
```
and you get output like this
```
{name:"swapper/0",count:7(uint64)}
{name:"python3",count:113(uint64)}
{name:"sshd",count:73(uint64)}
{name:"zed",count:392(uint64)}
{name:"kworker/u4:3",count:2(uint64)}
{name:"ksoftirqd/1",count:21(uint64)}
{name:"ksoftirqd/0",count:1(uint64)}
{name:"swapper/1",count:44(uint64)}
```
Here is a more sophisticated query where we sum up the counts from every
1 second sampling intervel and we use the "stack" and the process "name"
as group-by keys.  Note that the Zed query language is perfectly happy using
any Zed value (including arrays) as a group-by key.
```
zapi query -Z "from bpf | sum(count) by stack,name | sort -r sum | head 2"
```
This will give the top two stack traces and will look something like this
in the pretty-printed (`-Z`) ZSON output:
```
{
    stack: [
        "ip_output",
        "ip_queue_xmit",
        "__tcp_transmit_skb",
        "tcp_write_xmit",
        "__tcp_push_pending_frames",
        "tcp_push",
        "tcp_sendmsg_locked",
        "tcp_sendmsg",
        "inet_sendmsg",
        "sock_sendmsg",
        "sock_write_iter",
        "new_sync_write",
        "__vfs_write",
        "vfs_write",
        "sys_write",
        "do_syscall_64",
        "entry_SYSCALL_64_after_hwframe"
    ],
    name: "sshd",
    sum: 2020
}
{
    stack: [
        "ip_output",
        "ip_queue_xmit",
        "__tcp_transmit_skb",
        "tcp_write_xmit",
        "__tcp_push_pending_frames",
        "tcp_push",
        "tcp_sendmsg_locked",
        "tcp_sendmsg",
        "inet_sendmsg",
        "sock_sendmsg",
        "sock_write_iter",
        "new_sync_write",
        "__vfs_write",
        "vfs_write",
        "sys_write",
        "do_syscall_64",
        "entry_SYSCALL_64_after_hwframe"
    ],
    name: "zed",
    sum: 1851
}
```

### Zed and Data Shapes

Zed is a bit different and lets you put super-structured data all in one
location.  It's kind of like rich database tables without having to define
tables and schemas ahead of time.  While this may sound to you like a NoSQL store,
e.g., Mongo or CouchDB, it's quite different because Zed data is super-structured
instead of semi-structured:
super-structured data has a well-defined type for every value whereas semi-structured
data has implied types and the "shape" of a semi-structured data value can only be
determined by traversing that value.

The power of super-structured data types and Zed is that types are first class.
This means you can put a type anywhere a value can go, and in particular,
the Zed query language includes a `typeof()` operator that returns the type
of a value as a value.  So you can say things like
```
zapi query -Z 'count() by typeof(this)'
```
to see the "shape" of all the values in a data pool, e.g., giving output
that looks like this:
```
{
    typeof: (stack=({name:string,ustack:[string],stack:[string],count:int64})),
    count: 578 (uint64)
}
{
    typeof: ({ts:time,pcomm:string,pid:int64,ppid:int64,ret:int64,args:string}),
    count: 13 (uint64)
}
```
Or you could get a sample of each shape by saying this:
```
zapi query -Z 'val:=any(this) by typeof(this) | cut val'
```
giving a result like this:
```
{
    val: {
        ts: 2021-11-08T13:17:41Z,
        pcomm: "cp",
        pid: 2234,
        ppid: 1973,
        ret: 0,
        args: "/bin/cp /usr/sbin/opensnoop-bpfcc ."
    }
}
{
    val: {
        name: "python3",
        ustack: [
            "_PyEval_EvalFrameDefault",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]",
            "[unknown]"
        ],
        stack: [
            "ip_output",
            "ip_queue_xmit",
            "__tcp_transmit_skb",
            "tcp_write_xmit",
            "tcp_tsq_handler.part.42",
            "tcp_tasklet_func",
            "tasklet_action",
            "__do_softirq",
            "irq_exit",
            "do_IRQ",
            "ret_from_intr"
        ],
        count: 1
    } (=stack)
}
```

## Zed for Telemetry

We think Zed could be a really great way to store and query telemetry data
as it unifies events and metrics.  It's not just a single format but
[a family of formats](https://github.com/brimdata/zed/tree/main/docs/formats)
that all adhere to exactly the same data model.  ZNG is the efficient row-based format
and ZST is the columnar format.

> The ZST implementation is still a bit early...

[The Zed lake](https://github.com/brimdata/zed/tree/main/docs/lake)
is designed to ingest row-based ZNG then run indexing, compaction, and columnar-conversion as data objects stabilize (there's a nice API for querying objects and their metadata --- of course using ZNG --- so these indexing workflows can be driven by external agents and different agents can be developed for different use cases).

Unlike search systems, all the queries work whether indexed or not
and indexes simply speed things up.  And if you change indexing rules,
you don't need to reindex everything.  Just the stuff you want
the new rules to apply to.
