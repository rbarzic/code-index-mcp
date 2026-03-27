"""Tests for C tree-sitter discovery and typedef indexing."""

from code_index_mcp.indexing.strategies.c_strategy import CParsingStrategy


def test_c_strategy_indexes_typedefs_functions_and_imports():
    strategy = CParsingStrategy()
    content = """
#include \"foo.h\"

typedef struct Device {
    int id;
} Device;

typedef unsigned int u32;

static int add(int a, int b);

int add(int a, int b) {
    return a + b;
}
"""

    symbols, file_info = strategy.parse_file("sample.c", content)

    assert "sample.c::Device" in symbols
    assert symbols["sample.c::Device"].type in {"typedef", "struct"}
    assert "sample.c::u32" in symbols
    assert symbols["sample.c::u32"].type == "typedef"
    assert "sample.c::add" in symbols
    assert symbols["sample.c::add"].type == "function"
    assert file_info.imports == ["foo.h"]


def test_c_strategy_indexes_header_typedef_and_prototype():
    strategy = CParsingStrategy()
    content = """
typedef enum Mode {
    MODE_A,
    MODE_B,
} Mode;

int run_mode(Mode mode);
"""

    symbols, file_info = strategy.parse_file("sample.h", content)

    assert "sample.h::Mode" in symbols
    assert symbols["sample.h::Mode"].type in {"typedef", "enum"}
    assert "sample.h::run_mode" in symbols
    assert symbols["sample.h::run_mode"].type == "function"
    assert "Mode" in file_info.symbols["classes"]
    assert "run_mode" in file_info.symbols["functions"]
