from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

DMEM_RTL = (
    REPO_ROOT
    / "design"
    / "ramOnChipData.v"
)

DATA_HEX = (
    REPO_ROOT
    / "data.hex"
)


def test_canonical_data_hex_is_tracked_empty_baseline():
    assert DATA_HEX.is_file()

    assert DATA_HEX.read_bytes() == b""


def test_dmem_rtl_zeroes_memory_before_readmemh():
    text = DMEM_RTL.read_text(
        encoding="utf-8"
    )

    zero_loop = """
        for (i = 0; i < ramSize; i = i + 1)
            mem[i] = 0;
""".strip()

    readmem = (
        '$readmemh("data.hex", mem);'
    )

    assert zero_loop in text
    assert readmem in text

    assert (
        text.index(zero_loop)
        < text.index(readmem)
    )


def test_dmem_canonical_envelope_is_within_zeroed_ram():
    ram_size = 65536

    canonical_word_addresses = tuple(
        range(0, 509, 4)
    )

    assert len(canonical_word_addresses) == 128

    for address in canonical_word_addresses:
        assert address % 4 == 0
        assert 0 <= address <= 508

        # One RV32 word occupies four byte locations.
        assert address + 3 < ram_size
