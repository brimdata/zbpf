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
> that uses Python2.  If we take a more serious stab at this project, we'll
> make it all work with the latest versions of BPF tooling.

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
(note `loader.py` has pool "bpf" hardwired.)

Then run any experiments you'd like with this tooling and various options,
hitting ctrl-C to terminate, e.g.,
```
sudo ./execsnoop-bpfcc | python3 loader.py
sudo ./stackcount-bpfcc -i 1 -z ip_output | python3 loader.py
```
 Now, look at the data in the pool with `zapi query`:
```
zapi use -p bpf
zapi query -Z "sum(count) by stack,name | sort sum"
```

## The Brim App

The Brim app is a nice way to look at Zed data.  It's a desktop app based on
Electron, similar to Slack's model.

For my Mac/vagrant setup, I configured a port forwarding rule in the
Vagrantfile that came with the `bpftracing` repo by adding the
"forwarded_port" rule below:
```
Vagrant.configure("2") do |config|
  ...
  config.vm.network "forwarded_port", guest: 9867, host: 8098
```
Then, in the Brim app, I added a lake connection to `localhost:8098`.

## Sample Output

With your BPF trace data in a Zed lake, searching and analyzing your data
is a piece of cake.  You can also slice and dice the data in the lake
and export it in most any format you'd like (JSON, Parquet, CSV, or any Zed format).

First make sure zapi query uses the "bpf" pool for your queries by running
```
zapi use bpf@main
```

Here is a simple query that counts the number of times the
identifier `__tcp_transmit_skb` appears in a stack trace (from `stackcount-bpfcc`)
```
zapi query '"__tcp_transmit_skb" in kernel | count()'
```
and you'll get a result that looks like this as the default format is ZSON:
```
{count:650(uint64)}
```
If you want JSON, just add `-f json`:
```
% zapi query -f json '"__tcp_transmit_skb" in stack | count()'
{"count":650}
```
Here is a more sophisticated query where we sum up the counts from every
1 second sampling intervel and we use the "stack" and the process "name"
as group-by keys.  Note that the Zed query language is perfectly happy using
any Zed value (including arrays) as a group-by key.
```
zapi query -Z "from bpf | sum(count) by stack,name | sort -r sum | head 2"
```
This will give the top two stack traces and will look something like this
in the pretty-printed (-Z) ZSON output:
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

Zed it a bit different and lets you put super-structured data all in one
location.  It's kind of like rich database tables without having to define
tables and schemas ahead of time.  That sounds like NoSQL stores like Mongo
or CouchDB but Zed is quite different because it is super-structured
instead of semi-structured.
Super-structured data has a well-defined type for every value whereas semi-structured
data has implied types and the "shape" of a semi-structured data value can only be
determined by traversing that value.

The power of super-structured data types and Zed is that type are first class.
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
