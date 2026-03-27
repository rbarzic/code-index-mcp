"""C parsing strategy using tree-sitter."""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional, Set, Tuple

import tree_sitter
from tree_sitter_c import language

from .base_strategy import ParsingStrategy
from ..models import FileInfo, SymbolInfo

logger = logging.getLogger(__name__)


class CParsingStrategy(ParsingStrategy):
    """C-specific parsing strategy using tree-sitter."""

    _TYPE_KINDS = {
        "struct_specifier": "struct",
        "union_specifier": "union",
        "enum_specifier": "enum",
    }

    def __init__(self) -> None:
        self.c_language = tree_sitter.Language(language())
        self._parser_local = threading.local()

    def _get_parser(self) -> tree_sitter.Parser:
        parser = getattr(self._parser_local, "parser", None)
        if parser is None:
            parser = tree_sitter.Parser(self.c_language)
            self._parser_local.parser = parser
        return parser

    def get_language_name(self) -> str:
        return "c"

    def get_supported_extensions(self) -> List[str]:
        return [".c", ".h"]

    def parse_file(
        self, file_path: str, content: str
    ) -> Tuple[Dict[str, SymbolInfo], FileInfo]:
        """Parse C file using tree-sitter."""
        symbols: Dict[str, SymbolInfo] = {}
        functions: List[str] = []
        classes: List[str] = []
        imports: List[str] = []
        symbol_lookup: Dict[str, str] = {}
        pending_calls: List[Tuple[str, str]] = []
        pending_call_set: Set[Tuple[str, str]] = set()
        content_bytes = content.encode("utf8")

        try:
            tree = self._get_parser().parse(content_bytes)
        except Exception as exc:  # pragma: no cover
            logger.warning("Error parsing C file %s: %s", file_path, exc)
            return symbols, FileInfo(
                language=self.get_language_name(),
                line_count=len(content.splitlines()),
                symbols={"functions": functions, "classes": classes},
                imports=imports,
            )

        self._traverse_node(
            tree.root_node,
            file_path,
            content,
            symbols,
            functions,
            classes,
            imports,
            symbol_lookup,
            pending_calls,
            pending_call_set,
            None,
        )

        self._resolve_pending_calls(symbols, symbol_lookup, pending_calls)

        file_info = FileInfo(
            language=self.get_language_name(),
            line_count=len(content.splitlines()),
            symbols={"functions": functions, "classes": classes},
            imports=imports,
        )
        if pending_calls:
            file_info.pending_calls = pending_calls
        return symbols, file_info

    def _traverse_node(
        self,
        node,
        file_path: str,
        content: str,
        symbols: Dict[str, SymbolInfo],
        functions: List[str],
        classes: List[str],
        imports: List[str],
        symbol_lookup: Dict[str, str],
        pending_calls: List[Tuple[str, str]],
        pending_call_set: Set[Tuple[str, str]],
        current_function: Optional[str],
    ) -> None:
        node_type = node.type

        if node_type == "preproc_include":
            include_name = self._extract_include(node, content)
            if include_name and include_name not in imports:
                imports.append(include_name)
            return

        if node_type in {"preproc_def", "preproc_function_def"}:
            macro_name = self._extract_macro_name(node, content)
            if macro_name:
                self._register_symbol(
                    symbols,
                    classes,
                    symbol_lookup,
                    file_path,
                    macro_name,
                    "macro",
                    node,
                    self._node_text(node, content),
                )
            return

        if node_type == "function_definition":
            name = self._extract_function_name(node, content)
            if name:
                symbol_id = self._register_symbol(
                    symbols,
                    functions,
                    symbol_lookup,
                    file_path,
                    name,
                    "function",
                    node,
                    self._node_text(node, content),
                )
                for child in node.children:
                    self._traverse_node(
                        child,
                        file_path,
                        content,
                        symbols,
                        functions,
                        classes,
                        imports,
                        symbol_lookup,
                        pending_calls,
                        pending_call_set,
                        symbol_id,
                    )
            return

        if node_type == "call_expression" and current_function:
            called_name = self._extract_call_name(node, content)
            if called_name:
                self._record_call(
                    symbols,
                    symbol_lookup,
                    pending_calls,
                    pending_call_set,
                    current_function,
                    called_name,
                )

        if node_type == "type_definition":
            self._handle_type_definition(
                node,
                file_path,
                content,
                symbols,
                classes,
                symbol_lookup,
            )
            return

        if node_type == "declaration":
            self._handle_declaration(
                node,
                file_path,
                content,
                symbols,
                functions,
                classes,
                symbol_lookup,
            )
            return

        if node_type in self._TYPE_KINDS:
            type_name = self._extract_type_name(node, content)
            if type_name:
                self._register_symbol(
                    symbols,
                    classes,
                    symbol_lookup,
                    file_path,
                    type_name,
                    self._TYPE_KINDS[node_type],
                    node,
                    self._node_text(node, content),
                )
            return

        for child in node.children:
            self._traverse_node(
                child,
                file_path,
                content,
                symbols,
                functions,
                classes,
                imports,
                symbol_lookup,
                pending_calls,
                pending_call_set,
                current_function,
            )

    def _handle_declaration(
        self,
        node,
        file_path: str,
        content: str,
        symbols: Dict[str, SymbolInfo],
        functions: List[str],
        classes: List[str],
        symbol_lookup: Dict[str, str],
    ) -> None:
        if self._has_storage_class(node, content, "typedef"):
            typedef_names = self._extract_typedef_names(node, content)
            for typedef_name in typedef_names:
                self._register_symbol(
                    symbols,
                    classes,
                    symbol_lookup,
                    file_path,
                    typedef_name,
                    "typedef",
                    node,
                    self._node_text(node, content),
                )

        declarator = node.child_by_field_name("declarator")
        if declarator and self._contains_function_declarator(declarator):
            function_name = self._extract_declarator_name(declarator, content)
            if function_name:
                self._register_symbol(
                    symbols,
                    functions,
                    symbol_lookup,
                    file_path,
                    function_name,
                    "function",
                    node,
                    self._node_text(node, content),
                )

        for child in node.children:
            if child.type in self._TYPE_KINDS:
                type_name = self._extract_type_name(child, content)
                if type_name:
                    self._register_symbol(
                        symbols,
                        classes,
                        symbol_lookup,
                        file_path,
                        type_name,
                        self._TYPE_KINDS[child.type],
                        child,
                        self._node_text(child, content),
                    )

    def _handle_type_definition(
        self,
        node,
        file_path: str,
        content: str,
        symbols: Dict[str, SymbolInfo],
        classes: List[str],
        symbol_lookup: Dict[str, str],
    ) -> None:
        typedef_names = self._extract_typedef_names(node, content)
        for typedef_name in typedef_names:
            self._register_symbol(
                symbols,
                classes,
                symbol_lookup,
                file_path,
                typedef_name,
                "typedef",
                node,
                self._node_text(node, content),
            )

        for child in node.children:
            if child.type in self._TYPE_KINDS:
                type_name = self._extract_type_name(child, content)
                if type_name:
                    self._register_symbol(
                        symbols,
                        classes,
                        symbol_lookup,
                        file_path,
                        type_name,
                        self._TYPE_KINDS[child.type],
                        child,
                        self._node_text(child, content),
                    )

    def _register_symbol(
        self,
        symbols: Dict[str, SymbolInfo],
        bucket: List[str],
        symbol_lookup: Dict[str, str],
        file_path: str,
        name: str,
        symbol_type: str,
        node,
        signature: str,
    ) -> str:
        symbol_id = self._create_symbol_id(file_path, name)
        if symbol_id in symbols:
            return symbol_id
        symbols[symbol_id] = SymbolInfo(
            type=symbol_type,
            file=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature,
        )
        bucket.append(name)
        symbol_lookup[name] = symbol_id
        return symbol_id

    def _extract_typedef_names(self, node, content: str) -> List[str]:
        names: List[str] = []
        declarator = node.child_by_field_name("declarator")
        if declarator:
            name = self._extract_declarator_name(declarator, content)
            if name:
                names.append(name)

        for child in node.children:
            if child.type == "type_identifier":
                name = self._node_text(child, content)
                if name and name not in names:
                    names.append(name)
            if child.type == "init_declarator":
                declarator_child = child.child_by_field_name("declarator")
                name = self._extract_declarator_name(declarator_child, content)
                if name:
                    names.append(name)

        return names

    def _extract_function_name(self, node, content: str) -> Optional[str]:
        declarator = node.child_by_field_name("declarator")
        return self._extract_declarator_name(declarator, content)

    def _extract_declarator_name(self, node, content: str) -> Optional[str]:
        if node is None:
            return None
        if node.type == "identifier":
            return self._node_text(node, content)

        name_field = node.child_by_field_name("declarator")
        if name_field is not None:
            nested = self._extract_declarator_name(name_field, content)
            if nested:
                return nested

        for child in node.children:
            nested = self._extract_declarator_name(child, content)
            if nested:
                return nested

        return None

    def _extract_type_name(self, node, content: str) -> Optional[str]:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return self._node_text(name_node, content)
        return None

    def _contains_function_declarator(self, node) -> bool:
        if node is None:
            return False
        if node.type == "function_declarator":
            return True
        return any(self._contains_function_declarator(child) for child in node.children)

    def _has_storage_class(self, node, content: str, keyword: str) -> bool:
        for child in node.children:
            if (
                child.type == "storage_class_specifier"
                and self._node_text(child, content) == keyword
            ):
                return True
        return False

    def _extract_include(self, node, content: str) -> Optional[str]:
        path_node = node.child_by_field_name("path")
        if path_node is None:
            for child in node.children:
                if child.type in {"system_lib_string", "string_literal"}:
                    path_node = child
                    break
        if path_node is None:
            return None
        return self._node_text(path_node, content).strip('"<>')

    def _extract_macro_name(self, node, content: str) -> Optional[str]:
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child, content)
        return None

    def _extract_call_name(self, node, content: str) -> Optional[str]:
        function_node = node.child_by_field_name("function")
        if function_node is None and node.children:
            function_node = node.children[0]
        return self._extract_declarator_name(function_node, content)

    def _record_call(
        self,
        symbols: Dict[str, SymbolInfo],
        symbol_lookup: Dict[str, str],
        pending_calls: List[Tuple[str, str]],
        pending_call_set: Set[Tuple[str, str]],
        caller: str,
        called_name: str,
    ) -> None:
        symbol_id = symbol_lookup.get(called_name)
        if symbol_id:
            symbol_info = symbols.get(symbol_id)
            if symbol_info and caller not in symbol_info.called_by:
                symbol_info.called_by.append(caller)
            return

        key = (caller, called_name)
        if key not in pending_call_set:
            pending_calls.append(key)
            pending_call_set.add(key)

    def _resolve_pending_calls(
        self,
        symbols: Dict[str, SymbolInfo],
        symbol_lookup: Dict[str, str],
        pending_calls: List[Tuple[str, str]],
    ) -> None:
        remaining: List[Tuple[str, str]] = []
        for caller, called_name in pending_calls:
            symbol_id = symbol_lookup.get(called_name)
            symbol_info = symbols.get(symbol_id) if symbol_id else None
            if symbol_info:
                if caller not in symbol_info.called_by:
                    symbol_info.called_by.append(caller)
            else:
                remaining.append((caller, called_name))
        pending_calls[:] = remaining

    @staticmethod
    def _node_text(node, content: str) -> str:
        return content[node.start_byte : node.end_byte].strip()
