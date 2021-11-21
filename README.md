# zbpf

This repo contains a very lightweight, proof-of-concept for integrating
Zed into BPF.  The idea is to arrange for BPF to emit events and aggregates
directly in the
[super-structured Zed format](https://github.com/brimdata/zed/blob/zed-update/docs/formats/zdm.md)
and stream updates live into a Zed lake.

> Zed's super-structured approach allows data to be completely self describing using
> its comprehensive type system so that external schemas do not need to be
> defined and declared for richly typed data.

> TBD: update Zed arch doc after branch is merged.

The examples here are directly embedded in the Python tooling from the
[BPF Compiler Collection (BCC)](https://github.com/iovisor/bcc), but the
approach would be also applicable to
[bpftrace](https://github.com/iovisor/bpftrace)
or to any custom BPF application.

## Motivation

XXX story about CSV and BPF measurements

## Setup

You will need a linux environment with BPF enabled (the "linux host")
and a client host (the "desktop host") that you will use to query a
Zed lake running on the linux host.  If you happen to be running
a BPF-enabled desktop or laptop, then the linux host and desktop host
could be the same.

### The linux host

Provision a linux host with a recent kernel and recent version of
BPF enabled.
[See below](#appendix:-macbook-setup)
for some hints for running a recent linux using Vagrant on a MacBook
but any recent linux running anywhere should work.

Install `zed` (`v0.33` or later) on your linux host.
Follow the instructions in the repository's
[Github Releases](https://github.com/brimdata/zed/releases).

Install the latest `zed` Python module on your linux host:
```
pip3 install "git+https://github.com/brimdata/zed#subdirectory=python/zed"
```

Clone the Zed-modified BCC tooling.  We forked the BCC repository
and made the modifications on a branch therein called `zed`:
```
git clone https://github.com/brimdata/bcc.git
git checkout zed
```

A Zed lake service must run during the
course of experiments described below.
In a terminal on your linux host, create this service as follows:
```
mkdir scratch
zed lake serve -R scratch
```
In another terminal on the linux host, create a Zed data pool for the
BPF data and test that everything is working with `zapi ls`:
```
zapi create bpf
zapi ls
```
The `zapi ls` command should display the pool called `bpf`.

> Note that in a production environment, the linux host would post data
> to a Zed lake running at scale elsewhere.  For this experiment,
> we are simply running the Zed lake directly on the linux host.

### The desktop host

To query the Zed lake running on the linux host, you should install
zed and or Brim on your desktop/laptop.

Install these packages following the instructions in
[Zed releases](https://github.com/brimdata/zed/releases)
(as described above for the linux host)
[Brim releases](https://github.com/brimdata/brime/releases).

You can also [build Zed from source](https://github.com/brimdata/zed#building-from-source).

#### `zapi`

By default, `zapi` connects to the lake service API at `http://localhost:9867`,
which is also the default port used by `zed lake serve`.
Thus, you can run `zapi` commands on the linux host without any configuration.

On the desktop host, to point `zapi` at the lake running on linux host,
you can use the `-lake` command-line option or simply set
the `ZED_LAKE` environment, e.g.,
```
export ZED_LAKE=http://linux-host
```
where _linux-host_ is the IP or DNS name of the linux host.
If no port is supplied in the lake URL, then 9867 is assumed.

For the Vagrant setup described
[described below](#appendix:-macbook-setup), the desktop port 8098 is
forwarded to the linux port 9876, so you should use this for ZED_LAKE:
```
export ZED_LAKE=http://localhost:8098
```

#### Brim

The Brim app is a desktop application based on Electron, similar to the Slack
desktop model.  Brim is a nice way to look at Zed data.

To open a lake inside Brim, click on the current lake name in the upper left
of Brim's window.  This will bring up a drop-down menu and you should click on
the "Add Lake..." option at the bottom of the menu.  A form will appear and
you can enter a name (e.g., "Linux BPF Lake") and an URL for the lake.  The URL
should be one of the two options [described above](#zapi-on-the-desktop-host):
* `http://linux-host`, or
* `http://localhost:8098`.

## Running Experiments

Then `cd` into the forked bcc repo and
run any experiments you'd like with this tooling and various options,
hitting ctrl-C to terminate, e.g.,
```
sudo python3 ./tools/execsnoop.py -z
XXX sudo ./stackcount-bpfcc -i 1 -z ip_output | python3 loader.py
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

This query computes the unique set of stacks grouped by the parent caller
of the traced function (in this case `ip_output`):
```
zapi query -Z "from bpf | stacks:=union(stack) by callee:=stack[1] | len(stacks)==2"
```
where we filtered by the length of the stacks to get just this one record
(for this particular data set), giving
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

I set up tooling on my Mac with VirtualBox but a similar pattern should work on
other systems or native linux instances.

I adjusted a few things from [the instructions here](https://codeboten.medium.com/bpf-experiments-on-macos-9ad0cf21ea83),
mainly to use a newer version of Ubuntu Hirsute (21.04)
along with the more up-to-date BPF tooling referencing in
[BCC issue #2678](https://github.com/iovisor/bcc/issues/2678#issuecomment-883203478).
More details on the Ubuntu PPA are
[here](https://chabik.com/2021/09/ppas-update/).


> With this approach, I was able to
> [fork the BCC repo](https://github.com/brimdata/bcc),
> run the latest BCC tooling in this newer Ubuntu, and
> make the modifications described here.

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
You need version `v0.33` or later.

Finally, clone our fork of the [bcc repo]() into your linux host so you can
run Zed-emabled BCC tooling...
```
git clone https://github.com/brimdata/bcc
```

For the Mac/vagrant setup described below, a port forwarding rule is defined
in [the Vagrantfile](./Vagrantfile) that forwards the host port 8098 to
the guest port 9867, which is the default port for the Zed lake.

that came with the `bpftracing` repo by adding the
"forwarded_port" rule below:
```
Vagrant.configure("2") do |config|
  ...
  config.vm.network "forwarded_port", guest: 9867, host: 8098
```
