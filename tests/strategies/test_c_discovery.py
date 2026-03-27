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


def test_c_strategy_indexes_macros():
    strategy = CParsingStrategy()
    content = """
#define MAX_COUNT 32
#define SQR(x) ((x) * (x))
"""

    symbols, file_info = strategy.parse_file("macros.h", content)

    assert "macros.h::MAX_COUNT" in symbols
    assert symbols["macros.h::MAX_COUNT"].type == "macro"
    assert "macros.h::SQR" in symbols
    assert symbols["macros.h::SQR"].type == "macro"
    assert "MAX_COUNT" in file_info.symbols["classes"]
    assert "SQR" in file_info.symbols["classes"]


def test_c_strategy_tracks_function_call_relationships():
    strategy = CParsingStrategy()
    content = """
int helper(void) {
    return 1;
}

int run(void) {
    return helper();
}
"""

    symbols, file_info = strategy.parse_file("calls.c", content)

    assert "calls.c::helper" in symbols
    assert "calls.c::run" in symbols
    assert symbols["calls.c::helper"].called_by == ["calls.c::run"]
    assert not hasattr(file_info, "pending_calls") or file_info.pending_calls == []
