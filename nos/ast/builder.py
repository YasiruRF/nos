"""AST Builder - converts ANTLR4 parse trees to AST nodes.

This module provides the bridge between the ANTLR4 parser output
and the strongly-typed AST node hierarchy.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from . import nodes

logger = logging.getLogger(__name__)

INTERFACE_KINDS = ("msg", "srv", "action")


class ASTBuilder:
    """Builds AST from ANTLR4 parse tree.

    Usage:
        parser = NOSParser(CommonTokenStream(...))
        tree = parser.nosFile()
        builder = ASTBuilder(file_name="example.node")
        ast = builder.visit(tree)
    """

    def __init__(self, file_name: str = "<input>"):
        self.file_name = file_name
        # User-facing problems found while building ("file:line:col: error: ...")
        self.errors: List[str] = []

    def _error(self, ctx, message: str) -> None:
        """Record a source error at ``ctx``."""
        loc = self._loc(ctx)
        self.errors.append(f"{loc}: error: {message}")

    def _fallback(self, ctx, message: str) -> None:
        """Log (at debug level) that the builder substituted a default."""
        logger.debug("%s: %s", self._loc(ctx), message)

    def _loc(self, ctx) -> nodes.SourceLocation:
        """Create source location from ANTLR context."""
        if ctx is None or not hasattr(ctx, "start") or ctx.start is None:
            return nodes.SourceLocation(line=0, column=0, file=self.file_name)
        return nodes.SourceLocation(line=ctx.start.line, column=ctx.start.column, file=self.file_name)

    def visit(self, ctx) -> Optional[nodes.ASTNode]:
        """Visit a parse tree node and return AST node."""
        if ctx is None:
            return None

        method_name = f'visit_{ctx.__class__.__name__.replace("Context", "")}'
        method = getattr(self, method_name, self.visit_default)
        return method(ctx)

    def visit_default(self, ctx) -> None:
        """Default handler for unvisited nodes."""
        self._fallback(ctx, f"no AST handler for {ctx.__class__.__name__}")
        return None

    def visit_children(self, ctx) -> List[nodes.ASTNode]:
        """Visit all children and return AST nodes."""
        results = []
        if hasattr(ctx, "children") and ctx.children:
            for child in ctx.children:
                if child is not None:
                    result = self.visit(child)
                    if result:
                        results.append(result)
        return results

    # ==========================================================================
    # Entry Points
    # ==========================================================================

    def visit_NosFile(self, ctx) -> nodes.File:
        """Visit NOS file root."""
        package = None
        imports = []
        declarations = []

        # Visit package declaration if present
        if hasattr(ctx, "packageDecl") and callable(ctx.packageDecl):
            pkg_ctx = ctx.packageDecl()
            if pkg_ctx:
                package = self.visit(pkg_ctx)

        # Visit import declarations
        if hasattr(ctx, "importDecl") and callable(ctx.importDecl):
            for import_ctx in ctx.importDecl():
                if import_ctx:
                    imp = self.visit(import_ctx)
                    if imp:
                        imports.append(imp)

        # Visit all declarations (node, launch, interface)
        if hasattr(ctx, "children") and ctx.children:
            for child in ctx.children:
                if child is None:
                    continue
                class_name = child.__class__.__name__
                # Skip package, imports, EOF, and terminal nodes
                if "Decl" in class_name and "Import" not in class_name:
                    node = self.visit(child)
                    if node:
                        declarations.append(node)
                elif (
                    "node" in class_name.lower() or "launch" in class_name.lower() or "interface" in class_name.lower()
                ):
                    node = self.visit(child)
                    if node:
                        declarations.append(node)

        return nodes.File(location=self._loc(ctx), package=package, imports=imports, declarations=declarations)

    # Alias for compatibility
    visit_File = visit_NosFile

    # ==========================================================================
    # Package and Imports
    # ==========================================================================

    def visit_PackageDecl(self, ctx) -> nodes.PackageDecl:
        """Visit package declaration: package robot_navigation version '1.0.0'"""
        name = ""
        version = None
        dependencies = []

        # Get identifier
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        # Get version
        if hasattr(ctx, "version") and callable(ctx.version):
            ver_ctx = ctx.version()
            if ver_ctx and hasattr(ver_ctx, "STRING_LITERAL"):
                str_lit = ver_ctx.STRING_LITERAL()
                if str_lit:
                    version = self._strip_quotes(str_lit.getText())

        # Get dependencies
        if hasattr(ctx, "depends") and callable(ctx.depends):
            deps_ctx = ctx.depends()
            if deps_ctx and hasattr(deps_ctx, "STRING_LITERAL"):
                for str_lit in deps_ctx.STRING_LITERAL():
                    if str_lit:
                        dependencies.append(self._strip_quotes(str_lit.getText()))

        return nodes.PackageDecl(location=self._loc(ctx), name=name, version=version, dependencies=dependencies)

    def visit_ImportDecl(self, ctx) -> nodes.ImportDecl:
        """Visit import declaration: import nav2::components as nav"""
        qualified_name = ""
        alias = None

        # Get qualified identifier
        if hasattr(ctx, "qualifiedIdentifier") and callable(ctx.qualifiedIdentifier):
            qi_ctx = ctx.qualifiedIdentifier()
            if qi_ctx:
                qualified_name = self.visit_QualifiedIdentifier(qi_ctx)

        # Get alias if present
        if hasattr(ctx, "AS") and ctx.AS() is not None:
            if hasattr(ctx, "identifier") and callable(ctx.identifier):
                id_ctx = ctx.identifier()
                if id_ctx:
                    alias = self._get_text(id_ctx)

        return nodes.ImportDecl(location=self._loc(ctx), qualified_name=qualified_name, alias=alias)

    # ==========================================================================
    # Type System
    # ==========================================================================

    def visit_PrimitiveType(self, ctx) -> nodes.PrimitiveType:
        """Visit primitive type: bool, int, float, string, etc."""
        text = self._get_text(ctx).lower()
        kind_map = {
            "bool": nodes.PrimitiveTypeKind.BOOL,
            "int": nodes.PrimitiveTypeKind.INT,
            "float": nodes.PrimitiveTypeKind.FLOAT,
            "double": nodes.PrimitiveTypeKind.DOUBLE,
            "string": nodes.PrimitiveTypeKind.STRING,
            "duration": nodes.PrimitiveTypeKind.DURATION,
            "time": nodes.PrimitiveTypeKind.TIME,
        }
        return nodes.PrimitiveType(location=self._loc(ctx), kind=kind_map.get(text, nodes.PrimitiveTypeKind.STRING))

    def visit_QualifiedIdentifier(self, ctx) -> str:
        """Visit qualified identifier and return string representation."""
        if ctx is None:
            return ""

        parts = []
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            for id_ctx in ctx.identifier():
                if id_ctx:
                    parts.append(self._get_text(id_ctx))
        return "::".join(parts) if parts else ""

    def visit_QualifiedType(self, ctx) -> nodes.QualifiedType:
        """Visit qualified type: sensor_msgs::LaserScan, sensor_msgs::msg::LaserScan"""
        qualified = (
            self.visit_QualifiedIdentifier(ctx.qualifiedIdentifier()) if hasattr(ctx, "qualifiedIdentifier") else ""
        )
        package, kind, name = self.split_qualified_type(qualified, ctx)

        return nodes.QualifiedType(location=self._loc(ctx), package=package, name=name, kind=kind)

    def _qualified_type_of(self, ctx) -> nodes.QualifiedType:
        """QualifiedType for a declaration whose ``qualifiedIdentifier`` is the interface type."""
        qi_ctx = ctx.qualifiedIdentifier() if hasattr(ctx, "qualifiedIdentifier") else None
        if not qi_ctx:
            return nodes.QualifiedType(location=self._loc(ctx), package="", name="")
        return self.visit_QualifiedType(ctx)

    def split_qualified_type(self, qualified: str, ctx=None):
        """Validate and split ``pkg::Type`` / ``pkg::msg::Type``.

        Returns ``(package, kind, name)``.  ``package`` is empty for an
        unqualified name.  Malformed names are reported through ``self.errors``.
        """
        parts = qualified.split("::") if qualified else []

        if not parts or any(not part for part in parts):
            self._error(ctx, f"malformed qualified type '{qualified}'")
            return "", None, parts[-1] if parts and parts[-1] else ""

        if len(parts) == 1:
            return "", None, parts[0]
        if len(parts) == 2:
            return parts[0], None, parts[1]
        if len(parts) == 3 and parts[1] in INTERFACE_KINDS:
            return parts[0], parts[1], parts[2]

        self._error(
            ctx,
            f"invalid qualified type '{qualified}': expected 'package::Type' or "
            f"'package::{{{'|'.join(INTERFACE_KINDS)}}}::Type'",
        )
        return parts[0], None, parts[-1]

    def visit_typeSpec(self, ctx) -> nodes.Type:
        """Visit type specification."""
        if ctx is None:
            return nodes.PrimitiveType(
                location=nodes.SourceLocation(0, 0, self.file_name), kind=nodes.PrimitiveTypeKind.STRING
            )

        # Check for primitive type
        if hasattr(ctx, "primitiveType") and callable(ctx.primitiveType):
            prim_ctx = ctx.primitiveType()
            if prim_ctx:
                return self.visit(prim_ctx)

        # Check for qualified identifier (custom type)
        if hasattr(ctx, "qualifiedIdentifier") and callable(ctx.qualifiedIdentifier):
            qi_ctx = ctx.qualifiedIdentifier()
            if qi_ctx:
                return self.visit_QualifiedType(ctx)

        # Check for list type
        if hasattr(ctx, "LIST") and ctx.LIST() is not None:
            element_type = None
            if hasattr(ctx, "typeSpec") and callable(ctx.typeSpec):
                # `list<T>` has exactly one nested typeSpec, which ANTLR returns
                # as a single context rather than a list.
                child_type = self._first(ctx.typeSpec())
                if child_type is not None:
                    element_type = self.visit_typeSpec(child_type)
            return nodes.ListType(location=self._loc(ctx), element_type=element_type)

        # Check for struct type
        if hasattr(ctx, "STRUCT") and ctx.STRUCT() is not None:
            fields = []
            if hasattr(ctx, "fieldDecl") and callable(ctx.fieldDecl):
                for field_ctx in ctx.fieldDecl():
                    if field_ctx:
                        field = self.visit(field_ctx)
                        if field:
                            fields.append(field)
            return nodes.StructType(location=self._loc(ctx), fields=fields)

        # Default fallback
        self._fallback(ctx, "unrecognised type specification, defaulting to string")
        return nodes.PrimitiveType(location=self._loc(ctx), kind=nodes.PrimitiveTypeKind.STRING)

    # Alias for compatibility
    visit_TypeSpec = visit_typeSpec

    def visit_FieldDecl(self, ctx) -> nodes.FieldDecl:
        """Visit field declaration in struct."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        type_ = None
        if hasattr(ctx, "typeSpec") and callable(ctx.typeSpec):
            ts_ctx = ctx.typeSpec()
            if ts_ctx:
                type_ = self.visit_typeSpec(ts_ctx)

        default = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                default = self.visit_expression(expr_ctx)

        return nodes.FieldDecl(location=self._loc(ctx), name=name, type=type_, default_value=default)

    # ==========================================================================
    # Expressions
    # ==========================================================================

    # ==========================================================================
    # Expressions
    # ==========================================================================

    def visit_expression(self, ctx) -> nodes.Expression:
        """Visit an expression.

        Every alternative of the ``expression`` rule is labeled in the grammar,
        so ``ctx`` is a labeled subclass (``AdditiveExprContext``, ...) and is
        dispatched to its own ``visit_<Label>`` method.
        """
        if ctx is None or not ctx.children:
            return None
        return self.visit(ctx)

    visit_Expression = visit_expression

    def visit_PrimaryExpr(self, ctx) -> nodes.Expression:
        return self.visit_primaryExpression(ctx.primaryExpression())

    def visit_MemberAccessExpr(self, ctx) -> nodes.Expression:
        obj = self.visit(ctx.expression())
        member = self._get_text(ctx.identifier())
        return nodes.MemberAccessExpression(location=self._loc(ctx), object=obj, member=member)

    def visit_IndexExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        return nodes.IndexExpression(location=self._loc(ctx), array=self.visit(exprs[0]), index=self.visit(exprs[1]))

    def visit_CallExpr(self, ctx) -> nodes.Expression:
        callee = self.visit(ctx.expression())
        args = []
        if ctx.argumentList():
            for arg_ctx in ctx.argumentList().argument():
                args.append(self.visit(arg_ctx.expression()))
        return nodes.CallExpression(location=self._loc(ctx), callee=callee, arguments=args)

    def visit_InterpolatedExpr(self, ctx) -> nodes.Expression:
        return nodes.InterpolatedExpression(location=self._loc(ctx), inner=self.visit(ctx.expression()))

    def visit_UnaryExpr(self, ctx) -> nodes.Expression:
        return nodes.UnaryExpression(location=self._loc(ctx), operator="!", operand=self.visit(ctx.expression()))

    def visit_MultiplicativeExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        op = "*"
        for child in ctx.children:
            if child.getText() in ("*", "/", "%"):
                op = child.getText()
                break
        return nodes.BinaryExpression(
            location=self._loc(ctx), operator=op, left=self.visit(exprs[0]), right=self.visit(exprs[1])
        )

    def visit_AdditiveExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        op = "+"
        for child in ctx.children:
            if child.getText() in ("+", "-"):
                op = child.getText()
                break
        return nodes.BinaryExpression(
            location=self._loc(ctx), operator=op, left=self.visit(exprs[0]), right=self.visit(exprs[1])
        )

    def visit_RelationalExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        op = "<"
        for child in ctx.children:
            t = child.getText()
            if t in ("<", ">", "<=", ">=", "==", "!="):
                op = t
                break
        return nodes.BinaryExpression(
            location=self._loc(ctx), operator=op, left=self.visit(exprs[0]), right=self.visit(exprs[1])
        )

    def visit_LogicalAndExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        return nodes.BinaryExpression(
            location=self._loc(ctx), operator="&&", left=self.visit(exprs[0]), right=self.visit(exprs[1])
        )

    def visit_LogicalOrExpr(self, ctx) -> nodes.Expression:
        exprs = ctx.expression()
        return nodes.BinaryExpression(
            location=self._loc(ctx), operator="||", left=self.visit(exprs[0]), right=self.visit(exprs[1])
        )

    def visit_primaryExpression(self, ctx) -> nodes.Expression:
        """Visit primary expression."""
        if ctx is None:
            return nodes.LiteralExpression(
                location=nodes.SourceLocation(0, 0, self.file_name), value=None, literal_type="null"
            )

        # Handle literal
        if hasattr(ctx, "literal") and callable(ctx.literal) and ctx.literal():
            return self.visit_literal(ctx.literal())

        # Handle identifier
        if hasattr(ctx, "identifier") and callable(ctx.identifier) and ctx.identifier():
            name = self._get_text(ctx.identifier())
            return nodes.IdentifierExpression(location=self._loc(ctx), name=name)

        # Handle parenthesized expression
        if hasattr(ctx, "expression") and callable(ctx.expression) and ctx.expression():
            return self.visit(ctx.expression())

        text = self._get_text(ctx)
        return nodes.IdentifierExpression(location=self._loc(ctx), name=text)

    visit_PrimaryExpression = visit_primaryExpression

    def visit_literal(self, ctx) -> nodes.LiteralExpression:
        """Visit literal value."""
        if ctx is None:
            return nodes.LiteralExpression(
                location=nodes.SourceLocation(0, 0, self.file_name), value=None, literal_type="null"
            )

        text = self._get_text(ctx)

        if hasattr(ctx, "INT_LITERAL") and ctx.INT_LITERAL() is not None:
            return nodes.LiteralExpression(
                location=self._loc(ctx), value=int(ctx.INT_LITERAL().getText()), literal_type="int"
            )

        if hasattr(ctx, "FLOAT_LITERAL") and ctx.FLOAT_LITERAL() is not None:
            return nodes.LiteralExpression(
                location=self._loc(ctx), value=float(ctx.FLOAT_LITERAL().getText()), literal_type="float"
            )

        if hasattr(ctx, "STRING_LITERAL") and ctx.STRING_LITERAL() is not None:
            return nodes.LiteralExpression(
                location=self._loc(ctx), value=self._strip_quotes(ctx.STRING_LITERAL().getText()), literal_type="string"
            )

        if hasattr(ctx, "DURATION_LITERAL") and ctx.DURATION_LITERAL() is not None:
            return nodes.LiteralExpression(
                location=self._loc(ctx), value=ctx.DURATION_LITERAL().getText(), literal_type="duration"
            )

        if hasattr(ctx, "TRUE") and ctx.TRUE() is not None:
            return nodes.LiteralExpression(location=self._loc(ctx), value=True, literal_type="bool")

        if hasattr(ctx, "FALSE") and ctx.FALSE() is not None:
            return nodes.LiteralExpression(location=self._loc(ctx), value=False, literal_type="bool")

        if hasattr(ctx, "LBRACKET") and ctx.LBRACKET() is not None:
            el_ctx = ctx.expressionList()
            elements = [self.visit_expression(e) for e in (el_ctx.expression() if el_ctx else [])]
            return nodes.ArrayExpression(location=self._loc(ctx), elements=elements)

        if hasattr(ctx, "STRUCT") and ctx.STRUCT() is not None:
            fields = {}
            for init in ctx.fieldInitializer() or []:
                fields[self._get_text(init.identifier())] = self.visit_expression(init.expression())
            return nodes.StructInitializerExpression(location=self._loc(ctx), fields=fields)

        self._fallback(ctx, f"unrecognised literal {text!r}")
        return nodes.LiteralExpression(location=self._loc(ctx), value=text, literal_type="unknown")

    visit_Literal = visit_literal

    # ==========================================================================
    # Constraints
    # ==========================================================================

    def visit_Constraint(self, ctx) -> nodes.Constraint:
        """Visit constraint annotation: @range(0, 100)"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        args = []
        named: Dict[str, nodes.Expression] = {}
        arg_list_ctx = ctx.argumentList() if hasattr(ctx, "argumentList") and callable(ctx.argumentList) else None
        if arg_list_ctx is not None:
            # @name(arg, key=value, ...): positional and named arguments, in order
            for arg_ctx in arg_list_ctx.argument() or []:
                expr_ctx = arg_ctx.expression()
                if expr_ctx is not None:
                    arg = self.visit_expression(expr_ctx)
                    if arg:
                        args.append(arg)
                        key_ctx = arg_ctx.identifier()
                        if key_ctx is not None:
                            named[self._get_text(key_ctx)] = arg
        elif hasattr(ctx, "expressionList") and callable(ctx.expressionList):
            el_ctx = ctx.expressionList()
            if el_ctx and hasattr(el_ctx, "expression") and callable(el_ctx.expression):
                exprs = el_ctx.expression()
                if exprs:
                    # ANTLR4 returns a list for * or +, but check just in case
                    if not isinstance(exprs, list):
                        exprs = [exprs]
                    for expr_ctx in exprs:
                        if expr_ctx:
                            arg = self.visit_expression(expr_ctx)
                            if arg:
                                args.append(arg)
        elif hasattr(ctx, "expression") and callable(ctx.expression):
            exprs = ctx.expression()
            if exprs:
                if not isinstance(exprs, list):
                    exprs = [exprs]
                for expr_ctx in exprs:
                    if expr_ctx:
                        arg = self.visit_expression(expr_ctx)
                        if arg:
                            args.append(arg)

        return nodes.Constraint(location=self._loc(ctx), name=name, arguments=args, named_arguments=named)

    def _qos_from_constraints(self, constraints: List[nodes.Constraint]) -> Optional[nodes.QoSConfig]:
        """Build a QoSConfig from ``@qos(reliability="best_effort", depth=5, ...)``."""
        for constraint in constraints:
            if constraint.name != "qos":
                continue

            def text(key: str) -> Optional[str]:
                expr = constraint.named_arguments.get(key)
                if isinstance(expr, nodes.LiteralExpression):
                    return str(expr.value)
                if isinstance(expr, nodes.IdentifierExpression):
                    return expr.name
                return None

            depth_expr = constraint.named_arguments.get("depth")
            depth = depth_expr.value if isinstance(depth_expr, nodes.LiteralExpression) else None
            return nodes.QoSConfig(
                location=constraint.location,
                reliability=text("reliability") or "reliable",
                durability=text("durability"),
                depth=depth,
                history=text("history"),
            )
        return None

    # ==========================================================================
    # Node Declarations
    # ==========================================================================

    def visit_NodeDecl(self, ctx) -> nodes.NodeDecl:
        """Visit node declaration: node LidarProcessor { ... }"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        # Get body
        body = None
        if hasattr(ctx, "nodeBody") and callable(ctx.nodeBody):
            body = ctx.nodeBody()

        params = []
        subs = []
        pubs = []
        svcs = []
        acts = []
        lifecycle = None
        comps = []
        callbacks = []

        if body:
            # Parameters
            if hasattr(body, "parameterBlock") and callable(body.parameterBlock):
                pb = body.parameterBlock()
                if pb and hasattr(pb, "parameterDecl") and callable(pb.parameterDecl):
                    for p in pb.parameterDecl():
                        if p:
                            param = self.visit(p)
                            if param:
                                params.append(param)

            # Subscriptions
            if hasattr(body, "subscriptionBlock") and callable(body.subscriptionBlock):
                sb = body.subscriptionBlock()
                if sb and hasattr(sb, "subscriptionDecl") and callable(sb.subscriptionDecl):
                    for s in sb.subscriptionDecl():
                        if s:
                            sub = self.visit(s)
                            if sub:
                                subs.append(sub)

            # Publications
            if hasattr(body, "publicationBlock") and callable(body.publicationBlock):
                pb = body.publicationBlock()
                if pb and hasattr(pb, "publicationDecl") and callable(pb.publicationDecl):
                    for p in pb.publicationDecl():
                        if p:
                            pub = self.visit(p)
                            if pub:
                                pubs.append(pub)

            # Services
            if hasattr(body, "serviceBlock") and callable(body.serviceBlock):
                sb = body.serviceBlock()
                if sb and hasattr(sb, "serviceDecl") and callable(sb.serviceDecl):
                    for s in sb.serviceDecl():
                        if s:
                            svc = self.visit(s)
                            if svc:
                                svcs.append(svc)

            # Actions
            if hasattr(body, "actionBlock") and callable(body.actionBlock):
                ab = body.actionBlock()
                if ab and hasattr(ab, "actionDecl") and callable(ab.actionDecl):
                    for a in ab.actionDecl():
                        if a:
                            act = self.visit(a)
                            if act:
                                acts.append(act)

            # Lifecycle
            if hasattr(body, "lifecycleDecl") and callable(body.lifecycleDecl):
                lc_ctx = body.lifecycleDecl()
                if lc_ctx:
                    is_managed = hasattr(lc_ctx, "MANAGED") and lc_ctx.MANAGED() is not None
                    lifecycle = nodes.LifecycleDecl(location=self._loc(lc_ctx), is_managed=is_managed)

            # Components
            if hasattr(body, "componentBlock") and callable(body.componentBlock):
                cb = body.componentBlock()
                if cb and hasattr(cb, "componentDecl") and callable(cb.componentDecl):
                    for c in cb.componentDecl():
                        if c:
                            comp = self.visit(c)
                            if comp:
                                comps.append(comp)

            # Callbacks
            if hasattr(body, "callbackDecl") and callable(body.callbackDecl):
                for c in body.callbackDecl():
                    if c:
                        cb = self.visit(c)
                        if cb:
                            callbacks.append(cb)

        return nodes.NodeDecl(
            location=self._loc(ctx),
            name=name,
            parameters=params,
            subscriptions=subs,
            publications=pubs,
            services=svcs,
            actions=acts,
            lifecycle=lifecycle,
            components=comps,
            callbacks=callbacks,
        )

    def visit_ParameterDecl(self, ctx) -> nodes.ParameterDecl:
        """Visit parameter declaration: frame_id: string = "laser" @range(0, 100)"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        type_ = None
        if hasattr(ctx, "typeSpec") and callable(ctx.typeSpec):
            ts_ctx = ctx.typeSpec()
            if ts_ctx:
                type_ = self.visit_typeSpec(ts_ctx)

        default = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                default = self.visit_expression(expr_ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.ParameterDecl(
            location=self._loc(ctx), name=name, type=type_, default_value=default, constraints=constraints
        )

    def visit_SubscriptionDecl(self, ctx) -> nodes.SubscriptionDecl:
        """Visit subscription declaration: scan: LaserScan @topic("/scan")"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        # Get message type from qualified identifier
        msg_type = self._qualified_type_of(ctx)

        topic = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                topic = self.visit_expression(expr_ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.SubscriptionDecl(
            location=self._loc(ctx),
            name=name,
            message_type=msg_type,
            topic=topic,
            qos=self._qos_from_constraints(constraints),
            constraints=constraints,
        )

    def visit_PublicationDecl(self, ctx) -> nodes.PublicationDecl:
        """Visit publication declaration: processed_scan: LaserScan @topic("/out")"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        msg_type = self._qualified_type_of(ctx)

        topic = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                topic = self.visit_expression(expr_ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.PublicationDecl(
            location=self._loc(ctx),
            name=name,
            message_type=msg_type,
            topic=topic,
            qos=self._qos_from_constraints(constraints),
            constraints=constraints,
        )

    def visit_ServiceDecl(self, ctx) -> nodes.ServiceDecl:
        """Visit service declaration within node body."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        service_type = self._qualified_type_of(ctx)

        service_name = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                service_name = self.visit_expression(expr_ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.ServiceDecl(
            location=self._loc(ctx),
            name=name,
            service_type=service_type,
            service_name=service_name,
            constraints=constraints,
        )

    def visit_ActionDecl(self, ctx) -> nodes.ActionDecl:
        """Visit action declaration within node body."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        action_type = self._qualified_type_of(ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.ActionDecl(location=self._loc(ctx), name=name, action_type=action_type, constraints=constraints)

    def visit_ComponentDecl(self, ctx) -> nodes.ComponentDecl:
        """Visit component declaration: filter: PointCloudFilter { ... }"""
        ids = ctx.identifier()
        ids = ids if isinstance(ids, list) else [ids]
        name = self._get_text(ids[0]) if ids else ""
        component_type = self._get_text(ids[1]) if len(ids) > 1 else ""

        params = {}
        for po_ctx in ctx.parameterOverride() or []:
            key_ctx, val_ctx = po_ctx.identifier(), po_ctx.expression()
            if key_ctx is not None and val_ctx is not None:
                val = self.visit_expression(val_ctx)
                if val:
                    params[self._get_text(key_ctx)] = val

        return nodes.ComponentDecl(location=self._loc(ctx), name=name, component_type=component_type, parameters=params)

    def visit_CallbackDecl(self, ctx) -> nodes.CallbackDecl:
        """Visit callback declaration: on_scan_received(msg: LaserScan) { ... }"""
        event = ""

        # Check for lifecycle event keywords
        if hasattr(ctx, "ON_INIT") and ctx.ON_INIT() is not None:
            event = "on_init"
        elif hasattr(ctx, "ON_SHUTDOWN") and ctx.ON_SHUTDOWN() is not None:
            event = "on_shutdown"
        elif hasattr(ctx, "ON_PARAMETER_CHANGE") and ctx.ON_PARAMETER_CHANGE() is not None:
            event = "on_parameter_change"
        elif hasattr(ctx, "ON") and ctx.ON() is not None:
            # Custom event - get identifier after ON
            if hasattr(ctx, "identifier") and callable(ctx.identifier):
                id_ctx = ctx.identifier()
                if id_ctx:
                    event = self._get_text(id_ctx)

        params = []
        if hasattr(ctx, "parameterList") and callable(ctx.parameterList):
            pl_ctx = ctx.parameterList()
            if pl_ctx and hasattr(pl_ctx, "parameter") and callable(pl_ctx.parameter):
                for p_ctx in pl_ctx.parameter():
                    if p_ctx:
                        p = self.visit(p_ctx)
                        if p:
                            params.append(p)

        body = ""
        if hasattr(ctx, "PYTHON_CODE") and ctx.PYTHON_CODE() is not None:
            body = ctx.PYTHON_CODE().getText()
        elif hasattr(ctx, "pythonCode") and callable(ctx.pythonCode):
            pc_ctx = ctx.pythonCode()
            if pc_ctx:
                body = self._get_text(pc_ctx)

        return nodes.CallbackDecl(location=self._loc(ctx), event=event, parameters=params, body=body)

    def visit_parameter(self, ctx) -> nodes.ParameterDecl:
        """Visit parameter in callback parameter list."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        type_ = None
        if hasattr(ctx, "typeSpec") and callable(ctx.typeSpec):
            ts_ctx = ctx.typeSpec()
            if ts_ctx:
                type_ = self.visit_typeSpec(ts_ctx)

        return nodes.ParameterDecl(location=self._loc(ctx), name=name, type=type_)

    visit_Parameter = visit_parameter

    # ==========================================================================
    # Launch Declarations
    # ==========================================================================

    def visit_LaunchDecl(self, ctx) -> nodes.LaunchDecl:
        """Visit launch declaration: launch NavigationStack { ... }"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        body = None
        if hasattr(ctx, "launchBody") and callable(ctx.launchBody):
            body = ctx.launchBody()

        args = []
        groups = []
        containers = []
        includes = []
        lifecycle_mgr = None
        events = []

        if body:
            # Arguments
            if hasattr(body, "argumentBlock") and callable(body.argumentBlock):
                ab = body.argumentBlock()
                if ab and hasattr(ab, "argumentDecl") and callable(ab.argumentDecl):
                    for a in ab.argumentDecl():
                        if a:
                            arg = self.visit(a)
                            if arg:
                                args.append(arg)

            # Groups
            if hasattr(body, "groupDecl") and callable(body.groupDecl):
                for g in body.groupDecl():
                    if g:
                        group = self.visit(g)
                        if group:
                            groups.append(group)

            # Containers
            if hasattr(body, "containerDecl") and callable(body.containerDecl):
                for c in body.containerDecl():
                    if c:
                        container = self.visit(c)
                        if container:
                            containers.append(container)

            # Includes
            if hasattr(body, "includeDecl") and callable(body.includeDecl):
                for i in body.includeDecl():
                    if i:
                        inc = self.visit(i)
                        if inc:
                            includes.append(inc)

            # Lifecycle manager
            if hasattr(body, "lifecycleManagerDecl") and callable(body.lifecycleManagerDecl):
                lm_ctx = body.lifecycleManagerDecl()
                if lm_ctx:
                    lifecycle_mgr = self.visit(lm_ctx)

            # Events
            if hasattr(body, "launchEventDecl") and callable(body.launchEventDecl):
                for e in body.launchEventDecl():
                    if e:
                        event = self.visit(e)
                        if event:
                            events.append(event)

        return nodes.LaunchDecl(
            location=self._loc(ctx),
            name=name,
            arguments=args,
            groups=groups,
            containers=containers,
            includes=includes,
            lifecycle_manager=lifecycle_mgr,
            events=events,
        )

    def visit_ArgumentDecl(self, ctx) -> nodes.ArgumentDecl:
        """Visit argument declaration in launch."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        type_ = None
        if hasattr(ctx, "typeSpec") and callable(ctx.typeSpec):
            ts_ctx = ctx.typeSpec()
            if ts_ctx:
                type_ = self.visit_typeSpec(ts_ctx)

        default = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                default = self.visit_expression(expr_ctx)

        constraints = []
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c = self.visit(c_ctx)
                    if c:
                        constraints.append(c)

        return nodes.ArgumentDecl(
            location=self._loc(ctx), name=name, type=type_, default_value=default, constraints=constraints
        )

    def visit_GroupDecl(self, ctx) -> nodes.GroupDecl:
        """Visit group declaration: group sensors @namespace("sensors") { ... }"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        namespace = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                namespace = self.visit_expression(expr_ctx)

        nodes_list = []
        if hasattr(ctx, "nodeInstance") and callable(ctx.nodeInstance):
            for ni_ctx in ctx.nodeInstance():
                if ni_ctx:
                    ni = self.visit(ni_ctx)
                    if ni:
                        nodes_list.append(ni)

        return nodes.GroupDecl(location=self._loc(ctx), name=name, namespace=namespace, nodes=nodes_list)

    def visit_NodeInstance(self, ctx) -> nodes.NodeInstance:
        """Visit node instance: lidar: LidarProcessor { ... }"""
        name = ""
        node_type = ""

        # Get identifiers - first is name, second is type
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            ids = ctx.identifier()
            if ids and len(ids) > 0:
                name = self._get_text(ids[0])
            if ids and len(ids) > 1:
                node_type = self._get_text(ids[1])

        params = {}
        if hasattr(ctx, "nodeConfig") and callable(ctx.nodeConfig):
            for config in ctx.nodeConfig():
                if config and hasattr(config, "parameterOverride") and callable(config.parameterOverride):
                    for override in config.parameterOverride():
                        if override and hasattr(override, "identifier") and callable(override.identifier):
                            key_ctx = override.identifier()
                            if key_ctx:
                                key = self._get_text(key_ctx)
                                if hasattr(override, "expression") and callable(override.expression):
                                    val_ctx = override.expression()
                                    if val_ctx:
                                        val = self.visit_expression(val_ctx)
                                        if val:
                                            params[key] = val

        remaps: Dict[str, str] = {}
        for config in ctx.nodeConfig() or []:
            for remap in config.remapDecl() or []:
                source, target = remap.identifier(), remap.STRING_LITERAL()
                if source is not None and target is not None:
                    remaps[self._get_text(source)] = self._strip_quotes(target.getText())

        constraints = []
        for c_ctx in ctx.constraint() or []:
            c = self.visit(c_ctx)
            if c:
                constraints.append(c)

        # `@when(expr)` makes the node conditional on a launch argument
        condition = next((c.arguments[0] for c in constraints if c.name == "when" and c.arguments), None)

        return nodes.NodeInstance(
            location=self._loc(ctx),
            name=name,
            node_type=node_type,
            parameters=params,
            remaps=remaps,
            condition=condition,
        )

    def visit_ContainerDecl(self, ctx) -> nodes.ContainerDecl:
        """Visit container declaration for composable nodes."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        container_name = None
        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                container_name = self.visit_expression(expr_ctx)

        components = []
        if hasattr(ctx, "componentInstance") and callable(ctx.componentInstance):
            for ci_ctx in ctx.componentInstance():
                if ci_ctx:
                    comp = self.visit(ci_ctx)
                    if comp:
                        components.append(comp)

        return nodes.ContainerDecl(
            location=self._loc(ctx), name=name, container_name=container_name, components=components
        )

    def visit_ComponentInstance(self, ctx) -> nodes.ComponentInstance:
        """Visit component instance in container."""
        name = ""
        component_type = ""

        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            ids = ctx.identifier()
            if ids and len(ids) > 0:
                name = self._get_text(ids[0])
            if ids and len(ids) > 1:
                component_type = self._get_text(ids[1])

        params = {}
        if hasattr(ctx, "parameterOverride") and callable(ctx.parameterOverride):
            for po_ctx in ctx.parameterOverride():
                if po_ctx and hasattr(po_ctx, "identifier") and callable(po_ctx.identifier):
                    key_ctx = po_ctx.identifier()
                    if key_ctx:
                        key = self._get_text(key_ctx)
                        if hasattr(po_ctx, "expression") and callable(po_ctx.expression):
                            val_ctx = po_ctx.expression()
                            if val_ctx:
                                val = self.visit_expression(val_ctx)
                                if val:
                                    params[key] = val

        return nodes.ComponentInstance(
            location=self._loc(ctx), name=name, component_type=component_type, parameters=params
        )

    def visit_IncludeDecl(self, ctx) -> nodes.IncludeDecl:
        """Visit include declaration: include robot_description.launch { ... }"""
        target = ""
        arguments = {}

        # Get target (string literal or identifier)
        if hasattr(ctx, "STRING_LITERAL") and ctx.STRING_LITERAL() is not None:
            target = self._strip_quotes(ctx.STRING_LITERAL().getText())
        elif hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                target = self._get_text(id_ctx)

        # Get arguments
        if hasattr(ctx, "includeArgs") and callable(ctx.includeArgs):
            ia_ctx = ctx.includeArgs()
            if ia_ctx and hasattr(ia_ctx, "namedArgument") and callable(ia_ctx.namedArgument):
                for na_ctx in ia_ctx.namedArgument():
                    if na_ctx and hasattr(na_ctx, "identifier") and callable(na_ctx.identifier):
                        key_ctx = na_ctx.identifier()
                        if key_ctx:
                            key = self._get_text(key_ctx)
                            if hasattr(na_ctx, "expression") and callable(na_ctx.expression):
                                val_ctx = na_ctx.expression()
                                if val_ctx:
                                    val = self.visit_expression(val_ctx)
                                    if val:
                                        arguments[key] = val

        return nodes.IncludeDecl(location=self._loc(ctx), target=target, arguments=arguments)

    def visit_LifecycleManagerDecl(self, ctx) -> nodes.LifecycleManagerDecl:
        """Visit lifecycle manager declaration: ``lifecycle manager <Name> { ... }``."""
        name = ""
        ids = ctx.identifier() if hasattr(ctx, "identifier") and callable(ctx.identifier) else []
        if ids:
            # the rule is `LIFECYCLE identifier identifier`: the last one names the manager
            name = self._get_text(ids[-1] if isinstance(ids, list) else ids)

        managed_nodes = []
        if hasattr(ctx, "managesBlock") and callable(ctx.managesBlock):
            mb_ctx = ctx.managesBlock()
            if mb_ctx and hasattr(mb_ctx, "identifier") and callable(mb_ctx.identifier):
                for id_ctx in mb_ctx.identifier():
                    if id_ctx:
                        node_name = self._get_text(id_ctx)
                        if node_name:
                            managed_nodes.append(node_name)

        transitions = []
        if hasattr(ctx, "transitionBlock") and callable(ctx.transitionBlock):
            tb_ctx = ctx.transitionBlock()
            if tb_ctx and hasattr(tb_ctx, "transitionDecl") and callable(tb_ctx.transitionDecl):
                for t_ctx in tb_ctx.transitionDecl():
                    if t_ctx:
                        t = self.visit(t_ctx)
                        if t:
                            transitions.append(t)

        return nodes.LifecycleManagerDecl(
            location=self._loc(ctx), name=name, managed_nodes=managed_nodes, transitions=transitions
        )

    def visit_TransitionDecl(self, ctx) -> nodes.TransitionDecl:
        """Visit transition declaration: { from: unconfigured, to: inactive }"""
        from_state = ""
        to_state = ""
        delay = None

        if hasattr(ctx, "FROM") and ctx.FROM() is not None:
            if hasattr(ctx, "identifier") and callable(ctx.identifier):
                ids = ctx.identifier()
                if ids and len(ids) > 0:
                    from_state = self._get_text(ids[0])
                if ids and len(ids) > 1:
                    to_state = self._get_text(ids[1])

        # Check for delay constraint
        if hasattr(ctx, "constraint") and callable(ctx.constraint):
            for c_ctx in ctx.constraint():
                if c_ctx:
                    c_name = ""
                    if hasattr(c_ctx, "identifier") and callable(c_ctx.identifier):
                        id_ctx = c_ctx.identifier()
                        if id_ctx:
                            c_name = self._get_text(id_ctx)
                    if c_name == "delay" and hasattr(c_ctx, "expressionList"):
                        el_ctx = c_ctx.expressionList()
                        if el_ctx and hasattr(el_ctx, "expression"):
                            exprs = el_ctx.expression()
                            if exprs and len(exprs) > 0:
                                expr = self.visit_expression(exprs[0])
                                if isinstance(expr, nodes.LiteralExpression) and expr.literal_type in ("float", "int"):
                                    delay = float(expr.value)

        return nodes.TransitionDecl(location=self._loc(ctx), from_state=from_state, to_state=to_state, delay=delay)

    def visit_LaunchEventDecl(self, ctx) -> nodes.LaunchEventDecl:
        """Visit launch event handler: on "topic" { ... }"""
        trigger = ""
        if hasattr(ctx, "STRING_LITERAL") and ctx.STRING_LITERAL() is not None:
            trigger = self._strip_quotes(ctx.STRING_LITERAL().getText())

        actions = []
        if hasattr(ctx, "eventAction") and callable(ctx.eventAction):
            for ea_ctx in ctx.eventAction():
                if ea_ctx:
                    action = self.visit(ea_ctx)
                    if action:
                        actions.append(action)

        return nodes.LaunchEventDecl(location=self._loc(ctx), trigger=trigger, actions=actions)

    def visit_EventAction(self, ctx) -> nodes.EventAction:
        """Visit event action: node.enabled = true"""
        target = ""
        prop = ""
        value = None

        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            ids = ctx.identifier()
            if ids and len(ids) > 0:
                target = self._get_text(ids[0])
            if ids and len(ids) > 1:
                prop = self._get_text(ids[1])

        if hasattr(ctx, "expression") and callable(ctx.expression):
            expr_ctx = ctx.expression()
            if expr_ctx:
                value = self.visit_expression(expr_ctx)

        return nodes.EventAction(
            location=self._loc(ctx),
            target=target,
            property=prop,
            value=value if value else nodes.LiteralExpression(location=self._loc(ctx), value=True, literal_type="bool"),
        )

    # ==========================================================================
    # Interface Declarations
    # ==========================================================================

    def visit_InterfaceDecl(self, ctx) -> nodes.InterfaceDecl:
        """Visit an interface declaration (message, service or action).

        ``interfaceDecl`` is a single-alternative rule, so exactly one of the
        sub-contexts is present and ANTLR returns it directly (not a list).
        """
        declarations = []

        for accessor in ("messageDecl", "serviceDecl_interface", "actionDecl_interface"):
            sub_ctx = self._first(getattr(ctx, accessor)()) if hasattr(ctx, accessor) else None
            if sub_ctx is not None:
                decl = self.visit(sub_ctx)
                if decl:
                    declarations.append(decl)

        return nodes.InterfaceDecl(location=self._loc(ctx), declarations=declarations)

    def visit_MessageDecl(self, ctx) -> nodes.MessageDecl:
        """Visit message declaration: message SensorFusionOutput @id(1) { ... }"""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        msg_id = self._interface_id(ctx)

        fields = []
        if hasattr(ctx, "fieldDecl") and callable(ctx.fieldDecl):
            for f_ctx in ctx.fieldDecl():
                if f_ctx:
                    f = self.visit(f_ctx)
                    if f:
                        fields.append(f)

        return nodes.MessageDecl(location=self._loc(ctx), name=name, id=msg_id, fields=fields)

    def visit_ServiceDecl_interface(self, ctx) -> nodes.ServiceInterfaceDecl:
        """Visit service interface declaration."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        svc_id = self._interface_id(ctx)

        request_fields = []
        response_fields = []

        if hasattr(ctx, "requestBlock") and callable(ctx.requestBlock):
            rb_ctx = ctx.requestBlock()
            if rb_ctx and hasattr(rb_ctx, "fieldDecl") and callable(rb_ctx.fieldDecl):
                for f_ctx in rb_ctx.fieldDecl():
                    if f_ctx:
                        f = self.visit(f_ctx)
                        if f:
                            request_fields.append(f)

        if hasattr(ctx, "responseBlock") and callable(ctx.responseBlock):
            rb_ctx = ctx.responseBlock()
            if rb_ctx and hasattr(rb_ctx, "fieldDecl") and callable(rb_ctx.fieldDecl):
                for f_ctx in rb_ctx.fieldDecl():
                    if f_ctx:
                        f = self.visit(f_ctx)
                        if f:
                            response_fields.append(f)

        return nodes.ServiceInterfaceDecl(
            location=self._loc(ctx),
            name=name,
            id=svc_id,
            request_fields=request_fields,
            response_fields=response_fields,
        )

    def visit_ActionDecl_interface(self, ctx) -> nodes.ActionInterfaceDecl:
        """Visit action interface declaration."""
        name = ""
        if hasattr(ctx, "identifier") and callable(ctx.identifier):
            id_ctx = ctx.identifier()
            if id_ctx:
                name = self._get_text(id_ctx)

        act_id = self._interface_id(ctx)

        goal_fields = []
        feedback_fields = []
        result_fields = []

        if hasattr(ctx, "goalBlock") and callable(ctx.goalBlock):
            gb_ctx = ctx.goalBlock()
            if gb_ctx and hasattr(gb_ctx, "fieldDecl") and callable(gb_ctx.fieldDecl):
                for f_ctx in gb_ctx.fieldDecl():
                    if f_ctx:
                        f = self.visit(f_ctx)
                        if f:
                            goal_fields.append(f)

        if hasattr(ctx, "feedbackBlock") and callable(ctx.feedbackBlock):
            fb_ctx = ctx.feedbackBlock()
            if fb_ctx and hasattr(fb_ctx, "fieldDecl") and callable(fb_ctx.fieldDecl):
                for f_ctx in fb_ctx.fieldDecl():
                    if f_ctx:
                        f = self.visit(f_ctx)
                        if f:
                            feedback_fields.append(f)

        if hasattr(ctx, "resultBlock") and callable(ctx.resultBlock):
            rb_ctx = ctx.resultBlock()
            if rb_ctx and hasattr(rb_ctx, "fieldDecl") and callable(rb_ctx.fieldDecl):
                for f_ctx in rb_ctx.fieldDecl():
                    if f_ctx:
                        f = self.visit(f_ctx)
                        if f:
                            result_fields.append(f)

        return nodes.ActionInterfaceDecl(
            location=self._loc(ctx),
            name=name,
            id=act_id,
            goal_fields=goal_fields,
            feedback_fields=feedback_fields,
            result_fields=result_fields,
        )

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    @staticmethod
    def _first(ctx_or_list):
        """ANTLR returns a list for repeated sub-rules and a single context otherwise."""
        if isinstance(ctx_or_list, list):
            return ctx_or_list[0] if ctx_or_list else None
        return ctx_or_list

    def _interface_id(self, ctx) -> int:
        """Value of ``@id(N)`` on an interface declaration."""
        token = ctx.INT_LITERAL() if hasattr(ctx, "INT_LITERAL") else None
        return int(token.getText()) if token is not None else 0

    def _get_text(self, ctx) -> str:
        """Safely get text from a context."""
        if ctx is None:
            return ""
        if hasattr(ctx, "getText"):
            return ctx.getText()
        return str(ctx)

    def _strip_quotes(self, text: str) -> str:
        """Strip quotes from string literal."""
        if text is None:
            return ""
        text = text.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
            return text[1:-1]
        return text
