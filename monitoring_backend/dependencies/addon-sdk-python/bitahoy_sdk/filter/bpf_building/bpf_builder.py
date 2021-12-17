import asyncio
import struct
import tempfile
import sys

FILENAME = "bpfcode.c"
REPLACEMENT = "BPFBALLERN"


async def get_bpf_bytecode_from_c(bpf_filter: str):
    with open("xdp_filter.c") as f:
        template = f.read()
    with tempfile.TemporaryDirectory() as tmpdirname:
        filename = tmpdirname + "/" + FILENAME
        with open(filename, "w") as f:
            f.write(template.replace(REPLACEMENT, bpf_filter))
        clang_arg = (
            """clang -S
        -target bpf
        -D __BPF_TRACING__
        -Wall
        -Wno-unused-value
        -Wno-pointer-sign
        -Wno-compare-distinct-pointer-types
        -I .
        -O2 -emit-llvm -c -g -o {}ll {}
        """.format(
                filename[:-1], filename
            )
            .replace("\n", " ")
            .split(" ")
        )
        clang_arg = [e for e in clang_arg if e]
        clang = await asyncio.create_subprocess_exec(*clang_arg)
        await clang.wait()
        llc_arg = (
            """llc
        -march=bpf
        -filetype=obj
        -o {}o
        {}ll
        """.format(
                filename[:-1], filename[:-1]
            )
            .replace("\n", " ")
            .split(" ")
        )
        llc_arg = [e for e in llc_arg if e]
        llc = await asyncio.create_subprocess_exec(*llc_arg)
        await llc.wait()
        copy_arg = ("cp " + filename[:-1] + "o /tmp").split(" ")
        copy = await asyncio.create_subprocess_exec(*copy_arg)
        await copy.wait()
        return "/tmp/bpfcode.o"  # nosec


async def get_bpf_bytecode_from_tcpdump(bpf_filter: str) -> bytes:
    tcpdump_args = ["tcpdump", "-ddd", bpf_filter]
    tcpdump = await asyncio.create_subprocess_exec(
        *tcpdump_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await tcpdump.communicate()
    if stderr:
        print(b"tcpdump threw: " + stderr + b" for filter " + bpf_filter.encode('ascii'), file=sys.stderr)
    if tcpdump.returncode != 0:
        raise ValueError(b"tcpdump returned with exit code " + str(tcpdump.returncode).encode() + b": " + stderr + b" for filter " + bpf_filter.encode('ascii'))
    if not stdout:
        raise ValueError(b"tcpdump did not return anything for " + bpf_filter)
    code = b""
    for lineno, line in enumerate(stdout.split(b"\n")[:-1]):
        if lineno == 0:
            # tcpdump gives you the length of instructions which we don't need
            continue
        instructions = line.split(b" ")
        # hotpach return value to -1 compared to tcpdumps default val
        """
        from https://www.kernel.org/doc/html/latest/networking/filter.html
        struct sock_filter {    /* Filter block */
        __u16   code;   /* Actual filter code */
        __u8    jt;     /* Jump true */
        __u8    jf;     /* Jump false */
        __u32   k;      /* Generic multiuse field */
        };      
        """
        if instructions[0] == b"6" and instructions[1] == instructions[2] == b"0" and instructions[3] == b"262144":
            instructions[3] = b"4294967295"
        code += (
            struct.pack("HBBI", int(instructions[0]), int(instructions[1]), int(instructions[2]), int(instructions[3]))
        )

    return code
