# zbpf

This repo describes a very rough proof-of-concept for integrating
[Zed](https://github.com/brimdata/zed)
into
[BPF](https://ebpf.io/).
The idea is to arrange for BPF to emit events and aggregates
directly in the
[super-structured Zed format](https://github.com/brimdata/zed/blob/zed-update/docs/formats/zdm.md)
and stream updates live into a
[Zed lake](https://github.com/brimdata/zed/tree/main/docs/lake).

> Zed's super-structured approach allows data to be completely self describing using
> its comprehensive type system so that external schemas do not need to be
> defined and declared for richly typed data.

Note that we are using the term "BPF" to refer to the modern eBPF Linux
subsystem as the
[original BPF](https://www.usenix.org/conference/usenix-winter-1993-conference/bsd-packet-filter-new-architecture-user-level-packet)
is now called "classic BPF"
[as explained by Brendan Gregg in his LISA21 talk](https://youtu.be/_5Z2AU7QTH4?t=82).

The examples described here are directly embedded in the Python tooling from the
[BPF Compiler Collection (BCC)](https://github.com/iovisor/bcc), but the
approach would be also applicable to
[bpftrace](https://github.com/iovisor/bpftrace)
or to any custom BPF application.

## Motivation

Dealing with data is hard.  To keep things simple, people often simplify
their rich data with "go to" and ubiquitous formats like CSV and JSON.
While simple in appearance,
these formats can be
[frustrating in practice](https://www.bitsondisk.com/writing/2021/retire-the-csv/).

We were recently interacting with a colleague at a research university who
was instrumenting database performance using BPF.  The team there wrote
a bunch of custom BCC apps, which generated huge numbers of large CSV files.
They would then analyze this bulky data with custom Python/Pandas code,
along with running SQL analytics on an RDBMS.

Our colleague was pulling his hair out: running out of disk space,
dealing with thousands of CSV files in his local file system conforming
to many different and changing column layouts, and
updating tables in the SQL database to track changes in their
collection methodology.  It was a nightmare.

Then our friend remembered Zed and asked, "Isn't this where Zed is supposed to help?"
Yes, of course!

The obvious approach here would be to simply load all the CSV files into a Zed lake
(e.g., running on S3 to overcome storage limits),
then run SQL and/or Zed queries on the Zed lake.  Yet we wondered if there
could be some benefit in a deeper integration with BPF.

One of the difficulties in data
management is that the source of data often has rich and detailed information
about the types and structure of this origin data, only to throw that information
away when serializing into formats like CSV or JSON.  Indeed in BPF, the BCC tooling
has direct access to in-kernel C data structures with all of their type information
and potentially hierarchical structure.  The BCC Python code, for instance,
accesses native BPF events via the
[`ctypes`](https://docs.python.org/3/library/ctypes.html) library.

Yet our colleague's BCC tooling simply threw away this detailed type information
and instead wrote its output as CSV records in
a fixed set of hard-coded columns.

There must be a better way.

What if you could simply marshal any `ctypes` struct into a Zed record
and efficiently serialize this record as
[ZNG](https://github.com/brimdata/zed/blob/main/docs/formats/zng.md)?
Then BPF code that captured
native C events could simply marshal the data directly and send it along to a Zed lake.
Because Zed doesn't require schema definitions nor does it organize data
into tables, all these native C events could be intermingled and efficiently
transmitted into a Zed lake with minimal effort.

Moreover, if we mapped the type name of the C struct to a Zed type, then we
could use Zed type queries to pull out all of the records of a given type.
So, it's sort of like having tables without ever having to create them.

To explore this idea of efficient serialization of BPF events as ZNG,
we first developed the simple proof-of-concept here.  We don't have a
`ctypes` marshaler working yet nor do we have Zed output serialiead as ZNG.
Rather we instrumented a couple of BCC tools (namely, `execsnoop` and `stackcount`)
with flags to generate the human-readable ZSON format and load this data
directly into a Zed lake.

> ZSON much less efficient than ZNG, but we just wanted to try something simple
> here to see what people think and whether further work is warranted.

## Setup

To explore this proof of concept,
you will need a Linux environment with BPF enabled (the "Linux host")
and a client environment (the "desktop host") to query the BPF data.
The desktop host will query a
Zed lake running on the Linux host.

> If you happen to be running
> a BPF-enabled desktop or laptop, then the Linux host and desktop host
> could be one and the same.

### The Linux host

Provision a Linux host with a recent kernel and recent version of
BPF enabled.
[See below](#appendix-macbook-setup)
for some hints for running a recent Linux using Vagrant on a MacBook
but any recent Linux running anywhere should work.

Install Zed (`v0.33` or later) on your Linux host.
Follow the instructions in the repository's
[GitHub Releases](https://github.com/brimdata/zed/releases).

Install the latest Zed Python module on your Linux host:
```
pip3 install "git+https://github.com/brimdata/zed#subdirectory=python/zed"
```

Clone the Zed-modified BCC tooling.  We forked the BCC repository
and made the modifications on a branch therein called `zed`:
```
git clone https://github.com/brimdata/bcc.git
cd bcc
git checkout zed
```

A Zed lake service must run during the
course of experiments described below.
In a terminal on your Linux host, create this service as follows:
```
mkdir scratch
zed lake serve -R scratch
```
In another terminal on the Linux host, create a Zed data pool for the
BPF data and test that everything is working with `zapi ls`:
```
zapi create bpf
zapi ls
```
The `zapi ls` command should display the pool called `bpf`.
Note that the Zed-enhanced BCC tools are configured to write
to the `bpf` pool.

> Note that in a production environment, the Linux host would post data
> to a Zed lake running at scale elsewhere.  For this experiment,
> we are simply running the Zed lake directly on the Linux host.

### The desktop host

To query the Zed lake running on the Linux host, you should install
Zed and or Brim on your desktop/laptop.

Install these packages following the instructions in
[Zed releases](https://github.com/brimdata/zed/releases)
(as described above for the Linux host) or
[Brim releases](https://github.com/brimdata/brim/releases).

You can also [build Zed from source](https://github.com/brimdata/zed#building-from-source).

#### `zapi`

By default, `zapi` connects to the lake service API at `http://localhost:9867`,
which is also the default port used by `zed lake serve`.
Thus, you can run `zapi` commands on the Linux host without any configuration.

On the desktop host, to point `zapi` at the lake running on Linux host,
you can use the `-lake` command-line option or simply set
the `ZED_LAKE` environment variable, e.g.,
```
export ZED_LAKE=http://linux-host:9867
```
where _linux-host_ is the IP or DNS name of the Linux host.

For the Vagrant setup described
[described below](#appendix-macbook-setup), the desktop port 8098 is
forwarded to the Linux port 9876, so you should use this for `ZED_LAKE`:
```
export ZED_LAKE=http://localhost:8098
```

#### Brim

The Brim app is a desktop application based on Electron, similar to the Slack
desktop model.  Brim is a nice way to look at Zed data.

To open a lake inside Brim, click on the current lake name in the upper left
of Brim's window.  This will bring up a drop-down menu and you should click on
the "Add Lake..." option at the bottom of the menu.  A form will appear and
you can enter a name (e.g., "Linux BPF Lake") and a URL for the lake.  The URL
should be one of the two options [described above](#zapi-on-the-desktop-host):
* `http://linux-host:9867`, or
* `http://localhost:8098`.

## Running Experiments

To run a BPF/Zed capture experiment on the Linux host,
`cd` into the top-level directory of the forked BCC repo
(remember you need to be on the `zed` git branch).

Then, to run an experiment, specify the `-z` flag for Zed,
and try either _execsnoop_:
```
sudo python3 ./tools/execsnoop.py -z
```
Or _stackcount_:
```
sudo python3 ./tools/stackcount.py -i 1 -P -z ip_output
```
For _stackcount_, we have specified "ip_output" as the kernel function to trace,
but you can try any BPF-traceable function.  We also specified
`-i 1` so that data is transmitted to the Zed lake every second,
and `-P` so we get per-process stats (in particular, the process name
for each stack is present).

In either case, you can hit ctrl-C to terminate.

>Note that these two programs have the pool "bpf" hardwired.

 Now, you can look at the data in the pool with `zapi query`
 run either on the Linux host or the desktop host
 (configured as described above):
```
zapi query -use bpf@main -Z "sum(count) by stack,name | sort sum"
```

Note that `execsnoop` labels uses the Zed type name "exec" for its records
and `stackcount` likewise uses the name "stack".  Thus, you can query by type
to get the records that came from each different command:
```
zapi query -use bpf@main -Z "is(type(exec))"
zapi query -use bpf@main -Z "is(type(stack))"
```

For the examples below, we started both _execsnoop_ and _stackcount_
on the Linux host, then and the bash script [`workload`](./workload)
to generate synthetic activity.

## Examples

With your BPF trace data in a Zed lake, searching and analyzing your data
is a piece of cake.  You can also slice and dice the data in the lake
and export it in most any format you'd like (JSON, Parquet, CSV, or any Zed format).

First, make sure `zapi` query uses the `bpf` pool for your queries, as above,
by running
```
zapi use bpf@main
```
Here is a simple query that counts the number of times the
string "__tcp_transmit_skb" appears in a stack trace (from `stackcount`):
```
zapi query '"__tcp_transmit_skb" in stack | count()'
```
and you'll get a result that looks like this as the default format is ZSON:
```
{count:650(uint64)}
```
If you want JSON output, just add `-f json`:
```
zapi query -f json '"__tcp_transmit_skb" in stack | count()'
{"count":650}
```
Here's another cool one.  This counts up stuff by the `name` field where
the name could be in either a stack record or a process record:
```
zapi query "count() by name"
```
And you get output like this:
```
{name:"kworker/u4:3",count:4(uint64)}
{name:"kworker/u4:1",count:1(uint64)}
{name:"ps",count:2(uint64)}
{name:"python3",count:29(uint64)}
{name:"zq",count:1(uint64)}
{name:"zed",count:79(uint64)}
{name:"ksoftirqd/0",count:1(uint64)}
{name:"ls",count:10(uint64)}
{name:"swapper/1",count:21(uint64)}
{name:"find",count:3(uint64)}
{name:"ksoftirqd/1",count:11(uint64)}
{name:"sshd",count:54(uint64)}
{name:"systemd-resolve",count:6(uint64)}
{name:"grep",count:1(uint64)}
{name:"curl",count:31(uint64)}
{name:"swapper/0",count:2(uint64)}
```
Or if you want a table, you can specify `-f table`:
```
zapi query -f table "count() by name"
```
to get
```
name            count
python3         29
curl            31
zed             79
kworker/u4:1    1
ksoftirqd/1     11
kworker/u4:3    4
ls              10
grep            1
zq              1
ps              2
systemd-resolve 6
swapper/0       2
sshd            54
find            3
ksoftirqd/0     1
swapper/1       21
```

Here is a more sophisticated query where we sum up the counts from every
1 second sampling interval and we use the "stack" and the process "name"
as group-by keys.  Note that the Zed query language is perfectly happy using
any Zed value (including arrays) as a group-by key.
```
zapi query -Z "sum(count) by stack,name | sort -r sum | head 2"
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
        "vfs_write",
        "ksys_write",
        "__x64_sys_write",
        "do_syscall_64",
        "entry_SYSCALL_64_after_hwframe"
    ],
    name: "sshd",
    sum: 334
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
        "inet6_sendmsg",
        "sock_sendmsg",
        "sock_write_iter",
        "new_sync_write",
        "vfs_write",
        "ksys_write",
        "__x64_sys_write",
        "do_syscall_64",
        "entry_SYSCALL_64_after_hwframe"
    ],
    name: "zed",
    sum: 136
}
```

Here is a more sophisticated example.
This query computes the unique set of stacks grouped by the parent caller
of the traced function (in this case `ip_output`):
```
zapi query -Z "has(stack[1]) | stacks:=union(stack) by callee:=stack[1]"
```
giving output like this
```
{
    callee: "tcp_v4_send_synack",
    stacks: |[
        [
            "ip_output",
            "tcp_v4_send_synack",
            "tcp_conn_request",
            "tcp_v4_conn_request",
            "tcp_v6_conn_request",
            "tcp_rcv_state_process",
            "tcp_v4_do_rcv",
            "tcp_v4_rcv",
            "ip_protocol_deliver_rcu",
            "ip_local_deliver_finish",
            "ip_local_deliver",
            "ip_sublist_rcv_finish",
            "ip_list_rcv_finish.constprop.0",
            "ip_sublist_rcv",
            "ip_list_rcv",
            "__netif_receive_skb_list_core",
            "__netif_receive_skb_list",
            "netif_receive_skb_list_internal",
            "napi_complete_done",
            "e1000_clean",
            "napi_poll",
            "net_rx_action",
            "__softirqentry_text_start",
            "asm_call_sysvec_on_stack",
            "do_softirq_own_stack",
            "irq_exit_rcu",
            "common_interrupt",
            "asm_common_interrupt"
        ],
        [
            "ip_output",
            "tcp_v4_send_synack",
            "tcp_conn_request",
            "tcp_v4_conn_request",
            "tcp_v6_conn_request",
            "tcp_rcv_state_process",
            "tcp_v4_do_rcv",
            "tcp_v4_rcv",
            "ip_protocol_deliver_rcu",
            "ip_local_deliver_finish",
            "ip_local_deliver",
            "ip_rcv_finish",
            "ip_rcv",
            "__netif_receive_skb_one_core",
            "__netif_receive_skb",
            "process_backlog",
            "napi_poll",
            "net_rx_action",
            "__softirqentry_text_start",
            "asm_call_sysvec_on_stack",
            "do_softirq_own_stack",
            "do_softirq",
            "__local_bh_enable_ip",
            "ip_finish_output2",
            "__ip_finish_output",
            "ip_finish_output",
            "ip_output",
            "__ip_queue_xmit",
            "ip_queue_xmit",
            "__tcp_transmit_skb",
            "tcp_connect",
            "tcp_v4_connect",
            "__inet_stream_connect",
            "inet_stream_connect",
            "__sys_connect_file",
            "__sys_connect",
            "__x64_sys_connect",
            "do_syscall_64",
            "entry_SYSCALL_64_after_hwframe"
        ]
    ]|
}
...
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

The power of super-structured data and Zed is that types are first class.
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
    typeof: (stack=({ts:time,name:string,ustack:[string],stack:[string],count:int64})),
    count: 256 (uint64)
}
{
    typeof: (exec=({ts:time,pcomm:string,pid:int64,ppid:int64,ret:int64,args:[string]})),
    count: 30 (uint64)
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
        ts: 2021-11-22T14:45:09Z,
        name: "ksoftirqd/1",
        ustack: [] ([string]),
        stack: [
            "ip_output",
            "ip_queue_xmit",
            "__tcp_transmit_skb",
            "tcp_write_xmit",
            "tcp_tsq_write.part.0",
            "tcp_tsq_handler",
            "tcp_tasklet_func",
            "tasklet_action_common.constprop.0",
            "tasklet_action",
            "__softirqentry_text_start",
            "run_ksoftirqd",
            "smpboot_thread_fn",
            "kthread",
            "ret_from_fork"
        ],
        count: 1
    } (=stack)
}
{
    val: {
        ts: 2021-11-22T14:45:08Z,
        pcomm: "find",
        pid: 204580,
        ppid: 204536,
        ret: 0,
        args: [
            "/usr/bin/find",
            "../bcc"
        ]
    } (=exec)
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

## Appendix: MacBook Setup

I ran the experiments above using a Linux host configured on VirtualBox
using vagrant running on a MacBook.

I adjusted a few things from [the instructions here](https://codeboten.medium.com/bpf-experiments-on-macos-9ad0cf21ea83),
mainly to use a newer version of Ubuntu Hirsute (21.04)
along with the more up-to-date BPF tooling referenced in
[BCC issue #2678](https://github.com/iovisor/bcc/issues/2678#issuecomment-883203478).

I used the [PPA here](https://chabik.com/2021/09/ppas-update/),
but for these experiments, installed only bpfcc:
```
sudo add-apt-repository ppa:hadret/bpftrace
sudo add-apt update
sudo add-apt install bpfcc
```

Also, I added a port forwarding rule in the [Vagrantfile](./Vagrantfile):
```
Vagrant.configure("2") do |config|
  ...
  config.vm.network "forwarded_port", guest: 9867, host: 8098
```

# Demo notes - OpenObservability Podcast

> If we have enough time,
> this section contains a quick outline of a demo that I will run through
> during the [OpenObservability Podcast](https://openobservability.io/)
> at 11am on November 23, 2021.

[Motivated by colleague at CMU.](#motivation)

Exploit super-structured Zed data to make BPF instrumentation easier.

Everything is open source.

### Setup

* Based on this [`zbpf` repository](https://github.com/brimdata/zbpf)
    * can reproduce everything here
* Modified two BCC tools to produce Zed directly
    * _snoopexec_, _stacktrace_
    * The [diffs](https://github.com/brimdata/bcc/commit/9a8d6b95ec7bb9490c63f4d82524a58ba0142eeb) are in a [forked repo](https://github.com/brimdata/bcc)
* Ran experiments on my MacBook using vagrant and recent Linux
    * Zed lake runs on Linux host
    * Modified BCC tooling streams super-structured Zed data straight to lake
    * Queries run on desktop host
        * `zapi`
        * Brim app

**TL;DR** if you want to just play around with this BPF data without setting
up a Linux environment or even a Zed lake, you can just run Brim using
* The [bpf.zson file](bpf.zson) from our BPF experiment, and
* [sample queries](queries.json) for Brim.

You can drag the sample data into the Brim app and drag the queries into
the side panel where the query library is located.  Brim will automatically
launch a local lake that `zapi` will connect to.  To have the `zapi` commands
connect to the pool created from dragging `bpf.zson` into the app, issue
the command
```
zed use bpf.zson@main
```

### Zed basics

ZSON is a superset of JSON, and much more powerful
```
echo '{"ts":"11/22/2021 8:01am", "addr":"10.0.0.1", "number":"98.6"}' | zq -Z 'this:=cast(this, type({ts:time,addr:ip,number:float64}))' -
```
We can get the JSON back if you'd like (with a standard time)...
```
echo '{"ts":"11/22/2021 8:01am", "addr":"10.0.0.1", "number":"98.6"}' | zq -Z 'this:=cast(this, type({ts:time,addr:ip,number:float64}))' - | zq -f json - | jq
```
We can output Zed in an efficient binary form.  Then get back the type information...
```
echo '{"ts":"11/22/2021 8:01am", "addr":"10.0.0.1", "number":"98.6"}' | zq -f zng 'this:=cast(this, type({ts:time,addr:ip,number:float64}))' - > binary.zng
cat binary.zng
hexdump binary.zng
zq 'cut typeof(this)' binary.zng
```
There is much more to it, but I will refer you to the Zed docs for more info...

### The BPF data

Zed lake service is running on the Linux guest VM.

Earlier ran a simple [workload](https://github.com/brimdata/zbpf/blob/main/workload)
while _execsnoop_ and _stackcount_ were running.

We'll tell the `zapi` CLI command (for hitting Zed lake API) to use the
"main" branch of a pool called "bpf":
```
zapi use bpf@main
```

It's quite a small data set but Zed lakes are designed to scale...
```
zapi query "count()"
```

Have a look at some pretty-printed (-Z) records...
```
zapi query -Z "* | head 42"
```

That's interesting... count up all the stacks containing __tcp_transmit_skb_:
```
zapi query '"__tcp_transmit_skb" in stack | count()'
```
Are they always in the grandparent caller position?
```
zapi query 'stack[2]=="__tcp_transmit_skb" | count()'
```
One isn't!  Find it and pretty print it...
```
zapi query -Z 'stack[2]!="__tcp_transmit_skb" and "__tcp_transmit_skb" in stack'
```
How about listing the events from _execsnoop_?
```
zapi query -Z 'is(type(exec))'
```
What are all the commands that were run?
```
zapi query -Z 'commands:=union(pcomm)'
```
And what about their paths?  Let's take a union over record expressions:
```
zapi query -Z 'commands:=union({name:pcomm,path:args[0]})'
```
Pretty cool!

We'll cut over to the app here and run through the
[queries in the library](queries.json)...
