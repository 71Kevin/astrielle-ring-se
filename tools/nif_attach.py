"""AttachT for art-object NIFs (Skyrim SE, NIF 20.2.0.7, user 12, stream 100), which PyNifly cannot write.

An art object played on an actor (VisualEffect) moves the children of its root to the actor's node named in the root's
NiStringsExtraData "AttachT" ("NamedNode&<node name>"). The NIF is written by PyNifly with a NiStringExtraData named
"AttachT" whose value is also "AttachT" (so no extra header string is left behind); attach() rewrites that block in place
as the NiStringsExtraData the game reads.

python nif_attach.py <file.nif>      prints the blocks and every AttachT target
"""
import struct
import sys


class Nif:
    def __init__(self, path):
        self.path = path
        b = open(path, "rb").read()
        self.head_line = b[:b.index(b"\n") + 1]
        o = len(self.head_line)
        self.version, self.endian, self.user, n_blocks, self.stream = struct.unpack_from("<IBIII", b, o)
        assert (self.version, self.user, self.stream) == (0x14020007, 12, 100), "Skyrim SE NIF expected"
        o += 17
        self.export = []
        for _ in range(3):
            n = b[o]
            self.export.append(b[o + 1:o + 1 + n])
            o += 1 + n
        n_types = struct.unpack_from("<H", b, o)[0]
        o += 2
        self.types = []
        for _ in range(n_types):
            n = struct.unpack_from("<I", b, o)[0]
            self.types.append(b[o + 4:o + 4 + n].decode("latin-1"))
            o += 4 + n
        self.type_index = list(struct.unpack_from("<%dH" % n_blocks, b, o))
        o += 2 * n_blocks
        sizes = struct.unpack_from("<%dI" % n_blocks, b, o)
        o += 4 * n_blocks
        n_strings, self.max_len = struct.unpack_from("<II", b, o)
        o += 8
        self.strings = []
        for _ in range(n_strings):
            n = struct.unpack_from("<I", b, o)[0]
            self.strings.append(b[o + 4:o + 4 + n].decode("latin-1"))
            o += 4 + n
        n_groups = struct.unpack_from("<I", b, o)[0]
        self.groups = list(struct.unpack_from("<%dI" % n_groups, b, o + 4))
        o += 4 + 4 * n_groups
        self.blocks = []
        for s in sizes:
            self.blocks.append(b[o:o + s])
            o += s
        self.footer = b[o:]

    def block_type(self, i):
        return self.types[self.type_index[i]]

    def save(self, path=None):
        out = [self.head_line, struct.pack("<IBIII", self.version, self.endian, self.user, len(self.blocks), self.stream)]
        for e in self.export:
            out.append(bytes([len(e)]) + e)
        out.append(struct.pack("<H", len(self.types)))
        for t in self.types:
            out.append(struct.pack("<I", len(t)) + t.encode("latin-1"))
        out.append(struct.pack("<%dH" % len(self.blocks), *self.type_index))
        out.append(struct.pack("<%dI" % len(self.blocks), *[len(x) for x in self.blocks]))
        out.append(struct.pack("<II", len(self.strings), max(len(s) for s in self.strings)))
        for s in self.strings:
            out.append(struct.pack("<I", len(s)) + s.encode("latin-1"))
        out.append(struct.pack("<I", len(self.groups)) + struct.pack("<%dI" % len(self.groups), *self.groups))
        out.extend(self.blocks)
        out.append(self.footer)
        open(path or self.path, "wb").write(b"".join(out))

    def attach_targets(self):
        found = []
        for i, blk in enumerate(self.blocks):
            if self.block_type(i) == "NiStringsExtraData":
                name, count = struct.unpack_from("<iI", blk, 0)
                o, vals = 8, []
                for _ in range(count):
                    n = struct.unpack_from("<I", blk, o)[0]
                    vals.append(blk[o + 4:o + 4 + n].decode("latin-1"))
                    o += 4 + n
                found.append((i, self.strings[name] if name >= 0 else None, vals))
        return found


def attach(path, node):
    nif = Nif(path)
    key = nif.strings.index("AttachT")
    hits = [i for i, blk in enumerate(nif.blocks)
            if nif.block_type(i) == "NiStringExtraData" and struct.unpack_from("<ii", blk, 0) == (key, key)]
    assert len(hits) == 1, "one NiStringExtraData AttachT=AttachT expected"
    i = hits[0]
    value = ("NamedNode&" + node).encode("latin-1")
    if "NiStringsExtraData" not in nif.types:
        nif.types.append("NiStringsExtraData")
    old_type = nif.type_index[i]
    nif.type_index[i] = nif.types.index("NiStringsExtraData")
    nif.blocks[i] = struct.pack("<iII", key, 1, len(value)) + value
    if old_type not in nif.type_index:
        nif.types.pop(old_type)
        nif.type_index = [t - 1 if t > old_type else t for t in nif.type_index]
    nif.save()
    return Nif(path).attach_targets()


if __name__ == "__main__":
    n = Nif(sys.argv[1])
    for i in range(len(n.blocks)):
        print(i, n.block_type(i), len(n.blocks[i]))
    print("AttachT", n.attach_targets())
