"""Symbol table implementation for NOS.

Provides scoped symbol storage with parent chain lookup,
supporting nested scopes for packages, nodes, and callbacks.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum, auto


class SymbolType(Enum):
    """Types of symbols in the symbol table."""
    PACKAGE = auto()
    NODE = auto()
    PARAMETER = auto()
    SUBSCRIPTION = auto()
    PUBLICATION = auto()
    SERVICE = auto()
    ACTION = auto()
    CALLBACK = auto()
    COMPONENT = auto()
    TYPE = auto()
    VARIABLE = auto()
    LAUNCH = auto()
    ARGUMENT = auto()


@dataclass
class Symbol:
    """Represents a symbol in the symbol table.

    Attributes:
        name: The symbol name
        symbol_type: The type of symbol
        node: Reference to the AST node that declared this symbol
        scope: The scope containing this symbol
        type_info: Optional type information
        is_exported: Whether this symbol is visible outside its scope
    """
    name: str
    symbol_type: SymbolType
    node: Any  # ASTNode
    scope: 'Scope'
    type_info: Optional[Any] = None
    is_exported: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash((self.name, self.scope.name, id(self.node)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Symbol):
            return NotImplemented
        return (self.name == other.name and
                self.scope.name == other.scope.name and
                self.node is other.node)


class Scope:
    """Represents a scope in the symbol table.

    Scopes form a tree structure with parent pointers for
    lexical scope resolution.
    """

    def __init__(self, name: str, parent: Optional['Scope'] = None,
                 scope_type: str = "block"):
        self.name = name
        self.parent = parent
        self.scope_type = scope_type
        self.symbols: Dict[str, Symbol] = {}
        self.children: List['Scope'] = []
        if parent:
            parent.children.append(self)

    def lookup(self, name: str) -> Optional[Symbol]:
        """Lookup a symbol by name.

        Searches current scope, then parent scopes up the chain.

        Args:
            name: The symbol name to look up

        Returns:
            The symbol if found, None otherwise
        """
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def lookup_local(self, name: str) -> Optional[Symbol]:
        """Lookup a symbol in this scope only.

        Args:
            name: The symbol name to look up

        Returns:
            The symbol if found in this scope, None otherwise
        """
        return self.symbols.get(name)

    def define(self, symbol: Symbol) -> bool:
        """Define a symbol in this scope.

        Args:
            symbol: The symbol to define

        Returns:
            True if successfully defined, False if name already exists
        """
        if symbol.name in self.symbols:
            return False
        self.symbols[symbol.name] = symbol
        return True

    def remove(self, name: str) -> bool:
        """Remove a symbol from this scope.

        Args:
            name: The symbol name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self.symbols:
            del self.symbols[name]
            return True
        return False

    def get_all_symbols(self) -> List[Symbol]:
        """Get all symbols defined in this scope."""
        return list(self.symbols.values())

    def get_path(self) -> str:
        """Get the scope path (e.g., 'package::node::callback')."""
        if self.parent:
            return f"{self.parent.get_path()}::{self.name}"
        return self.name

    def __repr__(self) -> str:
        return f"Scope({self.get_path()})"


class SymbolTable:
    """Manages all scopes and symbols for a compilation unit.

    Provides convenient access to global and current scopes,
    and tracks all scopes for post-analysis.
    """

    def __init__(self):
        self.global_scope = Scope("global", None, "global")
        self.current_scope = self.global_scope
        self.all_scopes: List[Scope] = [self.global_scope]

    def push_scope(self, name: str, scope_type: str = "block") -> Scope:
        """Create and enter a new scope, or enter an existing one.

        Args:
            name: The scope name
            scope_type: The scope type (package, node, callback, block)

        Returns:
            The scope
        """
        # Check if scope already exists in children
        for child in self.current_scope.children:
            if child.name == name and child.scope_type == scope_type:
                self.current_scope = child
                return child

        new_scope = Scope(name, self.current_scope, scope_type)
        self.current_scope = new_scope
        self.all_scopes.append(new_scope)
        return new_scope

    def pop_scope(self) -> Optional[Scope]:
        """Exit the current scope and return to parent.

        Returns:
            The parent scope, or None if already at global
        """
        if self.current_scope.parent:
            self.current_scope = self.current_scope.parent
            return self.current_scope
        return None

    def lookup(self, name: str) -> Optional[Symbol]:
        """Lookup a symbol in the current scope chain."""
        return self.current_scope.lookup(name)

    def lookup_global(self, name: str) -> Optional[Symbol]:
        """Lookup a symbol in the global scope only."""
        return self.global_scope.lookup_local(name)

    def define(self, symbol: Symbol) -> bool:
        """Define a symbol in the current scope."""
        return self.current_scope.define(symbol)

    def get_all_symbols(self) -> List[Symbol]:
        """Get all symbols from all scopes."""
        symbols = []
        for scope in self.all_scopes:
            symbols.extend(scope.get_all_symbols())
        return symbols

    def find_by_type(self, symbol_type: SymbolType) -> List[Symbol]:
        """Find all symbols of a given type."""
        return [s for s in self.get_all_symbols() if s.symbol_type == symbol_type]

    def find_nodes(self) -> List[Symbol]:
        """Find all node symbols."""
        return self.find_by_type(SymbolType.NODE)

    def find_parameters(self, node_name: Optional[str] = None) -> List[Symbol]:
        """Find all parameter symbols, optionally filtered by node."""
        params = self.find_by_type(SymbolType.PARAMETER)
        if node_name:
            params = [p for p in params
                     if p.scope.name == node_name]
        return params

    def __repr__(self) -> str:
        return f"SymbolTable({len(self.all_scopes)} scopes, {len(self.get_all_symbols())} symbols)"
